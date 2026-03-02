"""
Trip Report Generator
Generates comprehensive trip reports with distance, fuel cost, and route planning
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
import os
import math

try:
    from core.location_manager import LocationManager as _LocationManager
except ImportError:
    _LocationManager = None

def extract_coords(coords_data):
    """Extract lat/lon from various formats"""
    try:
        if isinstance(coords_data, dict):
            # Handle both string and actual keys
            lat = coords_data.get('latitude') or coords_data.get('lat')
            lon = coords_data.get('longitude') or coords_data.get('lon')
            
            # Convert to float, handling string values
            if lat is not None:
                lat = float(lat)
            if lon is not None:
                lon = float(lon)
            
            if lat is None or lon is None:
                lat, lon = 0, 0
                
        elif isinstance(coords_data, (list, tuple)):
            lat = float(coords_data[0])
            lon = float(coords_data[1])
        else:
            lat, lon = 0, 0
        return lat, lon
    except Exception as e:
        print(f"Error extracting coords from {coords_data}: {e}")
        return 0, 0

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in km using Haversine formula"""
    R = 6371  # Earth's radius in km
    
    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        return distance
    except Exception as e:
        print(f"Error calculating distance: {e}")
        return 0

def calculate_fuel_cost(distance_km, fuel_consumption_per_100km=10, fuel_price_per_liter=1.80):
    """Calculate fuel cost based on distance"""
    liters_needed = (float(distance_km) / 100) * fuel_consumption_per_100km
    fuel_cost = liters_needed * fuel_price_per_liter
    return liters_needed, fuel_cost

def generate_report(location, report_type, coords, output_dir, trip_details=None):
    """Generate Trip Report PDF with start/end locations and fuel cost calculation"""
    try:
        pdf_filename = f"trip_report_{location.replace(' to ', '_to_').replace(' ', '_').replace('→', 'to')}.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter
        
        # Title
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, height - 50, "🚗 TRIP REPORT")
        
        c.setFont("Helvetica", 11)
        y_position = height - 80
        
        if trip_details:
            start_location = str(trip_details.get('start_location', 'Unknown'))
            end_location = str(trip_details.get('end_location', 'Unknown'))
            start_coords_raw = trip_details.get('start_coords')
            end_coords_raw = trip_details.get('end_coords')
            
            print(f"DEBUG: start_coords_raw = {start_coords_raw}")
            print(f"DEBUG: end_coords_raw = {end_coords_raw}")
            
            # Extract coordinates safely from various formats
            start_lat, start_lon = extract_coords(start_coords_raw)
            end_lat, end_lon = extract_coords(end_coords_raw)
            
            # Use LocationManager to resolve coordinates when missing
            if _LocationManager is not None and (start_lat == 0 and start_lon == 0):
                lm = _LocationManager()
                coord_dict = lm.geocode_location(start_location)
                start_lat = coord_dict.get('latitude', 0)
                start_lon = coord_dict.get('longitude', 0)
                if end_lat == 0 and end_lon == 0:
                    coord_dict = lm.geocode_location(end_location)
                    end_lat = coord_dict.get('latitude', 0)
                    end_lon = coord_dict.get('longitude', 0)
            elif _LocationManager is not None and (end_lat == 0 and end_lon == 0):
                lm = _LocationManager()
                coord_dict = lm.geocode_location(end_location)
                end_lat = coord_dict.get('latitude', 0)
                end_lon = coord_dict.get('longitude', 0)
            
            print(f"DEBUG: start_lat={start_lat}, start_lon={start_lon}")
            print(f"DEBUG: end_lat={end_lat}, end_lon={end_lon}")
            
            # Calculate distance
            distance = calculate_distance(start_lat, start_lon, end_lat, end_lon)
            liters_needed, fuel_cost = calculate_fuel_cost(distance)
            
            # Trip Information Section
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y_position, "Trip Information")
            y_position -= 20
            
            # Divider
            c.line(50, y_position, 500, y_position)
            y_position -= 15
            
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y_position, "Route Details:")
            y_position -= 20
            
            c.setFont("Helvetica", 11)
            trip_info = [
                f"Start Location: {start_location}",
                f"Start Coordinates: {abs(start_lat):.4f}° S, {start_lon:.4f}° E",
                f"",
                f"End Location: {end_location}",
                f"End Coordinates: {abs(end_lat):.4f}° S, {end_lon:.4f}° E",
                f"",
                f"Total Distance: {distance:.2f} km",
                f"Estimated Travel Time: {distance / 80:.1f} hours (at 80 km/h avg)",
            ]
            
            for info in trip_info:
                c.drawString(70, y_position, info)
                y_position -= 18
            
            # Fuel Calculation Section
            y_position -= 20
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y_position, "Fuel Calculation:")
            y_position -= 20
            
            c.setFont("Helvetica", 11)
            fuel_info = [
                f"Fuel Consumption Rate: 10 liters per 100 km",
                f"Distance: {distance:.2f} km",
                f"Estimated Fuel Needed: {liters_needed:.2f} liters",
                f"Fuel Price: $1.80 per liter (AUD)",
                f"Estimated Fuel Cost: ${fuel_cost:.2f}",
            ]
            
            for info in fuel_info:
                c.drawString(70, y_position, info)
                y_position -= 18
            
            # Trip Tips Section
            y_position -= 20
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y_position, "Trip Tips:")
            y_position -= 20
            
            c.setFont("Helvetica", 11)
            tips = [
                "Check your vehicle before departure",
                "Fill up fuel tanks at the start",
                "Take regular breaks every 2 hours",
                "Stay hydrated and maintain alertness",
                "Check weather conditions for your route",
                "Inform someone of your travel plans",
            ]
            
            for tip in tips:
                c.drawString(70, y_position, "✓ " + tip)
                y_position -= 15
        
        # Footer
        c.setFont("Helvetica", 9)
        c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.drawString(50, 15, "Sentinel Access - Trip Report")
        
        c.save()
        print(f"✅ Trip Report created: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        print(f"❌ Error generating trip report: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
