// File browser modal — replaces manual path entry.
// Path inputs with class "path-select" are read-only and open the browser on click.
(function () {
  const AUDIO_EXTS = ['.wav','.mp3','.flac','.ogg','.aac','.mp4','.mov','.mkv','.webm'];
  const YAML_EXTS  = ['.yaml','.yml'];
  const IMG_EXTS   = ['.png','.jpg','.jpeg','.webp','.gif','.bmp','.svg'];

  // Map input id → { filter, autoClickId, browseId }
  // autoClickId: button to programmatically click after a file is chosen (triggers load)
  // browseId:    button that opens the file browser modal
  const INPUT_CONFIG = {
    'path-input':            { filter: AUDIO_EXTS, autoClickId: 'load-btn',                  browseId: 'browse-audio-btn' },
    'score-path-input':      { filter: IMG_EXTS,   autoClickId: 'load-score-btn',             browseId: 'browse-score-btn' },
    'score2-path-input':     { filter: IMG_EXTS,   autoClickId: 'load-score2-btn',            browseId: 'browse-score2-btn' },
    'import-path':           { filter: YAML_EXTS,  autoClickId: 'import-btn',                 browseId: 'browse-import-btn' },
    'interp-score-path':     { filter: YAML_EXTS,  autoClickId: 'interp-load-score-btn',      browseId: 'interp-browse-score-btn' },
    'interp-load-path':      { filter: YAML_EXTS,  autoClickId: 'interp-load-btn',            browseId: 'interp-browse-load-btn' },
    'interp-audio-path':     { filter: AUDIO_EXTS, autoClickId: 'interp-load-wave-btn',       browseId: 'interp-browse-audio-btn' },
    'interp-score-img-path': { filter: IMG_EXTS,   autoClickId: 'interp-load-score-img-btn',  browseId: 'interp-browse-score-img-btn' },
    'interp-meta-img-path':  { filter: IMG_EXTS,   autoClickId: 'interp-load-meta-img-btn',   browseId: 'interp-browse-meta-img-btn' },
  };

  let _targetInput  = null;
  let _filter       = null;
  let _autoClick    = null;
  let _currentPath  = null;
  let _saveMode     = false;
  let _saveCallback = null;

  function open(inputEl, filter, autoClickId) {
    _targetInput = inputEl;
    _filter      = filter;
    _autoClick   = autoClickId ? document.getElementById(autoClickId) : null;
    _saveMode    = false;

    document.getElementById('fb-modal').style.display = 'flex';
    document.getElementById('fb-save-row').style.display = 'none';
    navigate(null);   // always start at home
  }

  // Expose for opening files with a callback (e.g. add track).
  window.openFileBrowser = function(callback, filterExts) {
    _saveMode     = false;
    _saveCallback = callback;  // reuse save callback slot for the file-chosen callback
    _targetInput  = null;
    _filter       = filterExts || AUDIO_EXTS;
    _autoClick    = null;

    document.getElementById('fb-save-row').style.display = 'none';
    document.getElementById('fb-modal').style.display = 'flex';
    navigate(null);
  };

  // Expose for export.js and interpreter.js to call for save dialogs.
  // Optional filterExts overrides the default YAML filter (e.g. ['.wav'] for audio export).
  window.openSaveBrowser = function(callback, defaultName, filterExts) {
    _saveMode     = true;
    _saveCallback = callback;
    _targetInput  = null;
    _filter       = filterExts || YAML_EXTS;

    const filenameEl = document.getElementById('fb-filename');
    if (filenameEl) filenameEl.value = defaultName || '';

    document.getElementById('fb-save-row').style.display = 'flex';
    document.getElementById('fb-modal').style.display = 'flex';
    navigate(null);
  };

  function close() {
    document.getElementById('fb-modal').style.display = 'none';
    document.getElementById('fb-save-row').style.display = 'none';
    _saveMode     = false;
    _saveCallback = null;
    _targetInput  = null;
  }

  function navigate(path) {
    const url = '/browse' + (path ? '?path=' + encodeURIComponent(path) : '');
    fetch(url)
      .then(r => r.json())
      .then(data => {
        if (data.error) { console.warn('browse error:', data.error); return; }
        render(data);
      });
  }

  function render(data) {
    _currentPath = data.current;
    document.getElementById('fb-path').textContent = data.current;
    const list = document.getElementById('fb-list');
    list.innerHTML = '';

    if (data.parent) {
      list.appendChild(makeItem('↑ ..', 'fb-dir', () => navigate(data.parent)));
    }

    for (const d of data.dirs) {
      list.appendChild(makeItem('▸ ' + d, 'fb-dir', () => navigate(data.current + '/' + d)));
    }

    let shown = 0;
    for (const f of data.files) {
      if (_filter) {
        const lower = f.toLowerCase();
        if (!_filter.some(ext => lower.endsWith(ext))) continue;
      }
      const fullPath = data.current + '/' + f;
      if (_saveMode) {
        // In save mode: clicking a file pre-fills the filename input
        list.appendChild(makeItem(f, 'fb-file', () => {
          const el = document.getElementById('fb-filename');
          if (el) el.value = f;
        }));
      } else {
        list.appendChild(makeItem(f, 'fb-file', () => select(fullPath)));
      }
      shown++;
    }

    if (shown === 0 && data.files.length > 0) {
      const hint = document.createElement('div');
      hint.className = 'fb-hint';
      hint.textContent = 'no matching files here';
      list.appendChild(hint);
    }
  }

  function makeItem(label, cls, onClick) {
    const el = document.createElement('div');
    el.className = 'fb-item ' + cls;
    el.textContent = label;
    el.addEventListener('click', onClick);
    return el;
  }

  function select(path) {
    const hadInput = !!_targetInput;
    const cb       = _saveCallback;
    const ac       = _autoClick;
    if (_targetInput) {
      _targetInput.value = path;
      _targetInput.dispatchEvent(new Event('change', { bubbles: true }));
    }
    close();
    if (!hadInput && cb) cb(path);   // openFileBrowser callback
    else if (ac) ac.click();
  }

  document.addEventListener('DOMContentLoaded', () => {
    // Wire close button and backdrop click
    const modal    = document.getElementById('fb-modal');
    const closeBtn = document.getElementById('fb-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', close);
    if (modal)    modal.addEventListener('click', e => { if (e.target === modal) close(); });

    // Wire save button
    const saveBtn = document.getElementById('fb-save-btn');
    if (saveBtn) {
      saveBtn.addEventListener('click', () => {
        const name = (document.getElementById('fb-filename').value || '').trim();
        if (!name || !_saveCallback) return;
        const fullPath = _currentPath ? _currentPath + '/' + name : name;
        const cb = _saveCallback;
        close();
        cb(fullPath);
      });
    }

    // Wire browse buttons and Enter-to-load on path inputs
    for (const [id, cfg] of Object.entries(INPUT_CONFIG)) {
      const el = document.getElementById(id);
      if (!el) continue;
      // Browse button → opens file browser
      const browseBtn = document.getElementById(cfg.browseId);
      if (browseBtn) {
        browseBtn.addEventListener('click', () => open(el, cfg.filter, cfg.autoClickId));
      }
      // Enter key in input → trigger load
      el.addEventListener('keydown', e => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const loadBtn = document.getElementById(cfg.autoClickId);
          if (loadBtn) loadBtn.click();
        }
      });
    }
  });
})();
