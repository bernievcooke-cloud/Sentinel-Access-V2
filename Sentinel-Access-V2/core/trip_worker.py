"""
Trip Report Generator
Generates comprehensive trip reports with distance, fuel cost, and route planning
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
import os
import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in km using Haversine formula"""
    R = 6371  # Earth's radius in km
    lat1_rad = math.radians(float(lat1))
    lat2_rad = math.radians(float(lat2))
    delta_lat = math.radians(float(lat2) - float(lat1))
    delta_lon = math.radians(float(lon2) - float(lon1))
    
    a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    distance = R * c
    return distance

def calculate_fuel_cost(distance_km, fuel_consumption_per_100km=10, fuel_price_per_liter=1.80):
    """
    Calculate fuel cost based on distance
    
    Args:
        distance_km: Distance in kilometers
        fuel_consumption_per_100km: Liters per 100 km (default 10)
        fuel_price_per_liter: Price per liter (default $1.80 AUD)
    
    Returns:
        tuple: (liters_needed, fuel_cost)
    """
    liters_needed = (float(distance_km) / 100) * fuel_consumption_per_100km
    fuel_cost = liters_needed * fuel_price_per_liter
    return liters_needed, fuel_cost

def generate_report(location, report_type, coords, output_dir, trip_details=None):
    """Generate Trip Report PDF with start/end locations and fuel cost calculation"""
    try:
        pdf_filename = f"trip_report_{location.replace(' to ', '_to_')}.pdf"
        pdf_path = os.path.join(output_dir, pdf_filename)
        
        c = canvas.Canvas(pdf_path, pagesize=letter)
        width, height = letter
        
        # Title
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, height - 50, "🚗 TRIP REPORT")
        
        c.setFont("Helvetica", 11)
        y_position = height - 80
        
        if trip_details:
            start_location = trip_details.get('start_location', 'Unknown')
            end_location = trip_details.get('end_location', 'Unknown')
            start_coords = trip_details.get('start_coords', coords)
            end_coords = trip_details.get('end_coords', coords)
            
            # Convert to floats for calculations
            start_coords = (float(start_coords[0]), float(start_coords[1]))
            end_coords = (float(end_coords[0]), float(end_coords[1]))
            
            # Calculate distance
            distance = calculate_distance(start_coords[0], start_coords[1], end_coords[0], end_coords[1])
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
                f"Start Coordinates: {start_coords[0]:.4f}° N, {start_coords[1]:.4f}° E",
                f"",
                f"End Location: {end_location}",
                f"End Coordinates: {end_coords[0]:.4f}° N, {end_coords[1]:.4f}° E",
                f"",
                f"Total Distance: {distance:.2f} km",
                f"Estimated Travel Time: {distance / 100:.1f} hours (at 100 km/h avg)",
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
                "✓ Check your vehicle before departure",
                "✓ Fill up fuel tanks at the start",
                "✓ Take regular breaks every 2 hours",
                "✓ Stay hydrated and maintain alertness",
                "✓ Check weather conditions for your route",
                "✓ Inform someone of your travel plans",
            ]
            
            for tip in tips:
                c.drawString(70, y_position, tip)
                y_position -= 15
        
        # Footer
        c.setFont("Helvetica", 9)
        c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.drawString(50, 15, "Sentinel Access - Trip Report")
        
        c.save()
        print(f"✅ Trip Report created: {pdf_path}")
        return pdf_path
        
    except Exception as e:
        print(f"❌ Error generating trip report: {e}")
        raise
