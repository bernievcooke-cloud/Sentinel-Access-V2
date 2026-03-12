#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class LocationManager:
    """
    Case-insensitive Location Manager with auto-save.

    Goals:
    - Case-insensitive lookups (via casefold index)
    - Consistent on-disk schema aligned with existing working locations.json:
        {
          "Some Place": {
            "display_name": "Some Place",
            "latitude": -38.123,
            "longitude": 143.456
            "state": "VIC",
          },
          ...
        }

    Compatibility:
    - Can read legacy keys: lat/lon, LAT/LON, lng, etc.
    - Saves using canonical keys: display_name, state, latitude, longitude
    - Preserves any extra fields already present for an existing location, but does NOT auto-inject new ones.
    """

    CANON_LAT_KEYS = ["latitude", "lat", "LAT", "Latitude", "y", "Y"]
    CANON_LON_KEYS = ["longitude", "lon", "lng", "LON", "LNG", "Longitude", "x", "X"]

    def __init__(self, locations_path: str | None = None):
        project_root = Path(__file__).resolve().parents[1]
        self.locations_path = Path(locations_path) if locations_path else (project_root / "config" / "locations.json")

        # display_name -> payload dict
        self._locations: dict[str, dict[str, Any]] = {}
        # casefold_name -> display_name
        self._index: dict[str, str] = {}

        self._load()

    # -----------------------------
    # Public API
    # -----------------------------
    def locations(self) -> list[str]:
        """Return display names in a stable sorted order."""
        return sorted(self._locations.keys(), key=lambda s: s.casefold())

    def get(self, name: str) -> dict[str, Any] | None:
        """Case-insensitive get by name."""
        key = (name or "").casefold()
        display = self._index.get(key)
        if not display:
            return None
        return self._locations.get(display)

    def add_or_update(self, name: str, lat: float, lon: float, **extra_fields: Any) -> str:
        """
        Add a new location or update an existing one (case-insensitive match).
        Returns the stored display name (preserves original casing for existing records).

        Writes canonical coordinate keys:
          latitude / longitude

        IMPORTANT:
        - Does NOT auto-add surf_profile or other extras.
        - If updating an existing location, preserves its existing extra fields.
        - Accepts extra_fields (e.g. state="VIC") and stores them, but will not duplicate lat/lon keys.
        """
        if not name or not name.strip():
            raise ValueError("Location name cannot be empty.")
        display_name_input = name.strip()

        lat = float(lat)
        lon = float(lon)

        key = display_name_input.casefold()
        existing_display = self._index.get(key)
        display = existing_display or display_name_input

        # Start from existing payload if updating (preserve any extra fields already present)
        payload: dict[str, Any] = {}
        if existing_display and existing_display in self._locations:
            payload = dict(self._locations[existing_display])

        # Canonical fields
        payload["display_name"] = display
        payload["latitude"] = lat
        payload["longitude"] = lon

        # Apply extra fields, but prevent schema drift
        # (we do NOT want "lat"/"lon" written anymore)
        for k, v in extra_fields.items():
            if k in ("lat", "lon", "LAT", "LON", "lng", "LNG", "x", "X", "y", "Y"):
                continue
            if k in ("latitude", "longitude"):
                # allow caller to override, but prefer provided lat/lon args above
                continue
            payload[k] = v

        self._locations[display] = payload
        self._index[key] = display

        self._save()
        return display

    def rename(self, old_name: str, new_name: str) -> str:
        old_key = (old_name or "").casefold()
        old_display = self._index.get(old_key)
        if not old_display:
            raise KeyError(f"Location not found: {old_name}")

        new_display = (new_name or "").strip()
        if not new_display:
            raise ValueError("New name cannot be empty.")

        new_key = new_display.casefold()
        existing = self._index.get(new_key)
        if existing and existing != old_display:
            raise ValueError(f"Cannot rename: '{new_name}' would collide with existing '{existing}'.")

        payload = self._locations.pop(old_display)

        # Remove old index entry
        self._index.pop(old_key, None)

        # Update payload display_name if present
        payload["display_name"] = new_display

        # Save under new key
        self._locations[new_display] = payload
        self._index[new_key] = new_display

        self._save()
        return new_display

    def delete(self, name: str) -> bool:
        key = (name or "").casefold()
        display = self._index.get(key)
        if not display:
            return False

        self._locations.pop(display, None)
        self._index.pop(key, None)

        # remove any other index entries that point to this display (rare, but safe)
        for k, v in list(self._index.items()):
            if v == display:
                self._index.pop(k, None)

        self._save()
        return True

    def reload(self) -> None:
        self._load()

    # -----------------------------
    # Internal normalize helpers
    # -----------------------------
    @staticmethod
    def _first_number(payload: dict[str, Any], keys: list[str]) -> float | None:
        for k in keys:
            if k in payload:
                try:
                    v = payload.get(k)
                    if v is None:
                        continue
                    return float(v)
                except Exception:
                    continue
        return None

    def _normalize_payload(self, display_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Normalize to internal canonical keys:
          display_name, latitude, longitude, state (optional) + preserved extras
        """
        out = dict(payload)  # preserve extras

        lat = self._first_number(out, self.CANON_LAT_KEYS)
        lon = self._first_number(out, self.CANON_LON_KEYS)

        # write canonical keys if we found them
        if lat is not None:
            out["latitude"] = lat
        if lon is not None:
            out["longitude"] = lon

        out["display_name"] = out.get("display_name") or display_name

        # remove legacy coordinate keys so we don't keep drifting
        for k in ["lat", "lon", "LAT", "LON", "lng", "LNG", "x", "X", "y", "Y", "Latitude", "Longitude"]:
            if k in out:
                out.pop(k, None)

        return out

    # -----------------------------
    # Internal load/save
    # -----------------------------
    def _load(self) -> None:
        self._locations.clear()
        self._index.clear()

        if not self.locations_path.exists():
            self.locations_path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            return

        raw = self.locations_path.read_text(encoding="utf-8").strip()
        if not raw:
            return

        data = json.loads(raw)

        # Support either dict {"Name": {...}} or list [{"name": "...", ...}]
        if isinstance(data, dict):
            for display_name, payload in data.items():
                if not isinstance(payload, dict):
                    continue
                norm = self._normalize_payload(display_name, payload)
                self._locations[display_name] = norm
                self._index[display_name.casefold()] = display_name

        elif isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                display_name = str(item.get("name", "")).strip()
                if not display_name:
                    continue
                payload = dict(item)
                payload.pop("name", None)

                norm = self._normalize_payload(display_name, payload)
                self._locations[display_name] = norm
                self._index[display_name.casefold()] = display_name

    def _save(self) -> None:
        """
        Saves as a dict keyed by display name.
        Writes atomically (tmp then replace).

        Canonical on-disk schema:
          display_name, state (if present), latitude, longitude, plus any preserved extras.
        """
        self.locations_path.parent.mkdir(parents=True, exist_ok=True)

        cleaned: dict[str, dict[str, Any]] = {}

        for name, payload in sorted(self._locations.items(), key=lambda x: x[0].casefold()):
            if not isinstance(payload, dict):
                continue

            p = dict(payload)

            # Enforce canonical keys exist (if possible)
            p["display_name"] = p.get("display_name") or name

            # Keep only canonical coordinate keys
            lat = self._first_number(p, ["latitude"])
            lon = self._first_number(p, ["longitude"])
            if lat is not None:
                p["latitude"] = float(lat)
            if lon is not None:
                p["longitude"] = float(lon)

            # Remove legacy coordinate keys (just in case something re-added them)
            for k in ["lat", "lon", "LAT", "LON", "lng", "LNG", "x", "X", "y", "Y", "Latitude", "Longitude"]:
                p.pop(k, None)

            cleaned[name] = p

        tmp = self.locations_path.with_suffix(self.locations_path.suffix + ".tmp")
        tmp.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.locations_path)