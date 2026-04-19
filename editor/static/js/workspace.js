// ─── Workspace tab switching ───────────────────────────────────────────────────
// Layout: #composer-topbar / #interp-topbar toggle; #mid + #palette always visible;
// #palette-composer / #palette-interpreter toggle; #interp-sections shows for interpreter;
// #ws-conductor is a full-page overlay.

let _activeWorkspace = 'composer';

document.addEventListener('DOMContentLoaded', () => {
  const tabs = document.querySelectorAll('.ws-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      _switchWorkspace(tab.dataset.ws);
    });
  });

  // Initial state: composer active
  _switchWorkspace('composer');
});

function _switchWorkspace(target) {
  _activeWorkspace = target;

  const composerTopbar  = document.getElementById('composer-topbar');
  const interpTopbar    = document.getElementById('interp-topbar');
  const mid             = document.getElementById('mid');
  const palComposer     = document.getElementById('palette-composer');
  const palInterp       = document.getElementById('palette-interpreter');
  const palLabel        = document.getElementById('palette-label');
  const interpSections  = document.getElementById('interp-sections');
  const interpBottombar = document.getElementById('interp-bottombar');
  // interpBottombar is now outside interp-sections — show/hide it with interpreter mode
  const golemWrap       = document.getElementById('golem-timeline-outer');
  const scoreInfoPanel  = document.getElementById('score-info-panel');
  const conductor       = document.getElementById('ws-conductor');
  const playSelect      = document.getElementById('play-mode-select');
  const palette         = document.getElementById('palette');
  const interpInfoPanel = document.getElementById('interp-info-panel');

  // ── Full bidirectional sync between workspaces ──
  // Stop any playing audio to prevent desync
  if (typeof stopAll === 'function') stopAll();

  // Audio path
  const _audioIn      = document.getElementById('path-input');
  const _interpAudioIn = document.getElementById('interp-audio-path');
  if (state.filePath) {
    if (_audioIn)       _audioIn.value       = state.filePath;
    if (_interpAudioIn) _interpAudioIn.value = state.filePath;
  }

  // Score YAML path
  const _interpScoreIn = document.getElementById('interp-score-path');
  const _importIn      = document.getElementById('import-path');
  const _scorePath     = interpState.scorePath || state.lastScorePath || '';
  if (_scorePath) {
    if (_interpScoreIn) _interpScoreIn.value = _scorePath;
    if (_importIn)      _importIn.value      = _scorePath;
    interpState.scorePath = _scorePath;
    state.lastScorePath   = _scorePath;
  }

  // Score images — sync input fields (scoreView/score2View objects are already global)
  if (typeof scoreView !== 'undefined' && scoreView.path) {
    ['score-path-input', 'interp-score-img-path'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = scoreView.path;
    });
  }
  if (typeof score2View !== 'undefined' && score2View.path) {
    ['score2-path-input', 'interp-meta-img-path'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = score2View.path;
    });
  }

  // Clear interpreter trace data when switching to composer so the
  // concerto metadata view doesn't show stale interpreter viz panels.
  if (target === 'composer' && typeof _lastTraceData !== 'undefined') {
    _lastTraceData = null;
  }

  if (target === 'composer') {
    if (composerTopbar)  composerTopbar.style.display  = '';
    if (interpTopbar)    interpTopbar.style.display    = 'none';
    if (mid)             mid.style.display             = '';
    if (palette)         { palette.style.display = ''; palette.style.width = ''; }
    if (palComposer)     palComposer.style.display     = '';
    if (palInterp)       palInterp.style.display       = 'none';
    if (palLabel)        palLabel.textContent          = 'tools';
    if (interpSections)  interpSections.style.display  = 'none';
    if (interpBottombar) interpBottombar.style.display = 'none';
    if (golemWrap)       golemWrap.style.display        = 'none';
    if (scoreInfoPanel)  scoreInfoPanel.style.display  = '';
    if (interpInfoPanel) interpInfoPanel.style.display = 'none';
    if (conductor)       conductor.style.display       = 'none';
    if (playSelect) playSelect.innerHTML =
      '<option value="source">Source</option><option value="mix">Mix</option>';

  } else if (target === 'interpreter') {
    if (composerTopbar)  composerTopbar.style.display  = 'none';
    if (interpTopbar)    interpTopbar.style.display    = '';
    if (mid)             mid.style.display             = '';
    if (palette)         { palette.style.display = ''; palette.style.width = '240px'; }
    if (palComposer)     palComposer.style.display     = 'none';
    if (palInterp)       palInterp.style.display       = '';
    if (palLabel)        palLabel.textContent          = 'golems';
    if (interpSections)  interpSections.style.display  = '';
    if (interpBottombar) interpBottombar.style.display = '';
    if (golemWrap)       golemWrap.style.display        = 'block';
    if (scoreInfoPanel)  scoreInfoPanel.style.display  = 'none';
    if (interpInfoPanel) { interpInfoPanel.style.display = 'flex'; }
    if (conductor)       conductor.style.display       = 'none';
    setTimeout(() => { if (typeof drawGolemTimeline === 'function') drawGolemTimeline(); }, 50);
    if (playSelect) playSelect.innerHTML =
      '<option value="raw">Raw</option><option value="score">Score</option><option value="interp">Interp</option>';


  } else if (target === 'conductor') {
    if (composerTopbar)  composerTopbar.style.display  = 'none';
    if (interpTopbar)    interpTopbar.style.display    = 'none';
    if (mid)             mid.style.display             = 'none';
    if (conductor)       conductor.style.display       = '';
    if (tbpComposer)     tbpComposer.style.display     = 'none';
    if (tbpInterp)       tbpInterp.style.display       = 'none';
  }

  document.dispatchEvent(new CustomEvent('workspace:activated', { detail: target }));
  // Force a layout recalc — without this, #frame-container may render too wide
  // until the user resizes or opens devtools
  setTimeout(() => window.dispatchEvent(new Event('resize')), 0);
}
