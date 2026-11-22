// ─── Output loudness ──────────────────────────────────────────────────────────
// Renders keep the level the performance produced (src/loudness.py).
//  • Safety brake — one shared switch (top bar) for everything played in the
//    editor: a limiter that pulls down only the moments that would go above
//    -1 dBFS. Off = overs clip, audibly.
//  • Exports add an optional one-gain adjustment (match source / target
//    LUFS) and their own brake checkbox; see loudnessOptionsHtml().

const _BRAKE_STORE_KEY = 'opus.audioBrake';

function audioBrakeOn() {
  const el = document.getElementById('audio-brake');
  return el ? el.checked : true;
}

// Loudness options for in-editor previews (no adjustment, just the brake).
function previewLoudness() {
  return { brake: audioBrakeOn() };
}

function _fmtDb(v) { return (v > 0 ? '+' : '') + v.toFixed(1); }

// One line describing a server loudness report.
function describeLoudness(rep) {
  if (!rep) return '';
  const parts = [rep.lufs == null ? 'silent' : `${rep.lufs.toFixed(1)} LUFS`];
  if (rep.gain_db) parts.push(`adjusted ${_fmtDb(rep.gain_db)} dB`);
  if (rep.brake_db > 0.05) parts.push(`brake −${rep.brake_db.toFixed(1)} dB`);
  if (rep.peak_db != null && rep.peak_db > 0) parts.push(`peaks ${_fmtDb(rep.peak_db)} dB over max — clips`);
  return parts.join(', ');
}

// Show what the brake did on the last editor render, next to its switch.
function showBrakeReport(rep) {
  const el = document.getElementById('audio-brake-status');
  if (!el) return;
  el.classList.remove('clipping');
  el.textContent = '';
  el.title = rep ? 'Last render: ' + describeLoudness(rep) : '';
  if (!rep) return;
  if (rep.brake_db > 0.05) {
    el.textContent = `−${rep.brake_db.toFixed(1)} dB`;
  } else if (rep.peak_db != null && rep.peak_db > 0) {
    el.textContent = `clips ${_fmtDb(rep.peak_db)} dB`;
    el.classList.add('clipping');
  }
}

// Export controls. `prefix` keeps ids unique per popup.
function loudnessOptionsHtml(prefix) {
  const sel = 'background:#1a1a1a;border:1px solid #333;color:#ccc;padding:4px 6px;font-size:11px;';
  return `
      <div>
        <label style="font-size:11px;color:#888;">Loudness:</label>
        <div style="display:flex;gap:6px;margin-top:3px;">
          <select id="${prefix}-adjust" style="flex:1;${sel}" onchange="_loudnessUiSync('${prefix}')">
            <option value="none" selected>Leave it (as performed)</option>
            <option value="source">Match source (as loud as the loaded audio)</option>
            <option value="target">Target loudness</option>
          </select>
          <select id="${prefix}-target" style="${sel}display:none;" onchange="_loudnessUiSync('${prefix}')">
            <option value="-14" selected>−14 LUFS (streaming)</option>
            <option value="-16">−16 LUFS (Apple, podcasts)</option>
            <option value="-23">−23 LUFS (broadcast)</option>
            <option value="custom">custom…</option>
          </select>
          <input id="${prefix}-custom" type="number" value="-18" step="0.5" max="0"
                 style="width:60px;${sel}display:none;" title="Target loudness in LUFS">
        </div>
        <label style="font-size:11px;color:#ccc;display:block;margin-top:4px;">
          <input id="${prefix}-brake" type="checkbox" checked> Safety brake (limit peaks to −1 dB)
        </label>
        <div style="font-size:9px;color:#555;margin-top:2px;">The adjustment is one gain for the whole piece, measured on the whole render — levels inside the piece and a range's level within it are kept. Without the brake, peaks over the maximum clip (except in 32-bit float).</div>
      </div>`;
}

function _loudnessUiSync(prefix) {
  const adj = document.getElementById(prefix + '-adjust')?.value;
  const tgt = document.getElementById(prefix + '-target');
  const cus = document.getElementById(prefix + '-custom');
  if (tgt) tgt.style.display = adj === 'target' ? '' : 'none';
  if (cus) cus.style.display = adj === 'target' && tgt?.value === 'custom' ? '' : 'none';
}

function readLoudnessOptions(prefix) {
  const adjust = document.getElementById(prefix + '-adjust')?.value || 'none';
  const tgt    = document.getElementById(prefix + '-target')?.value || '-14';
  const target = tgt === 'custom'
    ? parseFloat(document.getElementById(prefix + '-custom')?.value)
    : parseFloat(tgt);
  return {
    adjust,
    target_lufs: isFinite(target) ? target : -14,
    brake: document.getElementById(prefix + '-brake')?.checked !== false,
  };
}

// Restore the switch (a per-browser convenience; default on).
(function _initBrakeSwitch() {
  const el = document.getElementById('audio-brake');
  if (!el) return;
  try {
    const saved = localStorage.getItem(_BRAKE_STORE_KEY);
    if (saved !== null) el.checked = saved === '1';
  } catch (e) {}
  el.addEventListener('change', () => {
    try { localStorage.setItem(_BRAKE_STORE_KEY, el.checked ? '1' : '0'); } catch (e) {}
    showBrakeReport(null);   // the last report no longer applies
  });
})();
