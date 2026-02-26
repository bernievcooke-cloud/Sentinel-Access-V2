import os
from pathlib import Path
import shutil

base_path = Path(r'C:\OneDrive\Public Reports A\OUTPUT')

for folder in base_path.iterdir():
    if folder.is_dir() and folder.name not in ['__pycache__', '.', '..']:
        lowercase_name = folder.name.lower()
        if lowercase_name != folder.name:
            new_path = base_path / lowercase_name
            
            # If lowercase version exists, remove it first
            if new_path.exists():
                shutil.rmtree(new_path)
                print(f"Removed existing: {lowercase_name}")
            
            # Now rename
            try:
                os.rename(str(folder), str(new_path))
                print(f"✅ {folder.name} → {lowercase_name}")
            except Exception as e:
                print(f"❌ Failed: {folder.name} - {e}")

print("\n✅ Done!")