#!/usr/bin/env python3
"""
Report Wrapper
Routes reports to the correct worker based on report type
"""

import os

# --- INTEGRATION WITH WORKERS ---
try:
    from core.surf_worker import generate_report as surf_report
    from core.sky_worker import generate_report as sky_report
    from core.weather_worker import generate_report as weather_report
    from core.trip_worker import generate_report as trip_report
except ImportError as e:
    print(f"⚠️ Import error: {e}")
    
    def surf_report(*args, **kwargs):
        raise Exception("Surf Worker not found")
    
    def sky_report(*args, **kwargs):
        raise Exception("Sky Worker not found")
    
    def weather_report(*args, **kwargs):
        raise Exception("Weather Worker not found")
    
    def trip_report(*args, **kwargs):
        raise Exception("Trip Worker not found")


def generate_report(location, report_type, coords, output_dir, trip_details=None):
    """
    Main report generator - routes to correct worker
    
    Args:
        location: Location name or identifier
        report_type: Type of report (surf, sky, weather, trip)
        coords: Tuple of (latitude, longitude)
        output_dir: Directory to save PDF
        trip_details: Optional trip details dict for trip reports
    
    Returns:
        Path to generated PDF file
    """
    
    if report_type.lower() == "surf":
        return surf_report(location, report_type, coords, output_dir)
    
    elif report_type.lower() in ("night", "sky"):
        return sky_report(location, report_type, coords, output_dir)
    
    elif report_type.lower() == "weather":
        return weather_report(location, coords, output_dir)
    
    elif report_type.lower() == "trip":
        return trip_report(location, trip_details, output_dir)
    
    else:
        raise Exception(f"❌ Unknown Report Type: {report_type}")