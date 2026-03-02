<<<<<<< HEAD
cat > surf_worker.py << 'EOF'
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
import os

def generate_report(location, report_type, coords, output_dir):
    """Generate Surf Report - returns PDF path"""
    pdf_filename = f"surf_report_{location.replace(' ', '_')}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)
    
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, f"Surf Report: {location}")
    
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 80, f"Coordinates: {coords[0]:.4f}, {coords[1]:.4f}")
    c.drawString(50, height - 100, "Swell: 2.1m | Condition: EXCELLENT")
    c.drawString(50, height - 120, "Wind: 15 km/h | Tide: High")
    
    c.setFont("Helvetica", 9)
    c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    c.save()
    return pdf_path
=======
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
import os

def generate_report(location, report_type, coords, output_dir):
    """Generate Surf Report - returns PDF path"""
    pdf_filename = f"surf_report_{location.replace(' ', '_')}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)
    
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter;
    
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, f"Surf Report: {location}")
    
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 80, f"Coordinates: {coords[0]:.4f}, {coords[1]:.4f}")
    c.drawString(50, height - 100, "Swell: 2.1m | Condition: EXCELLENT")
    c.drawString(50, height - 120, "Wind: 15 km/h | Tide: High")
    
    c.setFont("Helvetica", 9)
    c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    c.save()
    return pdf_path
>>>>>>> 9343605bf497474c1770bb985ee748d48a5d622a
