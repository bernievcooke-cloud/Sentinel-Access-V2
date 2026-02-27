def handle_location_manager(location_dict):
    """
    This function handles location data given in a dictionary format.
    Expected format: {"latitude": <value>, "longitude": <value>}.
    """
    latitude = location_dict.get('latitude')
    longitude = location_dict.get('longitude')
    
    if latitude is None or longitude is None:
        raise ValueError('Both latitude and longitude must be provided. ')
    
    # Add your logic to handle the location here
    # For demonstration, we'll just print it out.
    print(f'Handling location with latitude: {latitude}, longitude: {longitude}')
