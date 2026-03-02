cat > sky_worker.py << 'EOF'
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from datetime import datetime
import os

def generate_report(location, report_type, coords, output_dir):
    """Generate Night Sky Report - returns PDF path"""
    pdf_filename = f"sky_report_{location.replace(' ', '_')}.pdf"
    pdf_path = os.path.join(output_dir, pdf_filename)
    
    c = canvas.Canvas(pdf_path, pagesize=letter)
    width, height = letter
    
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, f"Night Sky Report: {location}")
    
    c.setFont("Helvetica", 11)
    c.drawString(50, height - 80, f"Coordinates: {coords[0]:.4f}, {coords[1]:.4f}")
    c.drawString(50, height - 100, "Moon: Waxing Gibbous 🌔")
    c.drawString(50, height - 120, "Clarity: 92% | Seeing: Excellent")
    
    c.setFont("Helvetica", 9)
    c.drawString(50, 30, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    c.save()
    return pdf_path
