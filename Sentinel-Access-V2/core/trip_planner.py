(
echo from reportlab.lib.pagesizes import letter
echo from reportlab.pdfgen import canvas
echo from datetime import datetime
echo import os
echo.
echo def generate_report(location, report_type, coords, output_dir):
echo     """Generate Trip Planner PDF"""
echo     pdf_path = os.path.join(output_dir, f"trip_plan_{location.replace(' ', '_')}.pdf"^)
echo     c = canvas.Canvas(pdf_path, pagesize=letter^)
echo     
echo     # Title
echo     c.setFont("Helvetica-Bold", 16^)
echo     c.drawString(50, 750, f"Trip Planner - {location}"^)
echo     
echo     # Trip Info
echo     c.setFont("Helvetica", 12^)
echo     y = 700
echo     trip_info = [
echo         f"Location: {location}",
echo         f"Coordinates: {coords[0]}, {coords[1]}",
echo         f"Vehicle: Recommended Car/SUV",
echo         f"Fuel Type: Petrol/Diesel",
echo         f"Est. Fuel Cost: $50-100",
echo         f"Best Time to Visit: Year-round",
echo         f"Activities: Hiking, Photography, Sightseeing",
echo         f"Accommodation: Hotels, Airbnb, Camping",
echo         f"Generated: {datetime.now().strftime('%%Y-%%m-%%d %%H:%%M:%%S')}"
echo     ]
echo     
echo     for info in trip_info:
echo         c.drawString(70, y, info^)
echo         y -= 20
echo     
echo     c.save(^)
echo     return pdf_path
) > trip_worker.py