from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


DEFAULT_SETTINGS: Dict[str, Any] = {
    "General": {
        "AuthenticationSecret": None,
        "DownloadImages": False,
        "RenewImagesDuration": 30,
        "Webcalendars": [],
        "RefreshAlbumPeopleInterval": 12,
        "PhotoDateFormat": "MM/dd/yyyy",
        "ImageLocationFormat": "City,State,Country",
        "WeatherApiKey": "",
        "UnitSystem": "metric",
        "WeatherLatLong": "",
        "Webhook": None,
        "Language": "en",
        "Interval": 45,
        "TransitionDuration": 2,
        "ShowClock": True,
        "ClockFormat": "HH:mm",
        "ClockDateFormat": "eee, MMM d",
        "ShowProgressBar": True,
        "ShowPhotoDate": True,
        "ShowImageDesc": True,
        "ShowPeopleDesc": True,
        "ShowAlbumName": True,
        "ShowImageLocation": True,
        "PrimaryColor": "#f5deb3",
        "SecondaryColor": "#000000",
        "Style": "none",
        "BaseFontSize": "17px",
        "ShowWeatherDescription": True,
        "WeatherIconUrl": "https://openweathermap.org/img/wn/{IconId}.png",
        "ImageZoom": True,
        "ImagePan": False,
        "ImageFill": False,
        "PlayAudio": False,
        "Layout": "splitview",
    },
    "Accounts": [
        {
            "Name": "Frame account",
            "ImmichServerUrl": "http://immich-server:2283",
            "ApiKey": "",
            "ApiKeyFile": None,
            "ImagesFromDate": None,
            "ShowMemories": False,
            "ShowFavorites": False,
            "ShowArchived": False,
            "ShowVideos": False,
            "ImagesFromDays": None,
            "ImagesUntilDate": None,
            "Rating": None,
            "Albums": [],
            "ExcludedAlbums": [],
            "People": [],
            "Tags": [],
        }
    ],
}

DEFAULT_STATE: Dict[str, Any] = {
    "version": 2,
    "accounts": {},
    "last_sync": None,
    "last_error": None,
}

DEFAULT_ACCOUNT_STATE: Dict[str, Any] = {
    "album_mode": "manual",  # manual | all | selected | hide_selected
    "selected_albums": [],
    "hidden_albums": [],
    "auto_sync": False,
    "include_shared": True,
    "include_owned": True,
    "name_prefix": "",
    "last_seen_albums": [],
    "last_applied_albums": [],
    "album_cache": [],
    "last_album_refresh": None,
    "album_cache_error": None,
    "album_cache_source": None,
}

_LOCK = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _chmod_readable(path: Path, mode: int = 0o644) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        # Some mounted filesystems ignore chmod. Do not fail a successful save because of that.
        pass


def _safe_int(value: Any) -> Any:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _listify(value: Any) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, tuple):
        return [str(x).strip() for x in value if str(x).strip()]
    return [x.strip() for x in str(value).split(",") if x.strip()]


def _clean_album(album: Dict[str, Any]) -> Dict[str, Any]:
    """Keep cached album data useful for the UI without storing an entire Immich response blob."""
    return {
        "id": str(album.get("id") or album.get("albumId") or ""),
        "albumName": str(album.get("albumName") or album.get("name") or album.get("title") or album.get("id") or ""),
        "assetCount": album.get("assetCount", album.get("assetsCount")),
        "shared": bool(album.get("shared") or album.get("albumUsers") or album.get("sharedUsers") or album.get("sharedLink")),
        "ownerName": album.get("ownerName") or album.get("ownerEmail"),
    }


def normalize_settings(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    normalized = copy.deepcopy(data)
    normalized.setdefault("General", {})
    normalized.setdefault("Accounts", [])
    if not isinstance(normalized["Accounts"], list):
        normalized["Accounts"] = []
    return normalized


class ConfigStore:
    def __init__(self, settings_file: str, state_file: str, backup_dir: str | None = None):
        self.settings_file = Path(settings_file)
        self.state_file = Path(state_file)
        self.backup_dir = Path(backup_dir) if backup_dir else self.settings_file.parent / "backups"

    def exists(self) -> bool:
        return self.settings_file.exists()

    def load_settings(self) -> Dict[str, Any]:
        with _LOCK:
            if not self.settings_file.exists():
                return copy.deepcopy(DEFAULT_SETTINGS)
            raw = self.settings_file.read_text(encoding="utf-8")
            if not raw.strip():
                return copy.deepcopy(DEFAULT_SETTINGS)
            suffix = self.settings_file.suffix.lower()
            if suffix in {".yaml", ".yml"}:
                if yaml is None:
                    raise RuntimeError("Settings file is YAML but PyYAML is not available")
                data = yaml.safe_load(raw) or {}
            else:
                data = json.loads(raw)
            return normalize_settings(data)

    def save_settings(self, data: Dict[str, Any], make_backup: bool = True) -> None:
        with _LOCK:
            _ensure_parent(self.settings_file)
            data = normalize_settings(data)
            if make_backup and self.settings_file.exists():
                self.backup_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                backup = self.backup_dir / f"{self.settings_file.name}.{ts}.bak"
                backup.write_bytes(self.settings_file.read_bytes())
                _chmod_readable(backup)
            suffix = self.settings_file.suffix.lower()
            if suffix in {".yaml", ".yml"}:
                if yaml is None:
                    raise RuntimeError("Settings file is YAML but PyYAML is not available")
                payload = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
            else:
                payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            fd, tmp_name = tempfile.mkstemp(prefix=self.settings_file.name + ".", dir=str(self.settings_file.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    tmp.write(payload)
                os.replace(tmp_name, self.settings_file)
                _chmod_readable(self.settings_file)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)

    def load_state(self) -> Dict[str, Any]:
        with _LOCK:
            if not self.state_file.exists():
                return copy.deepcopy(DEFAULT_STATE)
            raw = self.state_file.read_text(encoding="utf-8")
            if not raw.strip():
                return copy.deepcopy(DEFAULT_STATE)
            data = json.loads(raw)
            state = copy.deepcopy(DEFAULT_STATE)
            state.update(data if isinstance(data, dict) else {})
            state.setdefault("accounts", {})
            return state

    def save_state(self, data: Dict[str, Any]) -> None:
        with _LOCK:
            _ensure_parent(self.state_file)
            payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
            fd, tmp_name = tempfile.mkstemp(prefix=self.state_file.name + ".", dir=str(self.state_file.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as tmp:
                    tmp.write(payload)
                os.replace(tmp_name, self.state_file)
                _chmod_readable(self.state_file)
            finally:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)

    def ensure_settings(self) -> Dict[str, Any]:
        settings = self.load_settings()
        if not self.settings_file.exists():
            self.save_settings(settings, make_backup=False)
        return settings

    def account_state(self, state: Dict[str, Any], account_index: int) -> Dict[str, Any]:
        key = str(account_index)
        accounts = state.setdefault("accounts", {})
        if key not in accounts or not isinstance(accounts[key], dict):
            accounts[key] = copy.deepcopy(DEFAULT_ACCOUNT_STATE)
        merged = copy.deepcopy(DEFAULT_ACCOUNT_STATE)
        merged.update(accounts[key])
        # Normalize list fields in case the state was edited manually or created by an older version.
        for field in ["selected_albums", "hidden_albums", "last_seen_albums", "last_applied_albums"]:
            merged[field] = _listify(merged.get(field))
        if not isinstance(merged.get("album_cache"), list):
            merged["album_cache"] = []
        accounts[key] = merged
        return merged

    def cache_albums(self, account_index: int, albums: List[Dict[str, Any]], source: str = "immich") -> Dict[str, Any]:
        state = self.load_state()
        policy = self.account_state(state, account_index)
        cleaned = [_clean_album(album) for album in albums]
        cleaned = [album for album in cleaned if album.get("id")]
        cleaned.sort(key=lambda album: str(album.get("albumName", "")).lower())
        policy["album_cache"] = cleaned
        policy["last_album_refresh"] = _now_iso()
        policy["album_cache_error"] = None
        policy["album_cache_source"] = source
        policy["last_seen_albums"] = [str(album["id"]) for album in cleaned]
        self.save_state(state)
        return policy

    def record_album_cache_error(self, account_index: int, message: str) -> None:
        state = self.load_state()
        policy = self.account_state(state, account_index)
        policy["album_cache_error"] = {"at": _now_iso(), "message": message}
        self.save_state(state)

    def add_account(self, name: str = "Frame account") -> int:
        settings = self.load_settings()
        account = copy.deepcopy(DEFAULT_SETTINGS["Accounts"][0])
        account["Name"] = name
        settings.setdefault("Accounts", []).append(account)
        self.save_settings(settings)
        return len(settings["Accounts"]) - 1

    def delete_account(self, index: int) -> None:
        settings = self.load_settings()
        accounts = settings.get("Accounts", [])
        if index < 0 or index >= len(accounts):
            raise IndexError("Account index out of range")
        accounts.pop(index)
        self.save_settings(settings)

        state = self.load_state()
        old_accounts = state.get("accounts", {})
        new_accounts: Dict[str, Any] = {}
        for key, value in old_accounts.items():
            try:
                old_index = int(key)
            except Exception:
                continue
            if old_index < index:
                new_accounts[str(old_index)] = value
            elif old_index > index:
                new_accounts[str(old_index - 1)] = value
        state["accounts"] = new_accounts
        self.save_state(state)

    def update_general_from_form(self, form: Dict[str, Any]) -> None:
        settings = self.load_settings()
        general = settings.setdefault("General", {})
        bool_fields = {
            "DownloadImages", "ShowClock", "ShowProgressBar", "ShowPhotoDate", "ShowImageDesc",
            "ShowPeopleDesc", "ShowAlbumName", "ShowImageLocation", "ShowWeatherDescription",
            "ImageZoom", "ImagePan", "ImageFill", "PlayAudio"
        }
        int_fields = {"RenewImagesDuration", "RefreshAlbumPeopleInterval", "Interval", "TransitionDuration"}
        nullable_fields = {"AuthenticationSecret", "Webhook"}

        handled = set(bool_fields) | int_fields | nullable_fields | {
            "Webcalendars", "PhotoDateFormat", "ImageLocationFormat", "WeatherApiKey", "UnitSystem",
            "WeatherLatLong", "Language", "ClockFormat", "ClockDateFormat", "PrimaryColor",
            "SecondaryColor", "Style", "BaseFontSize", "WeatherIconUrl", "Layout"
        }
        for field in handled:
            if field in bool_fields:
                general[field] = field in form
            elif field in int_fields:
                general[field] = _safe_int(form.get(field))
            elif field == "Webcalendars":
                general[field] = _listify(form.get(field))
            elif field in nullable_fields:
                value = str(form.get(field, "")).strip()
                general[field] = value if value else None
            else:
                general[field] = str(form.get(field, "")).strip()
        self.save_settings(settings)

    def update_account_from_form(self, index: int, form: Dict[str, Any]) -> None:
        settings = self.load_settings()
        accounts = settings.setdefault("Accounts", [])
        if index < 0 or index >= len(accounts):
            raise IndexError("Account index out of range")
        account = accounts[index]

        bool_fields = {"ShowMemories", "ShowFavorites", "ShowArchived", "ShowVideos"}
        nullable_int_fields = {"ImagesFromDays", "Rating"}
        nullable_str_fields = {"ApiKeyFile", "ImagesFromDate", "ImagesUntilDate"}
        simple_str_fields = {"Name", "ImmichServerUrl", "ApiKey"}
        list_fields = {"Albums", "ExcludedAlbums", "People", "Tags"}

        for field in bool_fields:
            account[field] = field in form
        for field in nullable_int_fields:
            account[field] = _safe_int(form.get(field))
        for field in nullable_str_fields:
            value = str(form.get(field, "")).strip()
            account[field] = value if value else None
        for field in simple_str_fields:
            account[field] = str(form.get(field, "")).strip()
        for field in list_fields:
            if field in form:
                account[field] = _listify(form.get(field))

        self.save_settings(settings)

    def update_policy_from_form(self, index: int, form: Dict[str, Any]) -> None:
        state = self.load_state()
        policy = self.account_state(state, index)
        mode = str(form.get("album_mode", "manual")).strip()
        if mode not in {"manual", "all", "selected", "hide_selected"}:
            mode = "manual"
        policy["album_mode"] = mode
        policy["selected_albums"] = _listify(form.get("selected_albums"))
        policy["hidden_albums"] = _listify(form.get("hidden_albums"))
        policy["auto_sync"] = "auto_sync" in form
        policy["include_shared"] = "include_shared" in form
        policy["include_owned"] = "include_owned" in form
        policy["name_prefix"] = str(form.get("name_prefix", "")).strip()
        self.save_state(state)

    def apply_album_policy(self, account_index: int, all_albums: List[Dict[str, Any]]) -> Tuple[List[str], Dict[str, Any]]:
        settings = self.load_settings()
        state = self.load_state()
        policy = self.account_state(state, account_index)
        accounts = settings.get("Accounts", [])
        if account_index < 0 or account_index >= len(accounts):
            raise IndexError("Account index out of range")

        visible_ids: List[str] = []
        for album in all_albums:
            album_id = str(album.get("id") or album.get("albumId") or "").strip()
            if not album_id:
                continue
            name = str(album.get("albumName") or album.get("name") or "")
            prefix = str(policy.get("name_prefix") or "")
            if prefix and not name.startswith(prefix):
                continue
            is_shared = bool(album.get("shared") or album.get("albumUsers") or album.get("sharedUsers"))
            if is_shared and not policy.get("include_shared", True):
                continue
            if not is_shared and not policy.get("include_owned", True):
                continue
            visible_ids.append(album_id)

        seen = set()
        visible_ids = [x for x in visible_ids if not (x in seen or seen.add(x))]

        mode = policy.get("album_mode", "manual")
        selected = set(_listify(policy.get("selected_albums")))
        hidden = set(_listify(policy.get("hidden_albums")))
        account = accounts[account_index]

        if mode == "manual":
            applied = _listify(account.get("Albums"))
        elif mode == "all":
            applied = visible_ids
            account["Albums"] = applied
            account["ExcludedAlbums"] = []
        elif mode == "selected":
            applied = [album_id for album_id in visible_ids if album_id in selected]
            # Preserve manually selected IDs that are temporarily not visible, so a transient API problem does not wipe them.
            for album_id in selected:
                if album_id not in applied:
                    applied.append(album_id)
            account["Albums"] = applied
            account["ExcludedAlbums"] = []
        elif mode == "hide_selected":
            applied = [album_id for album_id in visible_ids if album_id not in hidden]
            account["Albums"] = applied
            account["ExcludedAlbums"] = []
        else:
            applied = _listify(account.get("Albums"))

        policy["last_seen_albums"] = visible_ids
        policy["last_applied_albums"] = applied
        state["last_sync"] = _now_iso()
        state["last_error"] = None
        self.save_settings(settings)
        self.save_state(state)
        return applied, policy

    def record_error(self, message: str) -> None:
        state = self.load_state()
        state["last_error"] = {"at": _now_iso(), "message": message}
        self.save_state(state)
