// Concerto encode + upload worker.
//
// Receives composited frames as ImageBitmap from the main thread, JPEG-encodes
// them on a worker thread (off the main thread), batches them, and POSTs to
// /concerto_frames. Sends back per-frame `frameAck` messages so the main
// thread can apply backpressure when the worker falls behind.
//
// Wire format to /concerto_frames is unchanged from the in-process version:
//   form `frames`       : concatenated JPEG bytes
//   form `start_index`  : first frame index within the current segment
//   form `count`        : number of frames in this batch
//   form `lengths`      : comma-separated JPEG byte sizes (per-frame)
//
// Message protocol (main → worker):
//   {type:'init', jpegQuality, batchSize, maxInflight}
//   {type:'beginSegment'}                       — reset per-segment state
//   {type:'frame', bitmap, frameIdx}            — bitmap is in transfer list
//   {type:'flushSegment'}                       — drain pending uploads
//   {type:'shutdown'}                           — graceful close
//
// Message protocol (worker → main):
//   {type:'frameAck', frameIdx}                 — encode + queued for upload
//   {type:'segmentDone'}                        — flushSegment complete
//   {type:'error', message}                     — fatal worker error

'use strict';

// Wire format is chosen by the main thread and sent via the `init` message.
// Accepted values: 'png' (lossless, default) or 'jpeg' (smaller, slight
// ringing on high-frequency content). JPEG quality is 0.92 which stays on
// Chromium's fast encoder path (q=1.0 engages a 3-5× slower max-quality
// mode). The server's `/concerto_start` receives the same choice and
// configures ffmpeg's input demuxer accordingly.
let BATCH_SIZE   = 10;
let MAX_INFLIGHT = 2;
let WIRE_FORMAT  = 'png';

let _canvas        = null;   // worker-side OffscreenCanvas (sized lazily)
let _ctx           = null;
let _batchBuf      = [];     // Array<Blob> — encoded frames
let _batchStartIdx = 0;      // first frame index of the current batch (per segment)
let _inflight      = [];     // Array<Promise> — in-flight upload promises
let _shuttingDown  = false;

// Serialise message processing — each frame requires `await convertToBlob`
// and a possible `await inflight[0]`, so we can't process messages
// concurrently or frames would arrive out of order.
let _processing = Promise.resolve();

self.onmessage = (e) => {
  _processing = _processing.then(() => _handle(e.data)).catch((err) => {
    self.postMessage({ type: 'error', message: String(err && err.message || err) });
  });
};

async function _handle(msg) {
  if (_shuttingDown) return;
  switch (msg.type) {
    case 'init':           return _onInit(msg);
    case 'beginSegment':   return _onBeginSegment();
    case 'frame':          return _onFrame(msg);
    case 'flushSegment':   return _onFlushSegment();
    case 'shutdown':       _shuttingDown = true; return;
    default:               throw new Error('unknown message type: ' + msg.type);
  }
}

function _onInit(msg) {
  if (typeof msg.batchSize   === 'number') BATCH_SIZE   = msg.batchSize;
  if (typeof msg.maxInflight === 'number') MAX_INFLIGHT = msg.maxInflight;
  if (typeof msg.wireFormat  === 'string') WIRE_FORMAT  = msg.wireFormat;
}

function _onBeginSegment() {
  // Each segment's ffmpeg sees frames numbered from 0; reset per-segment state.
  _batchBuf      = [];
  _batchStartIdx = 0;
  _inflight      = [];
}

async function _onFrame(msg) {
  const bitmap = msg.bitmap;
  const frameIdx = msg.frameIdx;

  // Lazily create / resize the worker-side canvas to match bitmap dimensions.
  if (!_canvas || _canvas.width !== bitmap.width || _canvas.height !== bitmap.height) {
    _canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
    _ctx    = _canvas.getContext('2d');
  }

  _ctx.drawImage(bitmap, 0, 0);
  // Free the transferred ImageBitmap as soon as we've drawn it.
  bitmap.close();

  // Wire-format-aware encode. Raw RGBA skips convertToBlob entirely —
  // just reads pixels via getImageData, which is a fixed-cost memory copy
  // immune to the fps-decay that toBlob/convertToBlob suffers.
  let frameChunk;
  if (WIRE_FORMAT === 'raw') {
    const imageData = _ctx.getImageData(0, 0, _canvas.width, _canvas.height);
    frameChunk = new Uint8Array(imageData.data.buffer);
  } else {
    const encodeOpts = (WIRE_FORMAT === 'jpeg')
      ? { type: 'image/jpeg', quality: 0.92 }
      : { type: 'image/png' };
    frameChunk = await _canvas.convertToBlob(encodeOpts);
  }
  _batchBuf.push(frameChunk);

  // If pushing this frame completed a batch, flush it BEFORE acking — that
  // way the main thread's MAX_FRAMES_BEHIND backpressure applies to the
  // upload pipeline too, not just the encode. Otherwise acks pile up while
  // _batchBuf + _inflight grow unbounded at slow upload speeds.
  if (_batchBuf.length >= BATCH_SIZE) {
    await _flushBatch();
  }

  self.postMessage({ type: 'frameAck', frameIdx: frameIdx });
}

async function _onFlushSegment() {
  if (_batchBuf.length) await _flushBatch();
  if (_inflight.length) await Promise.all(_inflight);
  self.postMessage({ type: 'segmentDone' });
}

async function _flushBatch() {
  const frames    = _batchBuf;
  const startIdx  = _batchStartIdx;
  const lengths   = frames.map(b => b.size || b.byteLength || b.length).join(',');
  const blob      = new Blob(frames, { type: 'application/octet-stream' });
  const fd        = new FormData();
  const fname = (WIRE_FORMAT === 'raw') ? 'batch.raw'
              : (WIRE_FORMAT === 'jpeg') ? 'batch.mjpeg'
              : 'batch.png';
  fd.append('frames',      blob, fname);
  fd.append('start_index', String(startIdx));
  fd.append('count',       String(frames.length));
  fd.append('lengths',     lengths);

  const upload = fetch('/concerto_frames', { method: 'POST', body: fd })
    .then(async (res) => {
      if (!res.ok) {
        let detail = '';
        try { detail = (await res.json()).error || ''; } catch {}
        throw new Error(`upload ${res.status}: ${detail}`);
      }
    })
    .finally(() => {
      _inflight = _inflight.filter(p => p !== upload);
    });

  _inflight.push(upload);
  _batchStartIdx += frames.length;
  _batchBuf = [];

  // Cap concurrent uploads — same FIFO awaiting as the pre-worker version.
  if (_inflight.length >= MAX_INFLIGHT) await _inflight[0];
}
