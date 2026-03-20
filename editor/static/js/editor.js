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

// ─── Load ─────────────────────────────────────────────────────────────────────
document.getElementById("load-btn").addEventListener("click", loadFile);
document.getElementById("path-input").addEventListener("keydown", e => {
  if (e.key === "Enter") loadFile();
});

async function loadFile() {
  const path = document.getElementById("path-input").value.trim();
  if (!path) return;
  document.getElementById("load-btn").textContent = "Loading…";
  try {
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
    baseAudio.src = "/video?path=" + encodeURIComponent(path);
    if (data.frame) {
      vid.src = "/video?path=" + encodeURIComponent(path);
      vid.style.display = "none";
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

vid.addEventListener("loadedmetadata", () => {
  if (viewMode === "video") vid.style.display = "block";
  document.getElementById("frame-placeholder").style.display = "none";
  if (state.duration > 0) vid.currentTime = state.currentTime;
  draw();
});

// ─── Drag state ───────────────────────────────────────────────────────────────
const dragState = { active: false, startX: 0, curX: 0, startT: 0, curT: 0, canvas: null };
let mouseIsDown = false;
let panStart = null;
let score2Pan = null;

// ─── Waveform canvas interaction ──────────────────────────────────────────────
canvas.addEventListener("mousemove", e => {
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const t = xToT(x);

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

  if (activeTool === "sample" || activeTool === "dynamics" || activeTool === "tempo" ||
      activeTool === "fx" || activeTool === "phrase" || activeTool === "glissando" || activeTool === "legato") {
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
      if (activeTool === "dynamics")      openMarkPopup(t);
      else if (activeTool === "arpchord") openNoteRelPopup("arpeggiate", t, t);
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

// ─── Frame canvas interaction ─────────────────────────────────────────────────
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
  if (activeTool === "sample" || activeTool === "dynamics" || activeTool === "tempo" ||
      activeTool === "fx" || activeTool === "phrase" || activeTool === "glissando" || activeTool === "legato") {
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

// ─── Right-click delete ───────────────────────────────────────────────────────
canvas.addEventListener("contextmenu", e => {
  e.preventDefault();
  if (!state.duration) return;
  const r = canvas.getBoundingClientRect();
  const x = e.clientX - r.left;
  const PX_THRESH = 12;

  let best = null, bestDist = Infinity;

  state.events.forEach((ev, i) => {
    const d = Math.abs(tToX(ev.t) - x);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "event", i }; }
  });

  state.dynamics.forEach((d, i) => {
    if (d.t !== undefined) {
      const px = Math.abs(tToX(d.t) - x);
      if (px < PX_THRESH && px < bestDist) { bestDist = px; best = { type: "dynamic", i }; }
    }
  });

  state.dynamics.forEach((d, i) => {
    if (d.from !== undefined) {
      const x1 = tToX(d.from), x2 = tToX(d.to);
      if (x >= x1 && x <= x2) {
        const midDist = Math.abs(x - (x1 + x2) / 2);
        if (midDist < bestDist) { bestDist = midDist; best = { type: "dynamic", i }; }
      }
    }
  });

  for (const [name, s] of Object.entries(state.samples)) {
    const d1 = Math.abs(tToX(s.from) - x);
    const d2 = Math.abs(tToX(s.to) - x);
    const d = Math.min(d1, d2);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "sample", name }; }
  }

  state.fxRanges.forEach((fz, i) => {
    const x1 = tToX(fz.from), x2 = tToX(fz.to);
    if (x >= x1 && x <= x2) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "fxzone", i }; }
    }
  });

  state.tempo.forEach((tp, i) => {
    const x1 = tToX(tp.from), x2 = tToX(tp.to);
    if (x >= x1 && x <= x2) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "tempo", i }; }
    }
    const d = Math.min(Math.abs(x1 - x), Math.abs(x2 - x));
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "tempo", i }; }
  });

  state.phrases.forEach((ph, i) => {
    const x1 = tToX(ph.from), x2 = tToX(ph.to);
    if (x >= x1 && x <= x2) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "phrase", i }; }
    }
    const d = Math.min(Math.abs(x1 - x), Math.abs(x2 - x));
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "phrase", i }; }
  });

  state.noteRel.forEach((nr, i) => {
    const x1 = tToX(nr.from), x2 = tToX(nr.to ?? nr.from);
    if (x >= x1 && x <= (x2 || x1 + 1)) {
      const midDist = Math.abs(x - (x1 + x2) / 2);
      if (midDist < bestDist) { bestDist = midDist; best = { type: "noteRel", i }; }
    }
    const d = nr.to ? Math.min(Math.abs(x1 - x), Math.abs(x2 - x)) : Math.abs(x1 - x);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "noteRel", i }; }
  });

  state.articulations.forEach((ar, i) => {
    const xa = tToX(ar.t ?? ar.from);
    const d = Math.abs(xa - x);
    if (d < PX_THRESH && d < bestDist) { bestDist = d; best = { type: "articulation", i }; }
  });

  if (!best) return;

  pushHistory();
  if (best.type === "event")         state.events.splice(best.i, 1);
  else if (best.type === "dynamic")  state.dynamics.splice(best.i, 1);
  else if (best.type === "sample")   delete state.samples[best.name];
  else if (best.type === "tempo")    state.tempo.splice(best.i, 1);
  else if (best.type === "fxzone")   state.fxRanges.splice(best.i, 1);
  else if (best.type === "phrase")   state.phrases.splice(best.i, 1);
  else if (best.type === "noteRel")  state.noteRel.splice(best.i, 1);
  else if (best.type === "articulation") state.articulations.splice(best.i, 1);
  updateScoreInfo();
  draw();
});

// Initial draw
draw();
