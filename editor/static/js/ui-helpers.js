// ─── UI helpers (collapsible rows, image sync) ────────────────────────────────
function toggleBarContent(contentId, chevronId) {
  const el = document.getElementById(contentId);
  const ch = document.getElementById(chevronId);
  if (!el) return;
  const hidden = el.style.display === "none";
  el.style.display = hidden ? "" : "none";
  if (ch) ch.innerHTML = hidden ? "&#9660;" : "&#9658;";
}

function _collapsePanel(panelId, chevronId) {
  // Like toggleBarContent but collapses the entire panel, freeing layout space.
  // The header (with the chevron) stays visible; everything else hides.
  const panel = document.getElementById(panelId);
  const ch    = document.getElementById(chevronId);
  if (!panel) return;
  const children = Array.from(panel.children);
  const header   = children[0]; // first child is the clickable header
  const isCollapsed = panel.dataset.collapsed === '1';
  if (isCollapsed) {
    // Expand: show all children, restore panel width
    children.forEach(c => { if (c !== header) c.style.display = ''; });
    panel.style.width = '';
    panel.style.minWidth = '';
    panel.dataset.collapsed = '0';
    if (ch) ch.innerHTML = '&#9660;';
  } else {
    // Collapse: hide all children except header, shrink panel
    children.forEach(c => { if (c !== header) c.style.display = 'none'; });
    panel.style.width = 'auto';
    panel.style.minWidth = '0';
    panel.dataset.collapsed = '1';
    if (ch) ch.innerHTML = '&#9658;';
  }
  setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
}

function _collapsePalette() {
  const palette = document.getElementById('palette');
  const content = document.getElementById('palette-content');
  const ch      = document.getElementById('palette-chevron');
  if (!palette || !content) return;
  const hidden = content.style.display === 'none';
  if (hidden) {
    // Expand
    content.style.display = '';
    palette.style.width = palette.dataset.expandedWidth || '';
    if (ch) ch.innerHTML = '&#9660;';
  } else {
    // Collapse — save current width, shrink to label-only
    palette.dataset.expandedWidth = palette.style.width || getComputedStyle(palette).width;
    content.style.display = 'none';
    palette.style.width = '24px';
    if (ch) ch.innerHTML = '&#9658;';
  }
  setTimeout(() => window.dispatchEvent(new Event('resize')), 50);
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
