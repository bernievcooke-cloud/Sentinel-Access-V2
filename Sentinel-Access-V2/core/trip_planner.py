from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import os

def generate_report(location, report_type, coords, output_dir, trip_details=None):
    """Generate Trip Planner PDF with detailed trip information"""
    
    pdf_filename = f"trip_plan_{location.replace(' ', '_')}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)
    
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    # Title
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, f"Trip Planner: {location}")
    
    # Coordinates
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 70, f"Coordinates: {coords[0]:.4f}, {coords[1]:.4f}")
    
    # Trip Details Section
    c.setFont("Helvetica-Bold", 12)
    y_position = height - 100
    c.drawString(50, y_position, "Trip Details:")
    
    c.setFont("Helvetica", 11)
    y_position -= 20
    
    if trip_details:
        details = [
            f"Vehicle Type: {trip_details.get('vehicle_type', 'Not specified')}",
            f"Fuel Type: {trip_details.get('fuel_type', 'Not specified')}",
            f"Est. Fuel Cost: ${trip_details.get('fuel_cost', 0)}",
            f"Trip Duration: {trip_details.get('trip_duration', 0)} days",
            f"Accommodation: {trip_details.get('accommodation', 'Not specified')}",
        ]
    else:
        details = [
            "Vehicle Type: Car/SUV",
            "Fuel Type: Petrol/Diesel",
            "Est. Fuel Cost: $50-100",
            "Trip Duration: 3 days",
            "Accommodation: Hotel",
        ]
    
    for detail in details:
        c.drawString(70, y_position, detail)
        y_position -= 18
    
    # Activities Section
    y_position -= 10
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_position, "Planned Activities:")
    
    c.setFont("Helvetica", 11)
    y_position -= 18
    
    if trip_details and trip_details.get('activities'):
        for activity in trip_details['activities']:
            c.drawString(70, y_position, f"• {activity}")
            y_position -= 15
    else:
        activities = ["Hiking", "Photography", "Sightseeing"]
        for activity in activities:
            c.drawString(70, y_position, f"• {activity}")
            y_position -= 15
    
    # Footer
    c.setFont("Helvetica", 9)
    c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    c.save()
    return pdf_path
