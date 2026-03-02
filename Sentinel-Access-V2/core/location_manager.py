import os
from dotenv import load_dotenv

load_dotenv()

class LocationManager:
    """Manage locations with optional Google Maps integration"""
    
    def __init__(self):
        self.api_key = os.getenv('GOOGLE_MAPS_API_KEY', None)
        self.has_maps = self.api_key is not None
    
    def geocode_location(self, location_name):
        """Convert location name to coordinates (mock if no API)"""
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
            
            # Fallback: Use mock coordinates for known Australian locations
            mock_locations = {
                'bondi beach': {'latitude': -33.8915, 'longitude': 151.2754},
                'noosa heads': {'latitude': -26.3950, 'longitude': 153.0960},
                'birregurra': {'latitude': -38.3333, 'longitude': 142.8333},
                'alice springs': {'latitude': -23.7001, 'longitude': 133.8807},
                'nhulunbuy': {'latitude': -12.2381, 'longitude': 136.7757},
            }
            
            location_lower = location_name.lower().strip()
            if location_lower in mock_locations:
                return mock_locations[location_lower]
            
            # Default fallback
            print(f"⚠️ Location '{location_name}' not found, using Sydney coordinates")
            return {'latitude': -33.8688, 'longitude': 151.2093}
            
        except Exception as e:
            print(f"❌ Geocoding error: {e}")
            return {'latitude': -33.8688, 'longitude': 151.2093}
    
    def get_location_coords(self, location_data):
        """Extract or generate coordinates for a location"""
        if isinstance(location_data, dict):
            if 'latitude' in location_data and 'longitude' in location_data:
                return location_data
        
        # If just a name, geocode it
        if isinstance(location_data, str):
            return self.geocode_location(location_data)
        
        return {'latitude': -33.8688, 'longitude': 151.2093}
