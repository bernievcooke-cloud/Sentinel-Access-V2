def handle_coordinates(coords):
    if isinstance(coords, dict):
        lat = float(coords.get('latitude', 0))
        lon = float(coords.get('longitude', 0))
    elif isinstance(coords, (list, tuple)) and len(coords) == 2:
        lat, lon = float(coords[0]), float(coords[1])
    else:
        raise Exception(f"Invalid coords format: {coords}")

    return lat, lon 
