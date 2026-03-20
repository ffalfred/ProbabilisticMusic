// ─── score2 panel wiring ──────────────────────────────────────────────────────
document.getElementById("toggle-score2-btn").addEventListener("click", () => {
  const cont = document.getElementById("score2-container");
  const vis = cont.classList.toggle("visible");
  document.getElementById("toggle-score2-btn").classList.toggle("active", vis);
  if (vis) { setTimeout(() => { resizeScore2Canvas(); draw(); }, 10); } else { draw(); }
});

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

// score2Canvas mouse handlers
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
  if (activeTool === "sample" || activeTool === "dynamics" || activeTool === "tempo" ||
      activeTool === "fx" || activeTool === "phrase" || activeTool === "glissando" || activeTool === "legato") {
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
      if (activeTool === "sample")          openSamplePopup(t1, t2);
      else if (activeTool === "dynamics")   openRangePopup(t1, t2);
      else if (activeTool === "tempo")      openTempoPopup(t1, t2);
      else if (activeTool === "fx")         openFxZonePopup(t1, t2);
      else if (activeTool === "phrase")     openPhrasePopup(t1, t2);
      else if (activeTool === "glissando")  openNoteRelPopup("glissando", t1, t2);
      else if (activeTool === "legato")     openArticulationPopup("legato", t1, t2);
    } else {
      if (activeTool === "dynamics")        openMarkPopup(t);
      else if (activeTool === "arpchord")   openNoteRelPopup("arpeggiate", t, t);
      else if (activeTool === "staccato")   openArticulationPopup("staccato", t);
      else if (activeTool === "fermata")    openArticulationPopup("fermata", t);
      else if (activeTool === "accent")     openArticulationPopup("accent", t);
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

score2Canvas.addEventListener("wheel", e => {
  if (!score2View.img) return;
  e.preventDefault();
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
  score2View.scale = Math.max(0.1, Math.min(20, score2View.scale * factor));
  draw();
}, { passive: false });

score2Canvas.addEventListener("dblclick", () => {
  score2View.scale = 1; score2View.panOffset = 0; draw();
});

new ResizeObserver(() => {
  if (document.getElementById("score2-container").classList.contains("visible")) {
    resizeScore2Canvas();
  }
}).observe(document.getElementById("score2-container"));

// ─── Score image (primary) ────────────────────────────────────────────────────
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

// ─── View toggle (Score / Video) ──────────────────────────────────────────────
document.getElementById("view-toggle-btn").addEventListener("click", () => {
  viewMode = viewMode === "score" ? "video" : "score";
  document.getElementById("view-toggle-btn").textContent =
    viewMode === "score" ? "[ Score ]" : "[ Video ]";
  if (viewMode === "video") {
    applyFZ();
    vid.style.display = vid.src ? "block" : "none";
  } else {
    document.getElementById("frame-inner").style.transform = "";
    vid.style.display = "none";
  }
  draw();
});
