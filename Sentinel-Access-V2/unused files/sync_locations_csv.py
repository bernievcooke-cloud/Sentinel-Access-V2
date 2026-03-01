"""
Sync Locations CSV - Auto-sync between CSV and folder structure
Run this periodically to keep CSV backup in sync
"""

import os
from pathlib import Path
from core.location_manager import LocationManager
from config.settings import BASE_OUTPUT_PATH, CSV_LOCATIONS_PATH

def sync_csv_to_folders():
    """
    Import locations from CSV to folder structure
    Useful when CSV is updated externally
    """
    print("\n📥 SYNCING CSV → FOLDERS")
    print("-" * 50)
    
    manager = LocationManager(BASE_OUTPUT_PATH)
    imported = manager.import_from_csv(CSV_LOCATIONS_PATH)
    
    print(f"\n✅ Sync complete: {len(imported)} new locations added\n")
    return imported

def sync_folders_to_csv():
    """
    Export all locations from folder structure to CSV
    Useful for backup and external sharing
    """
    print("\n📤 SYNCING FOLDERS → CSV")
    print("-" * 50)
    
    manager = LocationManager(BASE_OUTPUT_PATH)
    success = manager.export_to_csv(CSV_LOCATIONS_PATH)
    
    if success:
        print(f"✅ CSV backup saved to: {CSV_LOCATIONS_PATH}\n")
    else:
        print("❌ Failed to sync to CSV\n")
    
    return success

def full_sync():
    """
    Do both: export folders to CSV, then import CSV to folders
    This ensures everything is in sync
    """
    print("\n🔄 FULL SYNC: FOLDERS ↔ CSV")
    print("=" * 50)
    
    # First export folders to CSV (backup current state)
    sync_folders_to_csv()
    
    # Then import CSV to folders (add any missing locations)
    sync_csv_to_folders()
    
    print("=" * 50)
    print("✅ FULL SYNC COMPLETE\n")

if __name__ == "__main__":
    full_sync()