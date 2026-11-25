// ─── interpreter.js ───────────────────────────────────────────────────────────
// Core interpreter logic: score loading, preview, save/load interpretation.
// Depends on: state.js (interpState, state), golems.js, kalman-trace.js

// ─── Score load ───────────────────────────────────────────────────────────────
async function _loadInterpScore() {
  const pathEl   = document.getElementById('interp-score-path');
  const statusEl = document.getElementById('interp-score-status');
  const path = pathEl.value.trim();
  if (!path) { statusEl.textContent = 'enter a score path'; return; }
  statusEl.textContent = 'loading…';
  try {
    const res  = await fetch('/load_yaml', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({path}) });
    const data = await res.json();
    if (data.error) { statusEl.textContent = 'error: ' + data.error; return; }
    const sc = data.score;
    interpState.scorePath = path;
    // Golems belong to the score — a score without golems resets them
    interpState.golems = (sc.golems && sc.golems.length) ? sc.golems : [];
    _selectedGolemIdx = null;
    clearHistory();
    _renderGolemCards();
    // Auto-fill audio path from score base_track
    const bt = sc.base_track || (sc.tracks && sc.tracks[0] && sc.tracks[0].path) || '';
    const audioEl = document.getElementById('interp-audio-path');
    if (bt && audioEl && !audioEl.value.trim()) audioEl.value = bt;
    interpState.scoreDynamics = (sc.dynamics || []).map(d => {
      if (d.marking !== undefined && d.mark === undefined) { const {marking, ...r} = d; return {...r, mark: marking}; }
      return d;
    });
    // Build full score data for draw.js overlays
    const _IC = ["#7788aa","#aa8877","#77aa88","#aa7788","#88aa77","#8877aa","#aaaa77","#77aaaa"];
    interpState.scoreData = {
      samples: Object.fromEntries(
        Object.entries(sc.samples || {}).map(([k, v], i) => [k, { ...v, color: _IC[i % _IC.length] }])
      ),
      dynamics:     interpState.scoreDynamics,
      tempo:        (sc.tempo   || []).map(t => ({ ...t, from: t.from||0, to: t.to||0,
                      mark: t.mark || (t.factor > 1 ? 'accelerando' : 'ritardando') })),
      events:       (sc.events        || []),
      phrases:      (sc.phrases       || []),
      fxRanges:     zonesFromScore(sc),
      noteRel:      (sc.note_rel      || []),
      articulations:(sc.articulations || []),
    };
    // Sync score data into shared state (same as composer import) so Composer sees it too
    state.samples       = sc.samples || {};
    state.dynamics      = interpState.scoreDynamics;
    state.tempo         = interpState.scoreData.tempo;
    state.events        = sc.events        || [];
    state.phrases       = (sc.phrases      || []).map(p => Object.assign({ gain_db: 0, fade_in: 0, fade_out: 0, tempo_factor: 1.0 }, p));
    state.noteRel       = sc.note_rel      || [];
    state.articulations = sc.articulations || [];
    state.baseFx        = sc.base_fx       || [];
    state.fxRanges      = zonesFromScore(sc);
    outputSettingsFromScore(sc);
    state.scoreExtras   = scoreExtrasFrom(sc);
    state.lastScorePath = path;
    // Sync to Composer's import path input
    const _impIn = document.getElementById('import-path');
    if (_impIn) _impIn.value = path;
    for (const k of Object.keys(state.samples)) {
      if (!state.samples[k].color) state.samples[k].color = nextColor();
    }
    if (typeof updateScoreInfo === 'function') updateScoreInfo();

    // Auto-load score images into shared scoreView/score2View
    if (sc.score_image) {
      const imgEl = document.getElementById('interp-score-img-path');
      if (imgEl && !imgEl.value.trim()) imgEl.value = sc.score_image;
      _loadImageIntoView(sc.score_image, 'score');
    }
    if (sc.score2_image) {
      const img2El = document.getElementById('interp-meta-img-path');
      if (img2El && !img2El.value.trim()) img2El.value = sc.score2_image;
      _loadImageIntoView(sc.score2_image, 'meta');
    }

    interpState.scoreDuration = _estimateScoreDuration(sc);
    const dur = interpState.scoreDuration;
    statusEl.textContent = path.split('/').pop();
    statusEl.title = dur ? `${path} (${dur.toFixed(1)}s)` : path;
    drawGolemTimeline();
    if (typeof draw === 'function') draw();
  } catch(e) { statusEl.textContent = 'failed: ' + e; }
}

function _loadImageIntoView(imgPath, which) {
  const img = new Image();
  img.onload = () => {
    const view = (which === 'score') ? scoreView : score2View;
    view.img       = img;
    view.path      = imgPath;
    view.start     = 0;
    view.end       = interpState.scoreDuration || state.duration || 0;
    view.panOffset = 0;
    // Sync to Composer path inputs
    const inputId = (which === 'score') ? 'score-path-input' : 'score2-path-input';
    const el = document.getElementById(inputId);
    if (el) el.value = imgPath;
    // Make score2 container visible (it's hidden until explicitly shown)
    if (which === 'meta') {
      const s2 = document.getElementById('score2-container');
      if (s2) s2.classList.add('visible');
    }
    if (typeof draw === 'function') draw();
  };
  img.onerror = () => {
    console.warn('Failed to load image:', imgPath);
    const statusEl = document.getElementById('interp-save-status');
    if (statusEl) statusEl.textContent = 'image not found: ' + imgPath.split('/').pop();
  };
  img.src = `/image?path=${encodeURIComponent(imgPath)}`;
}

function _estimateScoreDuration(sc) {
  let max = 0;
  (sc.events  || []).forEach(e => { if ((e.t||0) > max) max = e.t; });
  (sc.dynamics|| []).forEach(d => { const t = d.to || d.t || 0; if (t > max) max = t; });
  (sc.tempo   || []).forEach(t => { if ((t.to||0) > max) max = t.to; });
  (sc.phrases || []).forEach(p => { if ((p.to||0) > max) max = p.to; });
  return max;
}

// ─── Preview ──────────────────────────────────────────────────────────────────
// Copy UI-only settings (seed box, Global Settings panel) into interpState.v2config
// so every request that sends v2config carries them.
function _syncInterpConfigFromUI() {
  const seedEl = document.getElementById('interp-seed');
  if (seedEl && seedEl.value.trim() !== '' && !isNaN(parseInt(seedEl.value)))
    interpState.v2config.seed = parseInt(seedEl.value);
  else
    interpState.v2config.seed = null;
  // The trace step changes the performance (the filter steps on that grid),
  // so every render uses the box's value, not only Trace
  const stepEl = document.getElementById('interp-trace-step');
  if (stepEl) {
    if (!interpState.v2config.v2) interpState.v2config.v2 = {};
    interpState.v2config.v2.trace_step = parseFloat(stepEl.value) || 0;
  }
  if (typeof _syncGlobalSettings === 'function') _syncGlobalSettings();
}

// Store the score→real tempo map returned by /preview (mirrors renderAndPlay)
function _storeTempoMap(data) {
  state.tempoMap     = Array.isArray(data.tempo_map) ? data.tempo_map : [];
  state.durationReal = data.duration_real || 0;
}

async function renderScoreAndPlay() {
  const audioPathEl = document.getElementById('interp-audio-path');
  const audioPath   = (audioPathEl && audioPathEl.value.trim()) || state.filePath;
  if (!audioPath) { _setPlayStatus('load audio first'); return; }
  if (!interpState.scorePath) { _setPlayStatus('load a score first'); return; }
  const gen = _claimRenderGen();
  const btn = document.getElementById('play-btn');
  if (btn) btn.disabled = true;
  _setPlayBtn('⏳ rendering…');
  try {
    const renderKey = _mixRenderKey('score');
    const body = {
      path:       audioPath,
      score_path: interpState.scorePath,
      // The score as written: the plain (v1) engine — no golems, and no
      // random per-note timing / attack / release from a default character
      engine:     'v1',
      interp:     { golems: [], v2config: {}, mix_dims: interpState.mix_dims },
      loudness:   previewLoudness(),
    };
    const res  = await fetch('/preview', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    if (gen !== _renderGen) return;   // cancelled by stop or newer render
    if (data.error) { _setPlayStatus('error: ' + (data.detail || data.error)); return; }
    showBrakeReport(data.loudness);
    _storeTempoMap(data);
    const audioRes = await fetch(data.url);
    if (!audioRes.ok) throw new Error(`Audio fetch failed (${audioRes.status})`);
    const ab  = await audioRes.arrayBuffer();
    if (gen !== _renderGen) return;   // cancelled while decoding
    const buf = await _getMixCtx().decodeAudioData(ab);
    _setPlayStatus('');
    await playMixBuffer(buf, scoreToReal(state.currentTime || 0));
    _mixBufKey = renderKey;
  } catch(e) { if (gen === _renderGen) _setPlayStatus('failed: ' + e); }
  finally { if (btn) btn.disabled = false; if (!_mixPlaying) _setPlayBtn('▶ Play'); }
}

async function renderInterpAndPlay() {
  const audioPathEl = document.getElementById('interp-audio-path');
  const audioPath   = (audioPathEl && audioPathEl.value.trim()) || state.filePath;
  if (!audioPath) { _setPlayStatus('load audio first'); return; }
  if (!interpState.scorePath) { _setPlayStatus('load a score first'); return; }
  const gen = _claimRenderGen();
  const btn = document.getElementById('play-btn');
  if (btn) btn.disabled = true;
  _setPlayBtn('⏳ rendering…');
  try {
    _syncInterpConfigFromUI();
    const renderKey = _mixRenderKey('interp');
    const body = {
      path:       audioPath,
      score_path: interpState.scorePath,
      interp: {
        golems:   interpState.golems,
        v2config: interpState.v2config,
        mix_dims: interpState.mix_dims,
      },
      loudness: previewLoudness(),
    };
    const res  = await fetch('/preview', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body) });
    const data = await res.json();
    if (gen !== _renderGen) return;   // cancelled by stop or newer render
    if (data.error) { _setPlayStatus('error: ' + (data.detail || data.error)); return; }
    showBrakeReport(data.loudness);
    _storeTempoMap(data);
    const audioRes = await fetch(data.url);
    if (!audioRes.ok) throw new Error(`Audio fetch failed (${audioRes.status})`);
    const ab  = await audioRes.arrayBuffer();
    if (gen !== _renderGen) return;   // cancelled while decoding
    const buf = await _getMixCtx().decodeAudioData(ab);
    _setPlayStatus('');
    await playMixBuffer(buf, scoreToReal(state.currentTime || 0));
    _mixBufKey = renderKey;
    // Fetch trace after audio starts — updateVizPanel self-animates while isMixPlaying()
    if (typeof fetchAndDrawTrace === 'function') {
      // The trace of the performance just played: the seed this render used
      fetchAndDrawTrace({ seed: data.seed }).then(() => {
        // The trace echoes its effective seed into the seed box; that alone
        // shouldn't invalidate the buffer we just rendered.
        const now   = _mixRenderKey('interp');
        const strip = k => { const o = JSON.parse(k); delete o.seed; return JSON.stringify(o); };
        if (_mixBuf === buf && _mixBufKey === renderKey && strip(now) === strip(renderKey)) _mixBufKey = now;
      });
    }
  } catch(e) { if (gen === _renderGen) _setPlayStatus('failed: ' + e); }
  finally { if (btn) btn.disabled = false; if (!_mixPlaying) _setPlayBtn('▶ Play'); }
}

// ─── Save / Load interpretation ───────────────────────────────────────────────
async function saveInterp() {
  const nameEl   = document.getElementById('interp-name');
  const statusEl = document.getElementById('interp-save-status');
  statusEl.textContent = 'saving…';
  try {
    _syncInterpConfigFromUI();
    const res  = await fetch('/save_interpretation', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({
        name:       nameEl.value.trim() || 'untitled_interp',
        score_path: interpState.scorePath,
        golems:     interpState.golems,
        v2config:   interpState.v2config,
        mix_dims:   interpState.mix_dims,
      })
    });
    const data = await res.json();
    if (data.error) { statusEl.textContent = 'error: ' + data.error; return; }
    statusEl.textContent = 'saved → ' + data.path.split('/').slice(-2).join('/');
    setTimeout(() => { statusEl.textContent = ''; }, 4000);
  } catch(e) { statusEl.textContent = 'failed: ' + e; }
}

async function loadInterp() {
  const pathEl   = document.getElementById('interp-load-path');
  const statusEl = document.getElementById('interp-save-status');
  const path = pathEl.value.trim();
  if (!path) { statusEl.textContent = 'enter interpretation path'; return; }
  statusEl.textContent = 'loading…';
  try {
    const res  = await fetch('/load_interpretation', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (data.error) { statusEl.textContent = 'error: ' + data.error; return; }
    const interp = data.interp;
    // Load its score first (overlays, duration, images, the score's golems)…
    if (interp.score_path) {
      document.getElementById('interp-score-path').value = interp.score_path;
      await _loadInterpScore();
    }
    // …then the interpretation on top of it
    if (interp.golems) { interpState.golems = interp.golems; _selectedGolemIdx = null; clearHistory(); }
    if (interp.v2config) {
      // Replace, don't merge: nothing lingers from the previous session
      interpState.v2config = { engine: 'v2', seed: null, ...interp.v2config,
                               v2: { ...(interp.v2config.v2 || {}) } };
      const v2 = interpState.v2config.v2;
      _setInput('interp-seed', interp.v2config.seed != null ? interp.v2config.seed : '');
      if (v2.timbral_pull != null) _setInput('interp-timbral-pull', v2.timbral_pull);
      if (v2.trace_step != null)   _setInput('interp-trace-step', v2.trace_step);
      if (typeof _populateGlobalSettings === 'function') _populateGlobalSettings();
    }
    if (Array.isArray(interp.mix_dims)) {
      interpState.mix_dims = interp.mix_dims;
      document.querySelectorAll('.mix-dim-cb').forEach(cb => { cb.checked = interp.mix_dims.includes(cb.dataset.dim); });
    }
    _renderGolemCards();
    drawGolemTimeline();
    statusEl.textContent = 'loaded ← ' + path.split('/').slice(-2).join('/');
    setTimeout(() => { statusEl.textContent = ''; }, 4000);
  } catch(e) { statusEl.textContent = 'failed: ' + e; }
}

function _setInput(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}

// ─── DOMContentLoaded wiring ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Score load
  const loadScoreBtn = document.getElementById('interp-load-score-btn');
  if (loadScoreBtn) loadScoreBtn.addEventListener('click', _loadInterpScore);

  // Mix dimension toggles
  document.querySelectorAll('.mix-dim-cb').forEach(cb => {
    cb.addEventListener('change', () => {
      pushHistory();                       // undoable, and re-renders while playing
      const dims = [];
      document.querySelectorAll('.mix-dim-cb').forEach(el => {
        if (el.checked) dims.push(el.dataset.dim);
      });
      interpState.mix_dims = dims;
      // the trace shows the dims you hear
      if (typeof _lastTraceData !== 'undefined' && _lastTraceData) drawKalmanTrace(_lastTraceData);
    });
  });

  // Timbral pull slider
  const tpInput = document.getElementById('interp-timbral-pull');
  if (tpInput) tpInput.addEventListener('change', () => {
    pushHistory();
    if (!interpState.v2config.v2) interpState.v2config.v2 = {};
    interpState.v2config.v2.timbral_pull = _numOr(tpInput.value, 0.25);
  });

  // Export interpreter audio → output/ dir on disk
  const exportWavBtn = document.getElementById('interp-export-wav-btn-top');
  const saveStatus = document.getElementById('interp-save-status');
  const setSaveStatus = (msg) => { if (saveStatus) saveStatus.textContent = msg; };
  if (exportWavBtn) exportWavBtn.addEventListener('click', async () => {
    if (!interpState.scorePath) { setSaveStatus('load a score first'); return; }
    const audioPath = (document.getElementById('interp-audio-path')?.value.trim()) || state.filePath;
    if (!audioPath) { setSaveStatus('load audio first'); return; }
    const nameVal = (document.getElementById('interp-name')?.value.trim()) || 'untitled_interp';
    const dur = state.duration || interpState.scoreDuration || 0;
    const durStr = dur > 0 ? dur.toFixed(1) : '?';

    // Show export options popup
    const html = `
      <div style="display:flex;flex-direction:column;gap:8px;">
        <div>
          <label style="font-size:11px;color:#888;">What to export:</label>
          <select id="exp-mode" style="width:100%;margin-top:3px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;">
            <option value="interp" selected>Interpreter (base + events + golem)</option>
            <option value="score_only">Score only (events + golem, no base)</option>
            <option value="raw">Raw base (no events, no golem)</option>
          </select>
        </div>
        <div>
          <label style="font-size:11px;color:#888;">Save to:</label>
          <div style="display:flex;gap:4px;margin-top:3px;">
            <input id="exp-path" type="text" value="" placeholder="click Browse to choose…" readonly
                   style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;cursor:pointer;" />
            <button id="exp-browse-btn" style="padding:4px 8px;font-size:11px;">Browse</button>
          </div>
        </div>
        <div>
          <label style="font-size:11px;color:#888;">Time range (seconds):</label>
          <div style="display:flex;gap:6px;margin-top:3px;">
            <input id="exp-from" type="number" value="0" min="0" step="0.1" placeholder="from"
                   style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
            <span style="color:#555;align-self:center;">→</span>
            <input id="exp-to" type="number" value="${durStr}" min="0" step="0.1" placeholder="to"
                   style="flex:1;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;" />
          </div>
          <div style="font-size:9px;color:#555;margin-top:2px;">Full duration: ${durStr}s. Leave as-is for whole audio.</div>
        </div>
${loudnessOptionsHtml('exp-loud')}
        <div>
          <label style="font-size:11px;color:#888;">Audio quality:</label>
          <select id="exp-format" style="width:100%;margin-top:3px;background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;">
            <option value="wav24" selected>24-bit WAV (studio standard)</option>
            <option value="wav32f">32-bit float WAV (lossless)</option>
            <option value="flac">FLAC (lossless, smaller file)</option>
            <option value="wav16">16-bit WAV (CD quality)</option>
          </select>
        </div>
      </div>`;
    // showPopup renders the HTML into the DOM, then returns a promise.
    // We need to wire the Browse button BEFORE awaiting, so use a microtask.
    const popupPromise = showPopup('Export WAV — ' + escapeHtml(nameVal), html);

    // Wire browse button inside the popup (now in DOM)
    requestAnimationFrame(() => {
      const browseBtn = document.getElementById('exp-browse-btn');
      const pathInput = document.getElementById('exp-path');
      if (browseBtn && pathInput) {
        browseBtn.addEventListener('click', () => {
          const selFmt = document.getElementById('exp-format')?.value || 'wav24';
          const fmtExt = selFmt === 'flac' ? '.flac' : '.wav';
          openSaveBrowser((fullPath) => {
            pathInput.value = fullPath;
          }, nameVal + fmtExt, ['.wav', '.flac']);
        });
      }
    });

    const ok = await popupPromise;
    if (!ok) return;

    const expMode   = document.getElementById('exp-mode')?.value || 'interp';
    const expFrom   = parseFloat(document.getElementById('exp-from')?.value) || 0;
    const expTo     = parseFloat(document.getElementById('exp-to')?.value)   || 0;
    const expPath   = document.getElementById('exp-path')?.value.trim() || '';
    const expFormat = document.getElementById('exp-format')?.value || 'wav24';
    const expLoud   = readLoudnessOptions('exp-loud');

    exportWavBtn.disabled = true;
    setSaveStatus('rendering WAV…');
    try {
      _syncInterpConfigFromUI();
      const body = {
        path: audioPath,
        score_path: interpState.scorePath,
        out_name: nameVal,
        out_path: expPath,   // full path chosen by user (empty = default output/ dir)
        export_mode: expMode,
        audio_format: expFormat,
        loudness: expLoud,
        time_from: expFrom,
        // The whole piece unless a part was chosen: the source's duration as
        // the end would cut the reverb tail and any stretched ending
        time_to: (expFrom === 0 && Math.abs(expTo - dur) < 0.05) ? 0 : (expTo > expFrom ? expTo : 0),
        interp: { golems: interpState.golems, v2config: interpState.v2config, mix_dims: interpState.mix_dims },
      };
      const res  = await fetch('/export_interp_wav', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (data.error) { setSaveStatus('export error: ' + data.error); return; }
      setSaveStatus('saved → ' + data.path + (data.loudness ? '  (' + describeLoudness(data.loudness) + ')' : ''));
      setTimeout(() => setSaveStatus(''), 10000);
    } catch (e) {
      setSaveStatus('export failed: ' + e);
    } finally {
      exportWavBtn.disabled = false;
    }
  });
  const scorePathInput = document.getElementById('interp-score-path');
  if (scorePathInput) scorePathInput.addEventListener('keydown', e => { if (e.key === 'Enter') _loadInterpScore(); });

  // Load audio wave — set #path-input so loadFile() (editor.js) can read it
  const loadWaveBtn = document.getElementById('interp-load-wave-btn');
  if (loadWaveBtn) loadWaveBtn.addEventListener('click', async () => {
    const path = document.getElementById('interp-audio-path').value.trim();
    if (!path) return;
    const composerInput = document.getElementById('path-input');
    if (composerInput) composerInput.value = path;
    await loadFile();
    if (!interpState.scoreDuration) interpState.scoreDuration = state.duration;
    if (typeof draw === 'function') draw();
  });

  // Load score image
  const loadScoreImgBtn = document.getElementById('interp-load-score-img-btn');
  if (loadScoreImgBtn) loadScoreImgBtn.addEventListener('click', () => {
    const path = document.getElementById('interp-score-img-path').value.trim();
    if (path) _loadImageIntoView(path, 'score');
  });

  // Load metadata image
  const loadMetaImgBtn = document.getElementById('interp-load-meta-img-btn');
  if (loadMetaImgBtn) loadMetaImgBtn.addEventListener('click', () => {
    const path = document.getElementById('interp-meta-img-path').value.trim();
    if (path) _loadImageIntoView(path, 'meta');
  });

  // Save / Load
  const saveBtn = document.getElementById('interp-save-btn');
  if (saveBtn) saveBtn.addEventListener('click', saveInterp);
  const loadBtn = document.getElementById('interp-load-btn');
  if (loadBtn) loadBtn.addEventListener('click', loadInterp);

  // Workspace activation: resize + redraw all canvases once layout settles
  document.addEventListener('workspace:activated', e => {
    if (e.detail !== 'interpreter') return;
    if (!interpState.scoreDuration && state.duration) interpState.scoreDuration = state.duration;
    // Wait for flex layout to settle, then force canvas resizes
    const redraw = () => {
      if (typeof resizeCanvas === 'function') resizeCanvas();
      if (typeof drawGolemTimeline === 'function') drawGolemTimeline();
      if (_lastTraceData && typeof drawKalmanTrace === 'function') drawKalmanTrace(_lastTraceData);
      if (typeof draw === 'function') draw();
    };
    requestAnimationFrame(() => requestAnimationFrame(redraw));
    // Safety net: redraw again after 100ms in case first reflow wasn't enough
    setTimeout(redraw, 100);
  });

  // Also wire window.resize to redraw golem timeline + kalman trace
  window.addEventListener('resize', () => {
    if (typeof drawGolemTimeline === 'function') drawGolemTimeline();
    if (_lastTraceData && typeof drawKalmanTrace === 'function') drawKalmanTrace(_lastTraceData);
  });

  // Initial render
  _renderGolemCards();
  _refreshPresets('kalman');
  drawGolemTimeline();
  loadCustomChars();
});


// The golem's stereo width only acts on stereo audio: say so when the loaded
// audio is mono (the checkbox still works, so a score can carry the setting).
function _syncWidthDimHint() {
  const lab = document.getElementById("mixdim-width-label");
  if (!lab) return;
  const mono = (state.channels || 1) < 2 && !(state.tracks || []).some(t => (t.channels || 1) > 1);
  lab.style.opacity = mono ? "0.45" : "1";
  lab.title = mono
    ? "Stereo width — no effect here: the loaded audio is mono"
    : "Stereo width from the golem (0 mono, 0.5 as recorded, 1 twice as wide)";
}
document.addEventListener("DOMContentLoaded", _syncWidthDimHint);


// Global Settings and the trace step are undoable and re-render while
// playing. The snapshot is taken first, then the new values are copied into
// v2config, so v2config always holds what the inputs showed before an edit.
document.addEventListener('DOMContentLoaded', () => {
  const g = document.getElementById('ge-global-body');
  if (g) g.addEventListener('change', () => { pushHistory(); _syncGlobalSettings(); });
  const step = document.getElementById('interp-trace-step');
  if (step) step.addEventListener('change', () => {
    pushHistory();
    if (!interpState.v2config.v2) interpState.v2config.v2 = {};
    interpState.v2config.v2.trace_step = parseFloat(step.value) || 0;
  });
});
