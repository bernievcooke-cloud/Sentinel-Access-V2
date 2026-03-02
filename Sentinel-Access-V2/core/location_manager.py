import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_LOCATIONS_JSON = Path(__file__).parent.parent / 'config' / 'locations.json'


def _load_json_locations():
    """Load locations from config/locations.json, normalising to dict format."""
    try:
        with open(_LOCATIONS_JSON, 'r') as f:
            data = json.load(f)
        result = {}
        for key, val in data.items():
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                result[key] = {
                    'latitude': float(val[0]),
                    'longitude': float(val[1]),
                    'display_name': key,
                }
            elif isinstance(val, dict) and 'latitude' in val and 'longitude' in val:
                entry = dict(val)
                if 'display_name' not in entry:
                    entry['display_name'] = key
                result[key] = entry
        return result
    except Exception as e:
        print(f"⚠️ Could not load locations.json: {e}")
        return {}


class LocationManager:
    """Manage locations with optional Google Maps integration"""

    def __init__(self):
        self.api_key = os.getenv('GOOGLE_MAPS_API_KEY', None)
        self.has_maps = self.api_key is not None
        self._locations = _load_json_locations()

    def geocode_location(self, location_name):
        """Convert location name to coordinates (case-insensitive, loads from JSON)."""
        try:
            if self.has_maps:
                # Use Google Maps API if available
                import googlemaps
                gmaps = googlemaps.Client(key=self.api_key)
                geocode_result = gmaps.geocode(location_name)
                if geocode_result:
                    lat = geocode_result[0]['geometry']['location']['lat']
                    lon = geocode_result[0]['geometry']['location']['lng']
                    return {'latitude': lat, 'longitude': lon}

            search = location_name.lower().strip()

            # Search loaded JSON locations case-insensitively against key and display_name
            for key, entry in self._locations.items():
                if key.lower() == search or entry.get('display_name', '').lower() == search:
                    return dict(entry)

            # Default fallback
            print(f"⚠️ Location '{location_name}' not found, using Sydney coordinates")
            return {'latitude': -33.8688, 'longitude': 151.2093}

        except Exception as e:
            print(f"❌ Geocoding error: {e}")
            return {'latitude': -33.8688, 'longitude': 151.2093}

    def add_location(self, name, lat, lon, state=None, display_name=None,
                     source=None, verified=False):
        """Add a new location to the in-memory store and persist to locations.json."""
        entry = {
            'latitude': float(lat),
            'longitude': float(lon),
        }
        if state:
            entry['state'] = state
        entry['display_name'] = display_name or (f"{name}, {state}" if state else name)
        if source:
            entry['source'] = source
        if verified:
            entry['verified'] = verified

        self._locations[name] = entry

        try:
            with open(_LOCATIONS_JSON, 'r') as f:
                data = json.load(f)
            data[name] = entry
            with open(_LOCATIONS_JSON, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not persist location to JSON: {e}")

    def get_location_coords(self, location_data):
        """Extract or generate coordinates for a location."""
        if isinstance(location_data, dict):
            if 'latitude' in location_data and 'longitude' in location_data:
                return location_data

        # If just a name, geocode it
        if isinstance(location_data, str):
            return self.geocode_location(location_data)

        return {'latitude': -33.8688, 'longitude': 151.2093}
