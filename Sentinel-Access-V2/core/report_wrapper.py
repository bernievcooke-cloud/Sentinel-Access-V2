#!/usr/bin/env python3
import os

# --- INTEGRATION WITH WORKERS ---
try:
    from core.surf_worker import generate_report as surf_report
    from core.sky_worker import generate_report as sky_report
    from core.weather_worker import generate_report as weather_report 
except ImportError as e:
    print(f"Import error: {e}")
    def surf_report(*args, **kwargs):
        raise Exception("Surf Worker not found")
    def sky_report(*args, **kwargs):
        raise Exception("Sky Worker not found")

def generate_report(location, report_type, coords, output_dir):
    """
    Main report generator - routes to correct worker
    """
    
    if report_type.lower() == "surf":
        return surf_report(location, report_type, coords, output_dir)
    
    elif report_type.lower() == "night" or report_type.lower() == "sky":
        return sky_report(location, report_type, coords, output_dir)
    
    else:
        raise Exception(f"Unknown Report Type: {report_type}")