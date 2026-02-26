from pathlib import Path
import csv

base_path = Path(r'C:\OneDrive\Public Reports A\OUTPUT')
csv_path = r'C:\OneDrive\Public Reports A\locations.csv'

locations = {}
for folder in sorted(base_path.iterdir()):
    if folder.is_dir() and folder.name not in ['__pycache__', '.', '..']:
        coords_file = folder / 'coords.txt'
        if coords_file.exists():
            with open(coords_file) as f:
                lat, lon = f.read().strip().split(',')
                locations[folder.name] = (float(lat), float(lon))

with open(csv_path, 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['Location', 'Latitude', 'Longitude'])
    for loc in sorted(locations.keys()):
        writer.writerow([loc, locations[loc][0], locations[loc][1]])

print('✅ CSV regenerated from lowercase folders')