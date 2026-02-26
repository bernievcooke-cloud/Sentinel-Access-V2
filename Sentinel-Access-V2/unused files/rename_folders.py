import os
from pathlib import Path

base_path = Path(r'C:\OneDrive\Public Reports A\OUTPUT')

folders_to_rename = []

for folder in base_path.iterdir():
    if folder.is_dir() and folder.name not in ['__pycache__', '.', '..']:
        lowercase_name = folder.name.lower()
        if lowercase_name != folder.name:
            folders_to_rename.append((folder, lowercase_name))

folders_to_rename.sort(key=lambda x: x[0].name)

print(f"Found {len(folders_to_rename)} folders to rename:\n")

for old_folder, new_name in folders_to_rename:
    new_path = base_path / new_name
    try:
        if new_path.exists():
            print(f"⚠️ SKIP: {new_name} already exists")
        else:
            os.rename(str(old_folder), str(new_path))
            print(f"✅ {old_folder.name} → {new_name}")
    except Exception as e:
        print(f"❌ ERROR: {old_folder.name}: {e}")

print("\n✅ All folders renamed to lowercase!")
