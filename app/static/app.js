(function () {
  const statusBox = document.getElementById('apiStatus');
  const loadBtn = document.getElementById('loadAlbums');
  const testBtn = document.getElementById('testConnection');
  const albumList = document.getElementById('albumList');
  const selectedInput = document.getElementById('selectedAlbums');
  const hiddenInput = document.getElementById('hiddenAlbums');
  const albumSearch = document.getElementById('albumSearch');
  const modeHelp = document.getElementById('albumModeHelp');
  const selectVisible = document.getElementById('selectVisible');
  const clearVisible = document.getElementById('clearVisible');

  if (!albumList) return;

  let albums = Array.isArray(window.IMF_MANAGER?.albums) ? window.IMF_MANAGER.albums : [];
  let selected = new Set((window.IMF_MANAGER?.selectedAlbums || []).map(String));
  let hidden = new Set((window.IMF_MANAGER?.hiddenAlbums || []).map(String));

  function currentMode() {
    const checked = document.querySelector('input[name="album_mode"]:checked');
    return checked ? checked.value : 'manual';
  }

  function showStatus(message, kind) {
    if (!statusBox) return;
    statusBox.textContent = message;
    statusBox.className = `notice ${kind || ''}`;
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function syncHiddenInputs() {
    selectedInput.value = Array.from(selected).join(',');
    hiddenInput.value = Array.from(hidden).join(',');
  }

  function rowWanted(album) {
    const q = (albumSearch?.value || '').toLowerCase().trim();
    if (!q) return true;
    const hay = `${album.albumName || ''} ${album.id || ''} ${album.ownerName || ''}`.toLowerCase();
    return hay.includes(q);
  }

  function renderModeHelp() {
    const mode = currentMode();
    const manual = document.querySelector('.manual-fields');
    if (manual) manual.style.display = mode === 'manual' ? 'grid' : 'none';
    const text = {
      manual: 'Manual mode: the manager will not overwrite Albums. Use the raw Albums / ExcludedAlbums fields below. The album list only shows the cached Immich albums.',
      all: 'Allow all: every cached album passing the shared/owned/prefix filters is written into Accounts[n].Albums when you apply or sync.',
      selected: 'Show selected: only checked albums are written. Use this for a strict allow-list.',
      hide_selected: 'Hide selected: checked albums are removed from the matching album list. Use this when almost everything should be shown.'
    }[mode] || '';
    if (modeHelp) modeHelp.textContent = text;
  }

  function renderAlbums() {
    renderModeHelp();
    const mode = currentMode();
    const visibleAlbums = albums.filter(rowWanted);
    if (!albums.length) {
      albumList.innerHTML = `<div class="album-empty muted">No cached albums yet. Click "Refresh album cache" after saving a valid Immich URL and API key.</div>`;
      return;
    }
    if (!visibleAlbums.length) {
      albumList.innerHTML = `<div class="album-empty muted">No cached albums match the search filter.</div>`;
      return;
    }
    albumList.innerHTML = visibleAlbums.map(album => {
      const id = String(album.id || '');
      let checked = false;
      if (mode === 'selected') checked = selected.has(id);
      else if (mode === 'hide_selected') checked = hidden.has(id);
      else if (mode === 'all') checked = true;
      else checked = (window.IMF_MANAGER?.accountAlbums || []).map(String).includes(id);
      const disabled = mode === 'all' || mode === 'manual';
      const shortId = id.length > 14 ? `${id.slice(0, 8)}...${id.slice(-4)}` : id;
      return `<label class="album-row ${disabled ? 'is-disabled' : ''}" data-album-id="${escapeHtml(id)}">
        <span class="album-cell album-cell-check">
          <input type="checkbox" class="album-check" value="${escapeHtml(id)}" ${checked ? 'checked' : ''} ${disabled ? 'disabled' : ''}>
        </span>
        <span class="album-cell album-cell-main">
          <strong>${escapeHtml(album.albumName || id)}</strong>
          ${album.ownerName ? `<span class="muted">${escapeHtml(album.ownerName)}</span>` : '<span class="muted">Owner unavailable</span>'}
        </span>
        <span class="album-cell album-cell-meta">
          <span class="album-cell-label">Assets</span>
          <span>${album.assetCount ?? '—'}</span>
        </span>
        <span class="album-cell album-cell-meta">
          <span class="album-cell-label">Shared</span>
          <span>${album.shared ? 'yes' : 'no'}</span>
        </span>
        <span class="album-cell album-cell-id">
          <span class="album-cell-label">ID</span>
          <code title="${escapeHtml(id)}">${escapeHtml(shortId)}</code>
        </span>
      </label>`;
    }).join('');
  }

  function updateFromCheckboxes() {
    const mode = currentMode();
    for (const check of albumList.querySelectorAll('.album-check')) {
      const id = check.value;
      if (mode === 'selected') {
        if (check.checked) selected.add(id); else selected.delete(id);
      } else if (mode === 'hide_selected') {
        if (check.checked) hidden.add(id); else hidden.delete(id);
      }
    }
    syncHiddenInputs();
  }

  async function fetchJson(url, options) {
    const res = await fetch(url, options || {});
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  if (loadBtn) {
    loadBtn.addEventListener('click', async () => {
      try {
        showStatus('Refreshing albums from Immich and storing them in the sidecar state...', 'warning');
        const data = await fetchJson(loadBtn.dataset.albumsUrl);
        albums = data.albums || [];
        renderAlbums();
        showStatus(`Album cache refreshed: ${albums.length} album(s). Save the policy after changing checkboxes.`, 'success');
      } catch (err) {
        showStatus(`Could not refresh albums: ${err.message}`, 'error');
      }
    });
  }

  if (testBtn) {
    testBtn.addEventListener('click', async () => {
      try {
        showStatus('Testing Immich connection...', 'warning');
        const data = await fetchJson(testBtn.dataset.testUrl, { method: 'POST' });
        showStatus(`Connection OK. Immich returned ${data.album_count} album(s).`, 'success');
      } catch (err) {
        showStatus(`Connection failed: ${err.message}`, 'error');
      }
    });
  }

  albumList.addEventListener('change', (event) => {
    if (event.target.classList.contains('album-check')) updateFromCheckboxes();
  });

  for (const radio of document.querySelectorAll('input[name="album_mode"]')) {
    radio.addEventListener('change', renderAlbums);
  }

  if (albumSearch) albumSearch.addEventListener('input', renderAlbums);

  if (selectVisible) selectVisible.addEventListener('click', () => {
    const mode = currentMode();
    if (mode !== 'selected' && mode !== 'hide_selected') return;
    for (const check of albumList.querySelectorAll('.album-check')) {
      if (!check.disabled) check.checked = true;
    }
    updateFromCheckboxes();
  });

  if (clearVisible) clearVisible.addEventListener('click', () => {
    const mode = currentMode();
    if (mode !== 'selected' && mode !== 'hide_selected') return;
    for (const check of albumList.querySelectorAll('.album-check')) {
      if (!check.disabled) check.checked = false;
    }
    updateFromCheckboxes();
  });

  const form = document.getElementById('accountForm');
  if (form) form.addEventListener('submit', updateFromCheckboxes);

  renderAlbums();
})();

/* ── People browser ──────────────────────────────────── */
(function () {
  const loadBtn     = document.getElementById('loadPeople');
  const grid        = document.getElementById('peopleGrid');
  const searchInput = document.getElementById('peopleSearch');
  const statusBox   = document.getElementById('peopleStatus');
  const countBadge  = document.getElementById('peopleBrowserCount');
  const field       = document.getElementById('peopleField');

  if (!loadBtn || !grid) return;

  const thumbBase  = loadBtn.dataset.thumbBase || '';
  const peopleUrl  = loadBtn.dataset.peopleUrl || '';

  let allPeople = [];
  let selected  = new Set((window.IMF_MANAGER?.accountPeople || []).map(String).filter(Boolean));

  function esc(v) {
    return String(v ?? '').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }

  function thumbUrl(id) {
    return thumbBase.replace('PERSON_ID', encodeURIComponent(id));
  }

  function syncField() {
    if (field) field.value = Array.from(selected).join(', ');
    if (countBadge) {
      const n = selected.size;
      countBadge.textContent = n === 1 ? '1 selected' : `${n} selected`;
    }
  }

  function showStatus(msg, kind) {
    if (!statusBox) return;
    statusBox.textContent = msg;
    statusBox.className = `notice ${kind || ''}`;
  }

  function visible() {
    const q = (searchInput?.value || '').toLowerCase().trim();
    return q ? allPeople.filter(p => p.name.toLowerCase().includes(q)) : allPeople;
  }

  function renderPeople() {
    const list = visible();
    if (!allPeople.length) {
      grid.innerHTML = '<div class="people-empty muted">Click "Load / Refresh" to fetch people from Immich.</div>';
      return;
    }
    if (!list.length) {
      grid.innerHTML = '<div class="people-empty muted">No people match the filter.</div>';
      return;
    }
    grid.innerHTML = list.map(p => {
      const id  = String(p.id);
      const sel = selected.has(id);
      const src = esc(thumbUrl(id));
      const fb  = '/static/avatar-fallback.svg';
      return `<label class="person-card${sel ? ' is-selected' : ''}" data-person-id="${esc(id)}">
  <input type="checkbox" class="person-check sr-only" value="${esc(id)}"${sel ? ' checked' : ''}>
  <div class="person-avatar-wrap">
    <img class="person-avatar" src="${src}" alt="${esc(p.name)}" loading="lazy"
         onerror="this.classList.add('avatar-error');this.nextElementSibling.style.display='flex'">
    <div class="person-avatar-fallback" style="display:none">
      <svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="16" cy="12" r="6" fill="currentColor" opacity=".55"/>
        <ellipse cx="16" cy="28" rx="10" ry="7" fill="currentColor" opacity=".55"/>
      </svg>
    </div>
  </div>
  <span class="person-name">${esc(p.name)}</span>
</label>`;
    }).join('');
  }

  grid.addEventListener('change', e => {
    if (!e.target.classList.contains('person-check')) return;
    const id   = e.target.value;
    const card = e.target.closest('.person-card');
    if (e.target.checked) { selected.add(id);    card?.classList.add('is-selected'); }
    else                  { selected.delete(id); card?.classList.remove('is-selected'); }
    syncField();
  });

  if (searchInput) searchInput.addEventListener('input', renderPeople);

  loadBtn.addEventListener('click', async () => {
    loadBtn.disabled = true;
    showStatus('Loading people from Immich…', 'warning');
    try {
      const res  = await fetch(peopleUrl);
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${res.status}`);
      allPeople = data.people || [];
      renderPeople();
      showStatus(`Loaded ${allPeople.length} people.`, 'success');
      document.getElementById('peopleBrowserAccordion')?.setAttribute('open', '');
    } catch (err) {
      showStatus(`Could not load people: ${err.message}`, 'error');
    } finally {
      loadBtn.disabled = false;
    }
  });

  syncField();
  renderPeople();
})();
