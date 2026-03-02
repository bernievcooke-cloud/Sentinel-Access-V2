"""
Location Manager - Handles all location operations
Reads from locations.json file
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime

class LocationManager:
    """Manages locations, their coordinates, and available reports"""
    
    def __init__(self, base_output_path):
        """
        Initialize the Location Manager
        
        Args:
            base_output_path: Path to the storage folder
        """
        self.base_path = Path(base_output_path)
        self.locations_file = Path(os.getenv("LOCATIONS_FILE", "./config/locations.json"))
        
        if not self.locations_file.exists():
            print(f"⚠️ locations.json not found at: {self.locations_file}")
    
    def get_all_locations(self):
        """
        Read all locations from locations.json
        
        Returns:
            dict: {location_name: coords_dict, ...}
        """
        locations = {}
        
        try:
            if self.locations_file.exists():
                with open(self.locations_file, 'r') as f:
                    locations = json.load(f)
                print(f"✅ Loaded {len(locations)} locations from JSON")
            else:
                print(f"❌ locations.json not found at {self.locations_file}")
        except Exception as e:
            print(f"❌ Error reading locations.json: {e}")
        
        return locations
    
    def geocode_location(self, search_term):
        """
        Lookup coordinates for a location using OpenStreetMap Nominatim API

        Args:
            search_term: Location name to search for

        Returns:
            dict: {latitude, longitude, display_name, source, verified} or None if not found
        """
        try:
            params = {
                'q': search_term,
                'format': 'json',
                'limit': 1
            }
            headers = {'User-Agent': 'SentinelAccess/1.0 (https://github.com/bernievcooke-cloud/Sentinel-Access)'}
            response = requests.get(
                'https://nominatim.openstreetmap.org/search',
                params=params,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            if data:
                result = data[0]
                return {
                    'latitude': round(float(result['lat']), 6),
                    'longitude': round(float(result['lon']), 6),
                    'display_name': result['display_name'],
                    'source': 'OpenStreetMap Nominatim',
                    'verified': True
                }
            return None

        except requests.RequestException as e:
            print(f"❌ Geocoding network error: {e}")
            return None
        except (KeyError, ValueError) as e:
            print(f"❌ Geocoding response parse error: {e}")
            return None
        except Exception as e:
            print(f"❌ Geocoding error: {e}")
            return None

    def add_location(self, location_name, latitude, longitude, source=None, verified=False):
        """
        Add a new location to locations.json

        Args:
            location_name: Name of location
            latitude: Latitude coordinate
            longitude: Longitude coordinate
            source: Optional source reference (e.g. 'OpenStreetMap Nominatim')
            verified: Whether coordinates have been verified

        Returns:
            bool: True if successful
        """
        try:
            # Read existing locations
            if self.locations_file.exists():
                with open(self.locations_file, 'r') as f:
                    locations = json.load(f)
            else:
                locations = {}

            # Build location entry with optional source metadata
            entry = {
                "latitude": latitude,
                "longitude": longitude
            }
            if source is not None:
                entry["source"] = source
                entry["verified"] = verified

            # Add new location
            locations[location_name] = entry

            # Write back to file
            self.locations_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.locations_file, 'w') as f:
                json.dump(locations, f, indent=2)

            print(f"✅ Location added: {location_name}")
            return True

        except Exception as e:
            print(f"❌ Error adding location: {e}")
            return False
    
    def location_exists(self, location_name):
        """Check if a location exists"""
        locations = self.get_all_locations()
        return location_name in locations
    
    def get_coordinates(self, location_name):
        """
        Get coordinates for a location
        
        Args:
            location_name: Name of location
        
        Returns:
            dict: {latitude, longitude} or None
        """
        locations = self.get_all_locations()
        return locations.get(location_name)
    
    def get_available_reports(self, location_name):
        """
        Get list of available reports for a location
        
        Args:
            location_name: Name of location
        
        Returns:
            dict: {report_type: [list of files], ...}
        """
        reports = {'Surf': [], 'Sky': []}
        
        try:
            # Try to find reports in folder if it exists
            loc_dir = self.base_path / location_name
            if loc_dir.exists():
                for file in loc_dir.iterdir():
                    if file.is_file() and file.suffix == '.pdf':
                        if 'surf' in file.name.lower():
                            reports['Surf'].append(file.name)
                        elif 'sky' in file.name.lower():
                            reports['Sky'].append(file.name)
                
                reports['Surf'].sort(reverse=True)
                reports['Sky'].sort(reverse=True)
        except Exception as e:
            print(f"⚠️ Error getting reports: {e}")
        
        return reports
    
    def get_latest_report(self, location_name, report_type):
        """Get the latest report file for a location and type"""
        reports = self.get_available_reports(location_name)
        
        if reports.get(report_type):
            latest = reports[report_type][0]
            return self.base_path / location_name / latest
        
        return None
    
    def export_to_csv(self, csv_path):
        """Export all locations to CSV file"""
        import csv
        
        try:
            locations = self.get_all_locations()
            
            with open(csv_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Location', 'Latitude', 'Longitude'])
                for loc_name, coords in sorted(locations.items()):
                    lat = coords.get('latitude', '')
                    lon = coords.get('longitude', '')
                    writer.writerow([loc_name, lat, lon])
            
            print(f"✅ CSV exported to: {csv_path}")
            return True
        
        except Exception as e:
            print(f"❌ Error exporting CSV: {e}")
            return False