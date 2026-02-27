#!/usr/bin/env python3
"""
Report Wrapper - Routes reports to correct worker
Handles LocationManager dict format: {latitude, longitude}
"""
import os
from config.settings import BASE_OUTPUT
from config.location_manager import LocationManager

# --- INTEGRATION WITH WORKERS ---
try:
    from core.surf_worker import generate_report as surf_report
    from core.sky_worker import generate_report as sky_report
    from core.weather_worker import generate_report as weather_report 
except ImportError as e:
    print(f"[REPORT_WRAPPER] Import error: {e}")
    import traceback
    traceback.print_exc()
    def surf_report(*args, **kwargs):
        raise Exception("Surf Worker not found")
    def sky_report(*args, **kwargs):
        raise Exception("Sky Worker not found")
    def weather_report(*args, **kwargs):
        raise Exception("Weather Worker not found")

def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    """
    Main report generator - routes to correct worker
    
    Args:
        location: Location name
        report_type: 'Surf', 'Weather', or 'Sky'
        coords: Dict with 'latitude' and 'longitude' keys
        output_dir: Output directory for reports
    
    Returns:
        str: Path to generated PDF or None
    """
    try:
        print(f"[REPORT_WRAPPER] Generating {report_type} for {location}")
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Route to correct worker
        if report_type.lower() == "surf":
            print(f"[REPORT_WRAPPER] Calling surf_report...")
            result = surf_report(location, report_type, coords, output_dir)
        
        elif report_type.lower() == "weather":
            print(f"[REPORT_WRAPPER] Calling weather_report...")
            result = weather_report(location, report_type, coords, output_dir)
        
        elif report_type.lower() == "night" or report_type.lower() == "sky":
            print(f"[REPORT_WRAPPER] Calling sky_report...")
            result = sky_report(location, report_type, coords, output_dir)
        
        else:
            raise Exception(f"[REPORT_WRAPPER] Unknown Report Type: {report_type}")
        
        if result:
            print(f"[REPORT_WRAPPER] ✅ SUCCESS: {result}")
            return result
        else:
            print(f"[REPORT_WRAPPER] ❌ FAILED: Worker returned None")
            return None
            
    except Exception as e:
        print(f"[REPORT_WRAPPER] ❌ EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
        return None
