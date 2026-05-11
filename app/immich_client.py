from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests


class ImmichError(RuntimeError):
    pass


@dataclass
class ImmichAlbum:
    id: str
    name: str
    asset_count: Optional[int] = None
    shared: bool = False
    owner_name: Optional[str] = None
    raw: Dict[str, Any] | None = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any], shared_hint: bool = False) -> "ImmichAlbum":
        album_id = str(raw.get("id") or raw.get("albumId") or "")
        name = str(raw.get("albumName") or raw.get("name") or raw.get("title") or album_id)
        asset_count = raw.get("assetCount")
        if asset_count is None:
            asset_count = raw.get("assetsCount")
        try:
            asset_count = int(asset_count) if asset_count is not None else None
        except Exception:
            asset_count = None
        owner = raw.get("owner") or {}
        owner_name = None
        if isinstance(owner, dict):
            owner_name = owner.get("name") or owner.get("email")
        if owner_name is None:
            owner_name = raw.get("ownerName") or raw.get("ownerEmail")
        is_shared = bool(
            shared_hint
            or raw.get("shared")
            or raw.get("albumUsers")
            or raw.get("sharedUsers")
            or raw.get("sharedLink")
        )
        return cls(
            id=album_id,
            name=name,
            asset_count=asset_count,
            shared=is_shared,
            owner_name=str(owner_name) if owner_name else None,
            raw=raw,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "albumName": self.name,
            "assetCount": self.asset_count,
            "shared": self.shared,
            "ownerName": self.owner_name,
            "raw": self.raw or {},
        }


class ImmichClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 15):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.timeout = timeout
        if not self.base_url:
            raise ImmichError("ImmichServerUrl is empty")
        if not self.api_key:
            raise ImmichError("ApiKey is empty")

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": "immichframe-manager/1.0",
        }

    def _candidate_urls(self, path: str) -> List[str]:
        path = path.lstrip("/")
        candidates = []
        for prefix in ("api/", ""):
            url = f"{self.base_url}/{prefix}{path}"
            if url not in candidates:
                candidates.append(url)
        return candidates

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        last_error: Exception | None = None
        for url in self._candidate_urls(path):
            try:
                response = requests.get(url, headers=self.headers, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                last_error = exc
                continue
            if response.status_code == 404:
                last_error = ImmichError(f"404 at {url}")
                continue
            if response.status_code >= 400:
                body = response.text[:500]
                raise ImmichError(f"Immich API error {response.status_code}: {body}")
            try:
                return response.json()
            except ValueError as exc:
                raise ImmichError(f"Immich returned non-JSON response from {url}") from exc
        if last_error:
            raise ImmichError(str(last_error))
        raise ImmichError(f"No usable Immich endpoint for {path}")

    def test_connection(self) -> Dict[str, Any]:
        # The album endpoint is stable and needs only album.read permission. If it works, this sidecar can operate.
        albums = self.list_albums()
        return {"ok": True, "album_count": len(albums)}

    def list_albums(self) -> List[Dict[str, Any]]:
        """
        Immich has historically behaved differently around GET /albums and shared albums.
        To avoid surprises, query default + shared=true + shared=false and merge by ID.
        """
        merged: Dict[str, ImmichAlbum] = {}
        calls: List[Tuple[Optional[Dict[str, Any]], bool]] = [
            (None, False),
            ({"shared": "true"}, True),
            ({"shared": "false"}, False),
        ]
        errors = []
        for params, shared_hint in calls:
            try:
                data = self._get("albums", params=params)
            except ImmichError as exc:
                errors.append(str(exc))
                continue
            if not isinstance(data, list):
                continue
            for raw in data:
                if not isinstance(raw, dict):
                    continue
                album = ImmichAlbum.from_raw(raw, shared_hint=shared_hint)
                if album.id:
                    if album.id in merged:
                        existing = merged[album.id]
                        existing.shared = existing.shared or album.shared
                        if existing.asset_count is None:
                            existing.asset_count = album.asset_count
                    else:
                        merged[album.id] = album
        if not merged and errors:
            raise ImmichError("; ".join(errors[:3]))
        return sorted([album.as_dict() for album in merged.values()], key=lambda x: str(x.get("albumName", "")).lower())
