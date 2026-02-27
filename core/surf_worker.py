# Updated to handle LocationManager dict format

class LocationManager:
    def __init__(self):
        self.locations = {}

    def add_location(self, name, lat, lon):
        self.locations[name] = {'latitude': lat, 'longitude': lon}

    def get_location(self, name):
        return self.locations.get(name, None)

    def handle_location_dict_format(self, location_dict):
        if 'latitude' in location_dict and 'longitude' in location_dict:
            self.add_location('New Location', location_dict['latitude'], location_dict['longitude'])
        else:
            raise ValueError('Location dict must contain both latitude and longitude keys')