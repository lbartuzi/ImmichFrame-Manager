# New Feature Plan: People Browser

## Goal
Add an interactive people browser to the Account page that lets users discover Immich people by name and face thumbnail, then select them into the `People` field — replacing the current painful manual UUID lookup.

---

## Design Principles (stay consistent with existing project)
- No new frontend framework — vanilla JS only, same as `app.js`
- Dark-theme CSS variables already defined in `style.css` (no new design tokens needed)
- Native `<details>/<summary>` for the accordion — zero JS, semantically correct
- People cards use the same visual language as the album browser (rows → cards with circular avatar)
- The existing `People` textarea stays on the form; the browser simply populates it

---

## Architecture Overview

```
Browser
  └─ GET /api/accounts/<n>/people          (new)  → ImmichClient.list_people()
  └─ <img src="/api/accounts/<n>/people/<id>/thumbnail"> (new) → proxied from Immich
```

Thumbnails **must** be proxied through Flask because Immich requires the `x-api-key` header, which `<img>` tags cannot send.

---

## Files Changed / Added

### 1. `app/immich_client.py` — add `list_people()`

New method on `ImmichClient`:

```python
def list_people(self) -> List[Dict[str, Any]]:
    """
    Returns a sorted list of people dicts: {id, name, birthDate}.
    Handles both legacy array response and v1.106+ {people: [...]} envelope.
    """
    data = self._get("people")
    if isinstance(data, dict):
        raw_list = data.get("people") or data.get("items") or []
    elif isinstance(data, list):
        raw_list = data
    else:
        raw_list = []
    people = []
    for item in raw_list:
        pid = str(item.get("id") or "").strip()
        if not pid:
            continue
        people.append({
            "id": pid,
            "name": str(item.get("name") or "").strip() or "(unnamed)",
            "birthDate": item.get("birthDate"),
        })
    return sorted(people, key=lambda p: p["name"].lower())
```

No caching in ConfigStore — people lists are small and fetched on demand.

---

### 2. `app/main.py` — two new routes

#### `GET /api/accounts/<int:index>/people`
```python
@app.route("/api/accounts/<int:index>/people")
@require_auth
def api_people(index: int) -> Any:
    try:
        people = make_client(index).list_people()
        return jsonify({"ok": True, "people": people})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
```

#### `GET /api/accounts/<int:index>/people/<person_id>/thumbnail`
```python
from flask import Response
import requests as _requests

@app.route("/api/accounts/<int:index>/people/<person_id>/thumbnail")
@require_auth
def api_person_thumbnail(index: int, person_id: str) -> Any:
    try:
        client = make_client(index)
        for url in client._candidate_urls(f"people/{person_id}/thumbnail"):
            try:
                r = _requests.get(url, headers=client.headers, timeout=10, stream=True)
                if r.status_code == 200:
                    return Response(r.content, content_type=r.headers.get("Content-Type", "image/jpeg"))
            except Exception:
                continue
        return ("", 404)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
```

---

### 3. `app/templates/account.html` — new accordion section

Inserted **after** the existing "ImmichFrame account filters" fieldset, **before** the "Album policy" fieldset.

```html
<fieldset class="form-section">
  <details class="people-browser-accordion" id="peopleBrowserAccordion">
    <summary class="people-browser-summary">
      <span>People browser</span>
      <span class="people-browser-count muted" id="peopleBrowserCount">
        {{ (account.People or [])|length }} selected
      </span>
      <span class="people-browser-hint muted">click to expand · select faces to add their IDs to the People field</span>
    </summary>

    <div class="people-browser-body">
      <div class="people-browser-toolbar">
        <input id="peopleSearch" class="people-search-input" placeholder="Filter by name…">
        <button type="button" id="loadPeople" data-people-url="{{ url_for('api_people', index=index) }}" data-thumb-base="{{ url_for('api_person_thumbnail', index=index, person_id='PERSON_ID') }}">Load / Refresh</button>
      </div>
      <div id="peopleStatus" class="notice hidden"></div>
      <div id="peopleGrid" class="people-grid">
        <div class="people-empty muted">Click "Load / Refresh" to fetch people from Immich.</div>
      </div>
    </div>
  </details>
</fieldset>
```

The existing `People` textarea **remains untouched** — the JS writes selected IDs into it.

Bootstrap data injected at bottom of page (alongside existing `window.IMF_MANAGER`):
```js
window.IMF_MANAGER.accountPeople = {{ (account.People or [])|tojson }};
window.IMF_MANAGER.peopleBrowserUrl = "{{ url_for('api_people', index=index) }}";
window.IMF_MANAGER.peopleThumbnailBase = "{{ url_for('api_person_thumbnail', index=index, person_id='PERSON_ID') }}";
```

---

### 4. `app/static/app.js` — new self-contained IIFE block appended to end of file

Key logic:
- `loadPeople()` — `fetch` the people API endpoint, populate `allPeople`, call `renderPeople()`
- `renderPeople()` — build the card grid, mark selected cards, wire checkboxes
- `syncPeopleField()` — writes comma-separated IDs into the existing `[name=People]` textarea
- Search filter on `input` event (same pattern as `albumSearch`)
- Card click toggles selection (whole card is clickable, not just checkbox)
- Selected count badge updates live

Card HTML template (rendered in JS):
```html
<label class="person-card [is-selected]" data-person-id="{id}">
  <input type="checkbox" class="person-check sr-only" value="{id}" [checked]>
  <img class="person-avatar" src="/api/accounts/{n}/people/{id}/thumbnail" alt="{name}" loading="lazy" onerror="this.src='/static/avatar-fallback.svg'">
  <span class="person-name">{name}</span>
</label>
```

---

### 5. `app/static/style.css` — minimal additions (appended)

```css
/* People browser accordion */
.people-browser-accordion { border: none; padding: 0; }
.people-browser-summary {
  display: flex; align-items: center; gap: .75rem;
  cursor: pointer; padding: .5rem 0;
  font-weight: 600; list-style: none;
  user-select: none;
}
.people-browser-summary::-webkit-details-marker { display: none; }
.people-browser-summary::before {
  content: '▶'; font-size: .7rem; color: var(--muted);
  transition: transform .2s;
}
details[open] .people-browser-summary::before { transform: rotate(90deg); }

.people-browser-body { padding-top: .75rem; }
.people-browser-toolbar { display: flex; gap: .75rem; align-items: center; margin-bottom: .75rem; flex-wrap: wrap; }
.people-search-input { flex: 1; min-width: 160px; }
.people-browser-hint { font-size: .78rem; margin-left: auto; }

/* People grid */
.people-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: .75rem;
  max-height: 480px;
  overflow-y: auto;
  padding: .25rem;
}
.person-card {
  display: flex; flex-direction: column; align-items: center;
  gap: .5rem; padding: .75rem .5rem;
  border-radius: 12px;
  border: 2px solid transparent;
  background: var(--panel2);
  cursor: pointer;
  transition: border-color .15s, background .15s;
  text-align: center;
}
.person-card:hover { border-color: var(--primary); }
.person-card.is-selected {
  border-color: var(--ok);
  background: color-mix(in srgb, var(--ok) 12%, var(--panel2));
}
.person-avatar {
  width: 72px; height: 72px;
  border-radius: 50%;
  object-fit: cover;
  background: var(--panel);
  border: 2px solid var(--line);
}
.person-card.is-selected .person-avatar { border-color: var(--ok); }
.person-name {
  font-size: .78rem; color: var(--text);
  word-break: break-word; line-height: 1.3;
}
.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
.people-empty { padding: 1rem; text-align: center; }
.people-browser-count { font-size: .82rem; }
```

Also needed: a small fallback SVG (`/static/avatar-fallback.svg`) — a simple grey circle with a person silhouette, ~200 bytes inline SVG.

---

## What Does NOT Change

| Thing | Status |
|-------|--------|
| `config_store.py` | Untouched |
| `docker_control.py` | Untouched |
| All other templates | Untouched |
| Album browser logic | Untouched |
| General settings form | Untouched |
| Account form fields | Untouched (People textarea stays) |
| Auth / session logic | Untouched |

---

## Implementation Order

1. `immich_client.py` — `list_people()`
2. `main.py` — 2 new routes
3. `style.css` — append people styles + add `avatar-fallback.svg`
4. `account.html` — insert accordion fieldset + extend `window.IMF_MANAGER`
5. `app.js` — append people browser IIFE

Each step is independently testable before moving to the next.

---

## Open Questions / Decisions Needed

- Should the people browser be **open by default** or **collapsed**? (Recommendation: collapsed — keeps the page clean)
- Should selected people count appear **in the summary line** when collapsed? (Recommendation: yes — `3 selected` badge)
- Should loading people be **automatic** on page load, or **manual** (click Load button)? (Recommendation: manual, consistent with album cache refresh behaviour)
