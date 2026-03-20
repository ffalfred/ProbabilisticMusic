// ─── UI helpers (collapsible rows, image sync) ────────────────────────────────
function toggleBarContent(contentId, chevronId) {
  const el = document.getElementById(contentId);
  const ch = document.getElementById(chevronId);
  if (!el) return;
  const hidden = el.style.display === "none";
  el.style.display = hidden ? "" : "none";
  if (ch) ch.innerHTML = hidden ? "&#9660;" : "&#9658;";
}

function toggleImgPaths() {
  const el  = document.getElementById("img-paths-content");
  const btn = document.getElementById("toggle-img-paths-btn");
  if (!el) return;
  const hidden = el.style.display === "none";
  el.style.display = hidden ? "" : "none";
  if (btn) btn.innerHTML = (hidden ? "&#9660;" : "&#9658;") + " Paths";
}

function syncImageRanges() {
  const s  = document.getElementById("score-start-input");
  const e  = document.getElementById("score-end-input");
  const s2 = document.getElementById("score2-start-input");
  const e2 = document.getElementById("score2-end-input");
  if (!s || !e || !s2 || !e2) return;
  s2.value = s.value;
  e2.value = e.value;
  s2.dispatchEvent(new Event("change"));
  e2.dispatchEvent(new Event("change"));
}
