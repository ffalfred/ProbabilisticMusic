// ─── Tool state ───────────────────────────────────────────────────────────────
let activeTool = "sample";
let scoreMarkerDrag = null; // "start" | "end" | null — dragging a score alignment marker
document.querySelectorAll("[data-tool]").forEach(btn => {
  btn.addEventListener("click", () => {
    activeTool = btn.dataset.tool;
    document.querySelectorAll("[data-tool]").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    frameCanvas.style.cursor =
      activeTool === "zoom" ? "zoom-in" :
      activeTool === "pointer" ? "default" : "crosshair";
  });
});

// ─── Load ────────────────────────────────────────────────────────────────────
document.getElementById("load-btn").addEventListener("click", loadFile);
document.getElementById("path-input").addEventListener("keydown", e => {
  if (e.key === "Enter") loadFile();
});

async function loadFile() {
  const path = document.getElementById("path-input").value.trim();
  if (!path) return;
  document.getElementById("load-btn").textContent = "Loading…";
  try {
    // Stop any Web Audio stems from the previous file
    _waStop();
    Object.keys(_waCache).forEach(k => delete _waCache[k]);
    const res = await fetch("/load", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path})
    });
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    state.waveform = data.waveform;
    state.duration = data.duration;
    state.currentTime = 0;
    state.filePath = path;
    state.tracks = [{ name: "base", path, gain_db: 0, muted: false, waveform: data.waveform }];
    renderTracksPanel();
    resetFZ();
    waveView.zoom = 1; waveView.scrollT = 0;
    scoreView.end = data.duration;
    score2View.end = data.duration;
    document.getElementById("score2-end-input").value = data.duration.toFixed(3);
    document.getElementById("score-end-input").value = data.duration.toFixed(3);
    document.getElementById("dur-display").textContent = data.duration.toFixed(3);
    const ph = document.getElementById("frame-placeholder");
    // Always wire base audio for playback (vid is muted — display only)
    baseAudio.src = "/video?path=" + encodeURIComponent(path);
    if (data.frame) {
      vid.src = "/video?path=" + encodeURIComponent(path);
      vid.style.display = "none";   // shown only in video mode via loadedmetadata
      ph.style.display = "block";
      ph.textContent = "loading…";
      vid.load();
    } else {
      vid.src = "";
      vid.style.display = "none";
      ph.style.display = "none";
    }
    draw();
  } catch(e) {
    alert("Load failed: " + e);
  } finally {
    document.getElementById("load-btn").textContent = "Load";
  }
}

// ─── Drag state ───────────────────────────────────────────────────────────────
const dragState = { active: false, startX: 0, curX: 0, startT: 0, curT: 0, canvas: null };
let mouseIsDown = false;
let panStart = null;
let score2Pan = null; // {mx, panOffset} — pan-drag state

// ─── score2 wiring ─────────────────────────────────────────────────────────────

// Toggle second panel
document.getElementById("toggle-score2-btn").addEventListener("click", () => {
  const cont = document.getElementById("score2-container");
  const vis = cont.classList.toggle("visible");
  document.getElementById("toggle-score2-btn").classList.toggle("active", vis);
  if (vis) { setTimeout(() => { resizeScore2Canvas(); draw(); }, 10); } else { draw(); }
});

// Load second image
document.getElementById("load-score2-btn").addEventListener("click", () => {
  const path = document.getElementById("score2-path-input").value.trim();
  if (!path) return;
  const img = new Image();
  img.src = "/image?path=" + encodeURIComponent(path);
  img.onload = () => {
    score2View.img = img; score2View.path = path;
    score2View.start = parseFloat(document.getElementById("score2-start-input").value) || 0;
    score2View.end   = parseFloat(document.getElementById("score2-end-input").value)   || state.duration;
    score2View.panOffset = 0;
    const cont = document.getElementById("score2-container");
    if (!cont.classList.contains("visible")) {
      cont.classList.add("visible");
      document.getElementById("toggle-score2-btn").classList.add("active");
      setTimeout(() => { resizeScore2Canvas(); draw(); }, 10);
    } else { resizeScore2Canvas(); draw(); }
  };
  img.onerror = () => alert("Could not load second image: " + path);
});

document.getElementById("score2-start-input").addEventListener("input", () => {
  score2View.start = parseFloat(document.getElementById("score2-start-input").value) || 0; draw();
});
document.getElementById("score2-end-input").addEventListener("input", () => {
  const v = parseFloat(document.getElementById("score2-end-input").value);
  score2View.end = (v && v > score2View.start) ? v : state.duration; draw();
});
document.getElementById("reset-score2-btn").addEventListener("click", () => {
  score2View.scale = 1; score2View.panOffset = 0; draw();
});

// score2Canvas mouse handlers — same tools as frame canvas, using score2View coords
score2Canvas.addEventListener("mousemove", e => {
  if (score2Pan) {
    score2View.panOffset = score2Pan.panOffset + (e.clientX - score2Pan.mx);
    draw(); return;
  }
  if (!state.duration) return;
  const r = score2Canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToTFor(x, score2Canvas, score2View);
  if (dragState.active && dragState.canvas === score2Canvas) {
    dragState.curT = t; draw();
  }
});

score2Canvas.addEventListener("mousedown", e => {
  mouseIsDown = true;
  if (activeTool === "zoom" || activeTool === "pointer") {
    score2Pan = { mx: e.clientX, panOffset: score2View.panOffset };
    score2Canvas.style.cursor = "grabbing"; return;
  }
  if (!state.duration) return;
  const r = score2Canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToTFor(x, score2Canvas, score2View);
  if (activeTool === "sample" || activeTool === "dynamics" || activeTool === "tempo" || activeTool === "fx" || activeTool === "phrase" || activeTool === "glissando" || activeTool === "legato") {
    dragState.active = true; dragState.canvas = score2Canvas;
    dragState.startT = t; dragState.curT = t;
    dragState.startX = (x / score2Canvas.width) * canvas.width;
    dragState.curX   = dragState.startX;
  }
});

score2Canvas.addEventListener("mouseup", e => {
  mouseIsDown = false;
  if (score2Pan) {
    score2Pan = null;
    score2Canvas.style.cursor = activeTool === "zoom" ? "zoom-in" : activeTool === "pointer" ? "default" : "crosshair";
    return;
  }
  if (!state.duration) return;
  const r = score2Canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToTFor(x, score2Canvas, score2View);
  if (dragState.active && dragState.canvas === score2Canvas) {
    dragState.active = false;
    const t1 = Math.min(dragState.startT, t), t2 = Math.max(dragState.startT, t);
    const px = Math.abs(x - (dragState.startX / canvas.width) * score2Canvas.width);
    if (px >= 5) {
      if (activeTool === "sample")        openSamplePopup(t1, t2);
      else if (activeTool === "dynamics") openRangePopup(t1, t2);
      else if (activeTool === "tempo")    openTempoPopup(t1, t2);
      else if (activeTool === "fx")       openFxZonePopup(t1, t2);
      else if (activeTool === "phrase")   openPhrasePopup(t1, t2);
      else if (activeTool === "glissando") openNoteRelPopup("glissando", t1, t2);
      else if (activeTool === "legato")    openArticulationPopup("legato", t1, t2);
    } else {
      if (activeTool === "dynamics") openMarkPopup(t);
      else if (activeTool === "arpchord")  openNoteRelPopup("arpeggiate", t, t);
      else if (activeTool === "staccato") openArticulationPopup("staccato", t);
      else if (activeTool === "fermata")  openArticulationPopup("fermata", t);
      else if (activeTool === "accent")   openArticulationPopup("accent", t);
      else seekTo(t);
    }
  } else if (activeTool === "event") {
    openEventPopup(t);
  } else if (activeTool === "dynamics") {
    openMarkPopup(t);
  } else if (activeTool === "arpchord") {
    openNoteRelPopup("arpeggiate", t, t);
  } else if (activeTool === "staccato") {
    openArticulationPopup("staccato", t);
  } else if (activeTool === "fermata") {
    openArticulationPopup("fermata", t);
  } else if (activeTool === "accent") {
    openArticulationPopup("accent", t);
  } else {
    seekTo(t);
  }
  draw();
});

score2Canvas.addEventListener("mouseleave", () => {
  mouseIsDown = false; score2Pan = null;
  if (dragState.canvas === score2Canvas && dragState.active) { dragState.active = false; draw(); }
});

// Scroll to zoom score2
score2Canvas.addEventListener("wheel", e => {
  if (!score2View.img) return;
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  score2View.scale = Math.max(0.1, Math.min(20, score2View.scale * factor));
  draw();
}, { passive: false });

// Double-click to reset score2 zoom/pan
score2Canvas.addEventListener("dblclick", () => {
  score2View.scale = 1; score2View.panOffset = 0; draw();
});

// Resize observer
new ResizeObserver(() => {
  if (document.getElementById("score2-container").classList.contains("visible")) {
    resizeScore2Canvas();
  }
}).observe(document.getElementById("score2-container"));

// Score image load button
document.getElementById("load-score-btn").addEventListener("click", () => {
  const path = document.getElementById("score-path-input").value.trim();
  if (!path) return;
  const img = new Image();
  img.src = "/image?path=" + encodeURIComponent(path);
  img.onload = () => {
    scoreView.img = img;
    scoreView.path = path;
    scoreView.start = parseFloat(document.getElementById("score-start-input").value) || 0;
    scoreView.end   = parseFloat(document.getElementById("score-end-input").value)   || state.duration;
    scoreView.panOffset = 0;
    draw();
  };
  img.onerror = () => alert("Could not load score image: " + path);
});
document.getElementById("score-start-input").addEventListener("input", () => {
  scoreView.start = parseFloat(document.getElementById("score-start-input").value) || 0;
  draw();
});
document.getElementById("score-end-input").addEventListener("input", () => {
  const v = parseFloat(document.getElementById("score-end-input").value);
  scoreView.end = (v && v > scoreView.start) ? v : state.duration;
  draw();
});

// View toggle
document.getElementById("view-toggle-btn").addEventListener("click", () => {
  viewMode = viewMode === "score" ? "video" : "score";
  document.getElementById("view-toggle-btn").textContent =
    viewMode === "score" ? "[ Score ]" : "[ Video ]";
  if (viewMode === "video") {
    // restore CSS zoom transform on #frame-inner
    applyFZ();
    vid.style.display = vid.src ? "block" : "none";
  } else {
    // score mode: reset CSS transform, canvas draws the image
    document.getElementById("frame-inner").style.transform = "";
    vid.style.display = "none";
  }
  draw();
});

// Export MP4
document.getElementById("export-mp4-btn").addEventListener("click", async () => {
  if (!scoreView.path) { alert("Load a score image first."); return; }
  if (!state.filePath) { alert("Load an audio file first."); return; }
  const btn = document.getElementById("export-mp4-btn");
  btn.textContent = "⏳ rendering…"; btn.disabled = true;
  try {
    const res = await fetch("/export_mp4", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        audioPath: state.filePath,
        imagePath: scoreView.path,
        scoreStart: scoreView.start,
        scoreEnd: scoreView.end,
        name: document.getElementById("score-name").value.trim() || "score_video",
      })
    });
    const data = await res.json();
    if (data.error) { alert("MP4 error: " + data.error); }
    else { document.getElementById("export-status").textContent = "MP4 → " + data.path; }
  } catch(e) { alert("MP4 failed: " + e); }
  finally { btn.textContent = "▶ MP4"; btn.disabled = false; }
});

vid.addEventListener("loadedmetadata", () => {
  // Only show video element when in video mode; score mode uses the canvas
  if (viewMode === "video") vid.style.display = "block";
  document.getElementById("frame-placeholder").style.display = "none";
  if (state.duration > 0) vid.currentTime = state.currentTime;
  draw();
});

// ─── Waveform canvas interaction ─────────────────────────────────────────────
canvas.addEventListener("mousemove", e => {
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToT(x);

  // Score marker drag (score1 and score2)
  if (scoreMarkerDrag) {
    const clampedT = Math.max(0, Math.min(state.duration, t));
    if (scoreMarkerDrag === "start") {
      scoreView.start = Math.min(clampedT, scoreView.end - 0.1);
      document.getElementById("score-start-input").value = scoreView.start.toFixed(3);
    } else if (scoreMarkerDrag === "end") {
      scoreView.end = Math.max(clampedT, scoreView.start + 0.1);
      document.getElementById("score-end-input").value = scoreView.end.toFixed(3);
    } else if (scoreMarkerDrag === "start2") {
      score2View.start = Math.min(clampedT, score2View.end - 0.1);
      document.getElementById("score2-start-input").value = score2View.start.toFixed(3);
    } else if (scoreMarkerDrag === "end2") {
      score2View.end = Math.max(clampedT, score2View.start + 0.1);
      document.getElementById("score2-end-input").value = score2View.end.toFixed(3);
    }
    draw();
    return;
  }

  // Cursor hint near score markers
  {
    let nearMarker = false;
    if (scoreView.img && state.duration > 0) {
      const sx = tToX(scoreView.start);
      const ex = tToX(scoreView.end);
      if (Math.abs(x - sx) <= 7 || Math.abs(x - ex) <= 7) nearMarker = true;
    }
    const s2Vis = document.getElementById("score2-container").classList.contains("visible");
    if (!nearMarker && s2Vis && score2View.img && state.duration > 0) {
      const sx2 = tToX(score2View.start);
      const ex2 = tToX(score2View.end);
      if (Math.abs(x - sx2) <= 7 || Math.abs(x - ex2) <= 7) nearMarker = true;
    }
    canvas.style.cursor = nearMarker ? "col-resize" : "";
  }

  if (dragState.active) {
    dragState.curX = x; dragState.curT = t;
    draw();
  }
  if (mouseIsDown && !dragState.active) {
    const pl = activeBasePlayer();
    if (pl && pl.src && pl.readyState >= 1 && pl.paused) pl.currentTime = t;
    if (vid.src && vid.readyState >= 1 && vid.paused) vid.currentTime = t;
    state.currentTime = t;
    draw();
  }
});

canvas.addEventListener("mousedown", e => {
  mouseIsDown = true;
  if (!state.duration) return;
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToT(x);

  // Score marker drag
  if (scoreView.img && state.duration > 0) {
    const sx = tToX(scoreView.start);
    const ex = tToX(scoreView.end);
    if (Math.abs(x - sx) <= 7) { scoreMarkerDrag = "start"; return; }
    if (Math.abs(x - ex) <= 7) { scoreMarkerDrag = "end";   return; }
  }
  const s2Vis = document.getElementById("score2-container").classList.contains("visible");
  if (s2Vis && score2View.img && state.duration > 0) {
    const sx2 = tToX(score2View.start);
    const ex2 = tToX(score2View.end);
    if (Math.abs(x - sx2) <= 7) { scoreMarkerDrag = "start2"; return; }
    if (Math.abs(x - ex2) <= 7) { scoreMarkerDrag = "end2";   return; }
  }

  if (activeTool === "sample" || activeTool === "dynamics" || activeTool === "tempo" || activeTool === "fx" || activeTool === "phrase" || activeTool === "glissando" || activeTool === "legato") {
    dragState.active = true; dragState.canvas = canvas;
    dragState.startX = x; dragState.curX = x;
    dragState.startT = t; dragState.curT = t;
  }
});

canvas.addEventListener("mouseup", e => {
  mouseIsDown = false;
  if (scoreMarkerDrag) { scoreMarkerDrag = null; canvas.style.cursor = ""; return; }
  if (!state.duration) return;
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToT(x);

  if (dragState.active) {
    dragState.active = false;
    const t1 = Math.min(dragState.startT, t);
    const t2 = Math.max(dragState.startT, t);
    const dist = Math.abs(x - dragState.startX);

    if (dist < 5) {
      if (activeTool === "dynamics") openMarkPopup(t);
      else if (activeTool === "arpchord")  openNoteRelPopup("arpeggiate", t, t);
      else if (activeTool === "staccato") openArticulationPopup("staccato", t);
      else if (activeTool === "fermata")  openArticulationPopup("fermata", t);
      else if (activeTool === "accent")   openArticulationPopup("accent", t);
      else seekTo(t);
    } else {
      if (activeTool === "sample")         openSamplePopup(t1, t2);
      else if (activeTool === "dynamics")  openRangePopup(t1, t2);
      else if (activeTool === "tempo")     openTempoPopup(t1, t2);
      else if (activeTool === "fx")        openFxZonePopup(t1, t2);
      else if (activeTool === "phrase")    openPhrasePopup(t1, t2);
      else if (activeTool === "glissando") openNoteRelPopup("glissando", t1, t2);
      else if (activeTool === "legato")    openArticulationPopup("legato", t1, t2);
    }
  } else if (activeTool === "event") {
    openEventPopup(t);
  } else if (activeTool === "dynamics") {
    openMarkPopup(t);
  } else if (activeTool === "arpchord") {
    openNoteRelPopup("arpeggiate", t, t);
  } else if (activeTool === "staccato") {
    openArticulationPopup("staccato", t);
  } else if (activeTool === "fermata") {
    openArticulationPopup("fermata", t);
  } else if (activeTool === "accent") {
    openArticulationPopup("accent", t);
  } else {
    seekTo(t);
  }
  draw();
});

canvas.addEventListener("mouseleave", () => {
  mouseIsDown = false;
  scoreMarkerDrag = null;
  canvas.style.cursor = "";
  if (dragState.active) { dragState.active = false; draw(); }
});

// Waveform timeline zoom (scroll wheel)
canvas.addEventListener("wheel", e => {
  if (!state.duration) return;
  e.preventDefault();
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const tAtCursor = xToT(x);
  const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
  waveView.zoom = Math.max(1, Math.min(100, waveView.zoom * factor));
  const vis = waveVisible();
  waveView.scrollT = tAtCursor - (x / canvas.width) * vis;
  waveView.scrollT = Math.max(0, Math.min(state.duration - vis, waveView.scrollT));
  draw();
}, { passive: false });

// ─── Frame canvas interaction (same tools, different canvas) ──────────────────
function xToTF(x) {
  if (!state.duration) return 0;
  if (viewMode === "score") {
    const displayX = x + scoreScrollLeft();
    const dur = scoreView.end - scoreView.start;
    return Math.max(0, Math.min(state.duration,
      scoreView.start + (displayX / scoreDisplayWidth()) * dur));
  }
  return Math.max(0, Math.min(state.duration, (x / frameCanvas.width) * state.duration));
}

frameCanvas.addEventListener("mousemove", e => {
  if (panStart) {
    if (viewMode === "score") {
      scoreView.panOffset = panStart.panOffset + (e.clientX - panStart.mx);
    } else {
      fz.tx = panStart.tx + (e.clientX - panStart.mx);
      fz.ty = panStart.ty + (e.clientY - panStart.my);
      clampFZ();
      applyFZ();
    }
    draw();
    return;
  }
  const x = frameMouseX(e);
  const t = xToTF(x);
  if (dragState.active) {
    dragState.curX = (x / frameCanvas.width) * canvas.width;
    dragState.curT = t;
    draw();
  }
  if (mouseIsDown && !dragState.active) {
    const pl = activeBasePlayer();
    if (pl && pl.src && pl.readyState >= 1 && pl.paused) pl.currentTime = t;
    if (vid.src && vid.readyState >= 1 && vid.paused) vid.currentTime = t;
    state.currentTime = t;
    draw();
  }
});

frameCanvas.addEventListener("mousedown", e => {
  mouseIsDown = true;
  if (activeTool === "zoom" || activeTool === "pointer") {
    panStart = { mx: e.clientX, my: e.clientY, tx: fz.tx, ty: fz.ty, panOffset: scoreView.panOffset };
    frameCanvas.style.cursor = "grabbing";
    return;
  }
  if (!state.duration) return;
  const x = frameMouseX(e);
  const t = xToTF(x);
  if (activeTool === "sample" || activeTool === "dynamics" || activeTool === "tempo" || activeTool === "fx" || activeTool === "phrase" || activeTool === "glissando" || activeTool === "legato") {
    dragState.active = true; dragState.canvas = frameCanvas;
    dragState.startX = (x / frameCanvas.width) * canvas.width;
    dragState.curX   = dragState.startX;
    dragState.startT = t; dragState.curT = t;
  }
});

frameCanvas.addEventListener("mouseup", e => {
  mouseIsDown = false;
  if (panStart) {
    panStart = null;
    frameCanvas.style.cursor = activeTool === "zoom" ? "zoom-in" : activeTool === "pointer" ? "default" : "crosshair";
    return;
  }
  if (!state.duration) return;
  const x = frameMouseX(e);
  const t = xToTF(x);
  if (dragState.active) {
    dragState.active = false;
    const t1 = Math.min(dragState.startT, t);
    const t2 = Math.max(dragState.startT, t);
    const waveX = (x / frameCanvas.width) * canvas.width;
    const dist = Math.abs(waveX - dragState.startX);
    if (dist >= 5) {
      if (activeTool === "sample")         openSamplePopup(t1, t2);
      else if (activeTool === "dynamics")  openRangePopup(t1, t2);
      else if (activeTool === "tempo")     openTempoPopup(t1, t2);
      else if (activeTool === "fx")        openFxZonePopup(t1, t2);
      else if (activeTool === "phrase")    openPhrasePopup(t1, t2);
      else if (activeTool === "glissando") openNoteRelPopup("glissando", t1, t2);
      else if (activeTool === "legato")    openArticulationPopup("legato", t1, t2);
    } else {
      if (activeTool === "dynamics")      openMarkPopup(t);
      else if (activeTool === "arpchord") openNoteRelPopup("arpeggiate", t, t);
      else if (activeTool === "staccato") openArticulationPopup("staccato", t);
      else if (activeTool === "fermata")  openArticulationPopup("fermata", t);
      else if (activeTool === "accent")   openArticulationPopup("accent", t);
      else seekTo(t);
    }
  } else if (activeTool === "event") {
    openEventPopup(t);
  } else if (activeTool === "dynamics") {
    openMarkPopup(t);
  } else if (activeTool === "arpchord") {
    openNoteRelPopup("arpeggiate", t, t);
  } else if (activeTool === "staccato") {
    openArticulationPopup("staccato", t);
  } else if (activeTool === "fermata") {
    openArticulationPopup("fermata", t);
  } else if (activeTool === "accent") {
    openArticulationPopup("accent", t);
  } else {
    seekTo(t);
  }
  draw();
});

frameCanvas.addEventListener("mouseleave", () => {
  mouseIsDown = false;
  panStart = null;
  if (dragState.active) { dragState.active = false; draw(); }
});

frameCanvas.addEventListener("wheel", e => {
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  if (viewMode === "score") {
    if (!scoreView.img) return;
    e.preventDefault();
    scoreView.scale = Math.max(0.2, Math.min(10, scoreView.scale * factor));
    draw();
  } else {
    if (activeTool !== "zoom") return;
    e.preventDefault();
    const r = document.getElementById("frame-container").getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const newScale = Math.max(1, Math.min(10, fz.scale * factor));
    fz.tx = mx - (mx - fz.tx) * (newScale / fz.scale);
    fz.ty = my - (my - fz.ty) * (newScale / fz.scale);
    fz.scale = newScale;
    clampFZ();
    applyFZ();
  }
}, { passive: false });

frameCanvas.addEventListener("dblclick", () => {
  if (activeTool === "zoom" || activeTool === "pointer") {
    if (viewMode === "score") {
      scoreView.scale = 1; scoreView.panOffset = 0; draw();
    } else {
      resetFZ();
    }
  }
});

frameCanvas.addEventListener("contextmenu", e => {
  e.preventDefault();
  const x = frameMouseX(e);
  const waveX = (x / frameCanvas.width) * canvas.width;
  const cr = canvas.getBoundingClientRect();
  canvas.dispatchEvent(new MouseEvent("contextmenu", {
    clientX: cr.left + waveX,
    clientY: cr.top + canvas.height / 2,
    bubbles: true, cancelable: true
  }));
});

// ─── Track lanes ──────────────────────────────────────────────────────────────
function drawMiniWaveform(cvs, peaks) {
  // Sync pixel buffer to display size to avoid blurriness
  if (cvs.offsetWidth > 0) cvs.width = cvs.offsetWidth;
  const ctx = cvs.getContext("2d");
  const W = cvs.width, H = cvs.height, mid = H / 2;
  ctx.clearRect(0, 0, W, H);
  if (!peaks || !peaks.length) return;
  ctx.strokeStyle = "#4a9eff";
  ctx.lineWidth = 1;
  ctx.beginPath();
  peaks.forEach((v, i) => {
    const x = i / peaks.length * W;
    ctx.moveTo(x, mid - v * mid);
    ctx.lineTo(x, mid + v * mid);
  });
  ctx.stroke();
  // Playback cursor
  if (state.duration > 0) {
    const cx = (state.currentTime / state.duration) * W;
    ctx.strokeStyle = "rgba(255,50,50,0.85)";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.beginPath(); ctx.moveTo(cx, 0); ctx.lineTo(cx, H); ctx.stroke();
  }
}


let tracksOpen = true;

function toggleTracksPanel() {
  tracksOpen = !tracksOpen;
  document.getElementById("tracks-panel").style.display = tracksOpen ? "" : "none";
  document.getElementById("tracks-chevron").textContent = tracksOpen ? "\u25bc" : "\u25b6";
}

function renderTracksPanel() {
  const panel = document.getElementById("tracks-panel");
  if (!panel) return;
  const wrap = document.getElementById("tracks-wrap");
  if (state.tracks.length <= 1) { panel.innerHTML = ""; if (wrap) wrap.style.display = "none"; return; }
  if (wrap) wrap.style.display = "";
  document.getElementById("tracks-title").textContent = `Tracks (${state.tracks.length})`;
  panel.innerHTML = state.tracks.map((tk, i) => `
    <div style="display:flex;align-items:center;gap:5px;margin-bottom:2px;padding:2px 4px;background:#161616;border-radius:3px;">
      <span style="width:90px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#aaa;" title="${tk.name}">${i}: ${tk.name}</span>
      <input type="checkbox" ${tk.muted ? "" : "checked"} title="mute/unmute"
             onchange="state.tracks[${i}].muted=!this.checked; syncSourcePlayback(); renderTracksPanel();">
      <label style="font-size:10px;color:#666;">dB</label>
      <input type="number" value="${tk.gain_db}" step="1" style="width:44px;font-size:11px;background:#111;color:#ccc;border:1px solid #333;padding:1px 3px;"
             onchange="state.tracks[${i}].gain_db=parseFloat(this.value)||0;">
      <canvas data-tidx="${i}" width="300" height="26" style="flex:1;background:#1a1a1a;"></canvas>
    </div>`).join('');
  panel.querySelectorAll("canvas[data-tidx]").forEach(c => {
    const idx = parseInt(c.dataset.tidx);
    drawMiniWaveform(c, state.tracks[idx].waveform);
  });
}

// ─── Separate ────────────────────────────────────────────────────────────────
document.getElementById("separate-btn").addEventListener("click", async () => {
  if (!state.tracks.length || !state.tracks[0].path) { alert("Load an audio file first."); return; }
  const html = row("method", `<select id="p-sep-method">
      <option value="hpss">Harmonic / Percussive (HPSS)</option>
      <option value="nmf">NMF components</option>
      <option value="both">Both (HPSS + NMF)</option>
    </select>`)
    + row("NMF components", `<input id="p-sep-n" type="number" value="3" min="2" max="8" step="1" style="width:60px;">`)
    + row("NMF reconstruction", `<select id="p-sep-nmf-mode">
      <option value="softmask">Soft mask (stems sum to original)</option>
      <option value="naive">Naive (raw components, quieter)</option>
    </select>`);
  const ok = await showPopup("&#9881; Separate audio", html);
  if (!ok) return;
  const method   = document.getElementById("p-sep-method").value;
  const n        = parseInt(document.getElementById("p-sep-n").value) || 3;
  const nmf_mode = document.getElementById("p-sep-nmf-mode").value;
  const btn    = document.getElementById("separate-btn");
  const status = document.getElementById("export-status");
  btn.textContent = "⏳…"; btn.disabled = true;
  status.textContent = "separating…";
  try {
    const r = await fetch("/separate", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path: state.tracks[0].path, method, n_components: n, nmf_mode })
    });
    const data = await r.json();
    if (data.error) { status.textContent = "error: " + data.error; return; }
    // Stop HTML audio — Web Audio mixer takes over from here
    baseAudio.pause();
    vid.pause();
    // Remove any previously added stems (keep only track 0 = the source)
    state.tracks.splice(1);
    // Clear Web Audio buffer cache so stale stems aren't replayed
    Object.keys(_waCache).forEach(k => delete _waCache[k]);
    for (const stem of data.stems) {
      const wr = await fetch("/load", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ path: stem.path })
      });
      const wd = await wr.json();
      state.tracks.push({ name: stem.name, path: stem.path,
                          gain_db: 0, muted: false, waveform: wd.waveform || [] });
    }
    // Reset cached source so toggleBase picks a fresh track next play
    currentSourcePath = null;
    renderTracksPanel();
    status.textContent = `${data.stems.length} stems added as tracks`;
  } catch(e) {
    status.textContent = "separate failed: " + e;
  } finally {
    btn.textContent = "⚙ Stemize"; btn.disabled = false;
  }
});

// ─── Quantize ────────────────────────────────────────────────────────────────
document.getElementById("quantize-btn").addEventListener("click", async () => {
  if (!state.events.length) { alert("No events to quantize.\n\nEvents are time-placed notes created with the \u25ba Event tool (click on the waveform). Samples define audio clips but are not quantized — only placed events are snapped to the grid."); return; }
  const html =
      row("BPM", `<input id="q-bpm"   type="number" value="120" min="1" step="0.5" style="width:70px;">`)
    + row("subdivision", `<select id="q-sub">
        <option value="1">1/4 (quarter note)</option>
        <option value="2" selected>1/8 (eighth note)</option>
        <option value="4">1/16 (sixteenth note)</option>
        <option value="8">1/32 (thirty-second note)</option>
        <option value="0.5">1/2 (half note)</option>
      </select>`)
    + row("strength %", `<input id="q-str" type="number" value="100" min="0" max="100" step="5" style="width:60px;">`
        + `<span style="font-size:10px;color:#666;"> (100 = full snap, 50 = halfway)</span>`);
  const ok = await showPopup("Quantize events", html);
  if (!ok) return;

  try {
    const bpm      = parseFloat(document.getElementById("q-bpm").value)  || 120;
    const subdiv   = parseFloat(document.getElementById("q-sub").value)  || 2;
    const strength = (parseFloat(document.getElementById("q-str").value) || 100) / 100;

    // grid interval in seconds: one quarter note = 60/bpm, subdivide further
    const grid = (60 / bpm) / subdiv;

    pushHistory();
    state.events = state.events.map(ev => {
      const snapped = Math.round(ev.t / grid) * grid;
      return Object.assign({}, ev, { t: ev.t + (snapped - ev.t) * strength });
    });
    updateScoreInfo();
    draw();
  } catch(e) {
    alert("Quantize error: " + e);
  }
});

// ─── Export ───────────────────────────────────────────────────────────────────
document.getElementById("export-btn").addEventListener("click", async () => {
  const name = document.getElementById("score-name").value.trim() || "untitled";

  // Strip color from samples; keep fade_in/fade_out, track
  const samplesClean = {};
  for (const [k, v] of Object.entries(state.samples)) {
    samplesClean[k] = { from: v.from, to: v.to,
      fade_in: v.fade_in ?? 0.05, fade_out: v.fade_out ?? 0.05,
      ...(v.track ? { track: v.track } : {}) };
  }

  const score = {
    _name: name,
    samples: samplesClean,
    dynamics: state.dynamics,
    tempo: state.tempo,
    base_fx: state.baseFx,
    fx_ranges: state.fxRanges,
    events: state.events,
    phrases: state.phrases.map(p => ({
      from: p.from, to: p.to, label: p.label,
      gain_db: p.gain_db ?? 0, fade_in: p.fade_in ?? 0,
      fade_out: p.fade_out ?? 0, tempo_factor: p.tempo_factor ?? 1.0,
    })),
    ...(state.noteRel.length ? { note_rel: state.noteRel } : {}),
    ...(state.articulations.length ? { articulations: state.articulations } : {}),
    ...(state.tracks.length > 1 ? { tracks: state.tracks.map(tk => ({
      path: tk.path, name: tk.name, gain_db: tk.gain_db, muted: tk.muted
    })) } : {}),
    ...(scoreView.path ? {
      score_image: scoreView.path,
      score_start: scoreView.start,
      score_end:   scoreView.end,
    } : {}),
    ...(score2View.path ? {
      score2_image: score2View.path,
      score2_start: score2View.start,
      score2_end:   score2View.end,
    } : {}),
    ...(state.duckBase.enabled ? { duck_base: state.duckBase } : {}),
    ...(state.duckKey.enabled  ? { duck_key:  state.duckKey  } : {}),
    ...(state.autoMix.enabled  ? { auto_mix:  state.autoMix  } : {}),
  };
  const statusEl = document.getElementById("export-status");
  statusEl.textContent = "saving…";
  try {
    const res = await fetch("/export", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(Object.assign(score, { _config: state.v2config }))
    });
    const data = await res.json();
    statusEl.textContent = "saved → " + data.path;
    setTimeout(() => { statusEl.textContent = ""; }, 4000);
  } catch(e) {
    statusEl.textContent = "export failed: " + e;
  }
});

// ─── Import YAML ─────────────────────────────────────────────────────────────
document.getElementById("import-btn").addEventListener("click", async () => {
  const path = document.getElementById("import-path").value.trim();
  if (!path) { alert("Enter the path to a .yaml score file."); return; }
  const statusEl = document.getElementById("export-status");
  statusEl.textContent = "loading…";
  try {
    const res = await fetch("/load_yaml", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ path })
    });
    const data = await res.json();
    if (data.error) { alert("Import failed: " + data.error); statusEl.textContent = ""; return; }
    const sc = data.score;

    // Restore annotation state
    if (sc.samples)    state.samples  = sc.samples;
    if (sc.dynamics)   state.dynamics = sc.dynamics;
    if (sc.tempo)      state.tempo    = sc.tempo;
    if (sc.events)     state.events   = sc.events;
    if (sc.phrases)      state.phrases       = (sc.phrases || []).map(p => Object.assign({ gain_db: 0, fade_in: 0, fade_out: 0, tempo_factor: 1.0 }, p));
    if (sc.note_rel)     state.noteRel       = sc.note_rel;
    if (sc.articulations) state.articulations = sc.articulations;
    if (sc.base_fx)    state.baseFx   = sc.base_fx;
    if (sc.fx_ranges)  state.fxRanges = sc.fx_ranges;
    if (sc.duck_base)  Object.assign(state.duckBase, sc.duck_base);
    if (sc.duck_key)   Object.assign(state.duckKey,  sc.duck_key);
    if (sc.auto_mix)   Object.assign(state.autoMix,  sc.auto_mix);

    // Assign a color to imported samples that have none
    for (const k of Object.keys(state.samples)) {
      if (!state.samples[k].color) state.samples[k].color = nextColor();
    }

    // Restore score name
    const nameEl = document.getElementById("score-name");
    if (sc._name) nameEl.value = sc._name;
    else { const bn = path.split("/").pop().replace(/\.yaml$/i, ""); if (bn) nameEl.value = bn; }

    // Load audio if base_track present and no audio loaded yet
    if (sc.base_track && !state.filePath) {
      document.getElementById("path-input").value = sc.base_track;
      await loadFile();
    }

    // Load score image if present
    if (sc.score_image) {
      document.getElementById("score-path-input").value = sc.score_image;
      const sStart = sc.score_start ?? 0;
      const sEnd   = sc.score_end   ?? state.duration;
      document.getElementById("score-start-input").value = sStart.toFixed(3);
      document.getElementById("score-end-input").value   = sEnd.toFixed(3);
      const img = new Image();
      img.src = "/image?path=" + encodeURIComponent(sc.score_image);
      img.onload = () => {
        scoreView.img = img;
        scoreView.path  = sc.score_image;
        scoreView.start = sStart;
        scoreView.end   = sEnd;
        scoreView.panOffset = 0;
        draw();
      };
    }

    // Load second image if present
    if (sc.score2_image) {
      document.getElementById("score2-path-input").value = sc.score2_image;
      const s2Start = sc.score2_start ?? 0;
      const s2End   = sc.score2_end   ?? state.duration;
      document.getElementById("score2-start-input").value = s2Start.toFixed(3);
      document.getElementById("score2-end-input").value   = s2End.toFixed(3);
      const img2 = new Image();
      img2.src = "/image?path=" + encodeURIComponent(sc.score2_image);
      img2.onload = () => {
        score2View.img = img2; score2View.path = sc.score2_image;
        score2View.start = s2Start; score2View.end = s2End; score2View.panOffset = 0;
        const cont = document.getElementById("score2-container");
        if (!cont.classList.contains("visible")) {
          cont.classList.add("visible");
          document.getElementById("toggle-score2-btn").classList.add("active");
          setTimeout(resizeScore2Canvas, 10);
        } else { resizeScore2Canvas(); }
      };
    }

    updateScoreInfo();
    draw();
    statusEl.textContent = "imported ← " + path;
    setTimeout(() => { statusEl.textContent = ""; }, 4000);
  } catch(e) {
    statusEl.textContent = "import failed: " + e;
  }
});

// ─── Right-click delete ───────────────────────────────────────────────────────
canvas.addEventListener("contextmenu", e => {
  e.preventDefault();
  if (!state.duration) return;
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToT(x);
  const PX_THRESH = 12;  // pixels within which we snap to an annotation

  let best = null, bestDist = Infinity;

  // Check event markers
  state.events.forEach((ev, i) => {
    const d = Math.abs(tToX(ev.t) - x);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "event", i }; }
  });

  // Check dynamic point marks
  state.dynamics.forEach((d, i) => {
    if (d.t !== undefined) {
      const px = Math.abs(tToX(d.t) - x);
      if (px < PX_THRESH && px < bestDist) { bestDist = px; best = { type: "dynamic", i }; }
    }
  });

  // Check dynamic ranges (clicked inside a range)
  state.dynamics.forEach((d, i) => {
    if (d.from !== undefined) {
      const x1 = tToX(d.from), x2 = tToX(d.to);
      if (x >= x1 && x <= x2) {
        const midDist = Math.abs(x - (x1 + x2) / 2);
        if (midDist < bestDist) { bestDist = midDist; best = { type: "dynamic", i }; }
      }
    }
  });

  // Check sample boundaries (within PX_THRESH of from or to edge)
  for (const [name, s] of Object.entries(state.samples)) {
    const d1 = Math.abs(tToX(s.from) - x);
    const d2 = Math.abs(tToX(s.to) - x);
    const d = Math.min(d1, d2);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "sample", name }; }
  }

  // Check FX zones
  state.fxRanges.forEach((fz, i) => {
    const x1 = tToX(fz.from), x2 = tToX(fz.to);
    if (x >= x1 && x <= x2) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "fxzone", i }; }
    }
  });

  // Check tempo ranges
  state.tempo.forEach((tp, i) => {
    const x1 = tToX(tp.from), x2 = tToX(tp.to);
    if (x >= x1 && x <= x2) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "tempo", i }; }
    }
    const d = Math.min(Math.abs(x1 - x), Math.abs(x2 - x));
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "tempo", i }; }
  });

  // Check phrase markers
  state.phrases.forEach((ph, i) => {
    const x1 = tToX(ph.from), x2 = tToX(ph.to);
    if (x >= x1 && x <= x2) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "phrase", i }; }
    }
    const d = Math.min(Math.abs(x1 - x), Math.abs(x2 - x));
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "phrase", i }; }
  });

  // Check noteRel markers
  state.noteRel.forEach((nr, i) => {
    const x1 = tToX(nr.from), x2 = tToX(nr.to ?? nr.from);
    const d = nr.to ? Math.min(Math.abs(x1 - x), Math.abs(x2 - x)) : Math.abs(x1 - x);
    if (x >= x1 && x <= (x2 || x1 + 1)) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "noteRel", i }; }
    }
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "noteRel", i }; }
  });

  // Check articulation markers
  state.articulations.forEach((ar, i) => {
    const xa = tToX(ar.t ?? ar.from);
    const d = Math.abs(xa - x);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "articulation", i }; }
  });

  if (!best) return;

  pushHistory();
  if (best.type === "event") {
    state.events.splice(best.i, 1);
  } else if (best.type === "dynamic") {
    state.dynamics.splice(best.i, 1);
  } else if (best.type === "sample") {
    delete state.samples[best.name];
  } else if (best.type === "tempo") {
    state.tempo.splice(best.i, 1);
  } else if (best.type === "fxzone") {
    state.fxRanges.splice(best.i, 1);
  } else if (best.type === "phrase") {
    state.phrases.splice(best.i, 1);
  } else if (best.type === "noteRel") {
    state.noteRel.splice(best.i, 1);
  } else if (best.type === "articulation") {
    state.articulations.splice(best.i, 1);
  }
  updateScoreInfo();
  draw();
});

// Initial draw
draw();
