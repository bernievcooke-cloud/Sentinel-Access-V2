#!/usr/bin/env python3
import json
from pathlib import Path
import shutil

# ---------------------------------------------
# PATH TO YOUR LOCATIONS FILE
# ---------------------------------------------
LOC_FILE = Path(r"C:\OneDrive\Sentinel-Access-V2\Sentinel-Access-V2\config\locations.json")

# Legacy keys we want to ACCEPT (read) but NOT keep
LEGACY_LAT_KEYS = ["lat", "LAT", "Latitude", "y", "Y"]
LEGACY_LON_KEYS = ["lon", "LON", "lng", "LNG", "Longitude", "x", "X"]

# Canonical keys we want to KEEP
CANON_LAT_KEY = "latitude"
CANON_LON_KEY = "longitude"


def find_number(payload, keys):
    for k in keys:
        if k in payload:
            try:
                return float(payload[k])
            except Exception:
                pass
    return None


def normalize():
    if not LOC_FILE.exists():
        print(f"ERROR: locations.json not found at: {LOC_FILE}")
        return

    # Backup (another one, just in case)
    backup = LOC_FILE.with_suffix(".backup2.json")
    shutil.copy2(LOC_FILE, backup)
    print(f"Backup created: {backup}")

    data = json.loads(LOC_FILE.read_text(encoding="utf-8"))

    if not isinstance(data, dict):
        print("ERROR: locations.json must be a dict of {name: payload}")
        return

    cleaned = {}
    skipped = []

    for name, payload in data.items():
        if not isinstance(payload, dict):
            skipped.append(name)
            continue

        # Prefer canonical if present
        lat = find_number(payload, [CANON_LAT_KEY]) or find_number(payload, LEGACY_LAT_KEYS)
        lon = find_number(payload, [CANON_LON_KEY]) or find_number(payload, LEGACY_LON_KEYS)

        if lat is None or lon is None:
            skipped.append(name)
            # keep record unchanged (don't destroy it)
            cleaned[name] = dict(payload)
            continue

        new_payload = dict(payload)

        # Ensure canonical keys exist
        new_payload["display_name"] = new_payload.get("display_name", name)
        new_payload[CANON_LAT_KEY] = lat
        new_payload[CANON_LON_KEY] = lon

        # Remove ONLY legacy coordinate keys (do NOT remove canonical)
        for k in LEGACY_LAT_KEYS + LEGACY_LON_KEYS:
            new_payload.pop(k, None)

        cleaned[name] = new_payload

    # Write cleaned
    LOC_FILE.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"locations.json normalized OK. Locations: {len(cleaned)}")
    if skipped:
        print(f"WARNING: {len(skipped)} location(s) missing coords and left unchanged:")
        print(", ".join(skipped))


if __name__ == "__main__":
    normalize()