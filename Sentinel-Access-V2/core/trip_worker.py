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
        vehicle = trip_details.get('vehicle_type', 'Not specified')
        fuel = trip_details.get('fuel_type', 'Not specified')
        cost = trip_details.get('fuel_cost', 0)
        duration = trip_details.get('trip_duration', 0)
        accommodation = trip_details.get('accommodation', 'Not specified')
        
        details = [
            f"Location: {location}",
            f"Vehicle Type: {vehicle}",
            f"Fuel Type: {fuel}",
            f"Est. Fuel Cost: ${cost}",
            f"Trip Duration: {duration} days",
            f"Accommodation: {accommodation}",
        ]
    else:
        details = [
            f"Location: {location}",
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
        activities = trip_details['activities']
        if isinstance(activities, list) and len(activities) > 0:
            for activity in activities:
                if y_position < 50:
                    c.showPage()
                    c.setFont("Helvetica", 11)
                    y_position = height - 50
                c.drawString(70, y_position, f"• {activity}")
                y_position -= 15
        else:
            c.drawString(70, y_position, "• No activities specified")
    else:
        default_activities = ["Hiking", "Photography", "Sightseeing"]
        for activity in default_activities:
            c.drawString(70, y_position, f"• {activity}")
            y_position -= 15
    
    # Recommendations Section
    y_position -= 10
    if y_position < 100:
        c.showPage()
        c.setFont("Helvetica-Bold", 12)
        y_position = height - 50
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_position, "Trip Recommendations:")
    
    c.setFont("Helvetica", 11)
    y_position -= 18
    
    recommendations = [
        "• Check weather conditions before departure",
        "• Ensure vehicle maintenance is up to date",
        "• Book accommodations in advance",
        "• Plan daily itinerary and routes",
        "• Pack appropriate gear for activities",
        "• Keep emergency contacts and documents",
        "• Set budget for meals and attractions",
    ]
    
    for rec in recommendations:
        if y_position < 50:
            c.showPage()
            c.setFont("Helvetica", 11)
            y_position = height - 50
        c.drawString(70, y_position, rec)
        y_position -= 15
    
    # Footer
    c.setFont("Helvetica", 9)
    c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    c.drawString(50, 15, "Sentinel Access - Trip Planner Report")
    
    c.save()
    return pdf_path
