(function () {
  const statusBox = document.getElementById('apiStatus');
  const loadBtn = document.getElementById('loadAlbums');
  const testBtn = document.getElementById('testConnection');
  const table = document.getElementById('albumTable');
  const selectedInput = document.getElementById('selectedAlbums');
  const hiddenInput = document.getElementById('hiddenAlbums');
  const albumSearch = document.getElementById('albumSearch');
  const modeHelp = document.getElementById('albumModeHelp');
  const selectVisible = document.getElementById('selectVisible');
  const clearVisible = document.getElementById('clearVisible');

  if (!table) return;

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
      manual: 'Manual mode: the manager will not overwrite Albums. Use the raw Albums / ExcludedAlbums fields below. The table only shows the cached Immich albums.',
      all: 'Allow all: every cached album passing the shared/owned/prefix filters is written into Accounts[n].Albums when you apply or sync.',
      selected: 'Show selected: only checked albums are written. Use this for a strict allow-list.',
      hide_selected: 'Hide selected: checked albums are removed from the matching album list. Use this when almost everything should be shown.'
    }[mode] || '';
    if (modeHelp) modeHelp.textContent = text;
  }

  function renderAlbums() {
    renderModeHelp();
    const tbody = table.querySelector('tbody');
    const mode = currentMode();
    const visibleAlbums = albums.filter(rowWanted);
    if (!albums.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted">No cached albums yet. Click “Refresh album cache” after saving a valid Immich URL and API key.</td></tr>`;
      return;
    }
    if (!visibleAlbums.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="muted">No cached albums match the search filter.</td></tr>`;
      return;
    }
    tbody.innerHTML = visibleAlbums.map(album => {
      const id = String(album.id || '');
      let checked = false;
      if (mode === 'selected') checked = selected.has(id);
      else if (mode === 'hide_selected') checked = hidden.has(id);
      else if (mode === 'all') checked = true;
      else checked = (window.IMF_MANAGER?.accountAlbums || []).map(String).includes(id);
      const disabled = mode === 'all' || mode === 'manual' ? 'disabled' : '';
      return `<tr data-album-id="${escapeHtml(id)}" data-search="${escapeHtml(`${album.albumName} ${id}`.toLowerCase())}">
        <td><input type="checkbox" class="album-check" value="${escapeHtml(id)}" ${checked ? 'checked' : ''} ${disabled}></td>
        <td><strong>${escapeHtml(album.albumName || id)}</strong>${album.ownerName ? `<br><span class="muted">${escapeHtml(album.ownerName)}</span>` : ''}</td>
        <td>${album.assetCount ?? ''}</td>
        <td>${album.shared ? 'yes' : 'no'}</td>
        <td><code>${escapeHtml(id)}</code></td>
      </tr>`;
    }).join('');
  }

  function updateFromCheckboxes() {
    const mode = currentMode();
    for (const check of table.querySelectorAll('.album-check')) {
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

  table.addEventListener('change', (event) => {
    if (event.target.classList.contains('album-check')) updateFromCheckboxes();
  });

  for (const radio of document.querySelectorAll('input[name="album_mode"]')) {
    radio.addEventListener('change', renderAlbums);
  }

  if (albumSearch) albumSearch.addEventListener('input', renderAlbums);

  if (selectVisible) selectVisible.addEventListener('click', () => {
    const mode = currentMode();
    if (mode !== 'selected' && mode !== 'hide_selected') return;
    for (const check of table.querySelectorAll('.album-check')) {
      if (!check.disabled) check.checked = true;
    }
    updateFromCheckboxes();
  });

  if (clearVisible) clearVisible.addEventListener('click', () => {
    const mode = currentMode();
    if (mode !== 'selected' && mode !== 'hide_selected') return;
    for (const check of table.querySelectorAll('.album-check')) {
      if (!check.disabled) check.checked = false;
    }
    updateFromCheckboxes();
  });

  const form = document.getElementById('accountForm');
  if (form) form.addEventListener('submit', updateFromCheckboxes);

  renderAlbums();
})();
