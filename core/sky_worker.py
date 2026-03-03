import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
import requests

# Import global settings
try:
    from config.settings import BASE_OUTPUT
except ImportError:
    BASE_OUTPUT = r"C:\OneDrive\Public Reports A\OUTPUT"

# ----------------------
# 1. ASTRO LOGIC
# ----------------------
def get_moon_phase(d=None):
    """Calculates moon phase (0-30 days) and returns name and icon."""
    if d is None:
        d = datetime.now()
    
    known_new_moon = datetime(2000, 1, 6)
    days_since = (d - known_new_moon).days
    phase = (days_since % 29.53) / 29.53
    
    if phase < 0.03 or phase > 0.97:
        name, icon = "New Moon", "🌑"
    elif 0.22 < phase < 0.28:
        name, icon = "First Quarter", "🌓"
    elif 0.47 < phase < 0.53:
        name, icon = "Full Moon", "🌕"
    elif 0.72 < phase < 0.78:
        name, icon = "Last Quarter", "🌗"
    elif phase < 0.25:
        name, icon = "Waxing Crescent", "🌒"
    elif phase < 0.5:
        name, icon = "Waxing Gibbous", "🌔"
    elif phase < 0.75:
        name, icon = "Waning Gibbous", "🌖"
    else:
        name, icon = "Waning Crescent", "🌘"
    
    return name, icon

def check_astro_window(row):
    cloud = row['cloud_cover']
    if cloud <= 15: return "CLEAR SKY"
    if cloud <= 30: return "PARTIAL"
    return None

def fetch_sky_data(lat, lon):
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=cloud_cover,visibility,relative_humidity_2m&timezone=auto"
        df = pd.DataFrame(requests.get(url).json()['hourly'])
        df['time'] = pd.to_datetime(df['time'])
        return df
    except Exception as e:
        print(f"Sky data fetch error: {e}")
        return None

# ----------------------
# 2. PLOTTING
# ----------------------
def generate_sky_daily(df, loc_name):
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(df['time'], df['cloud_cover'], color='skyblue', alpha=0.6, label='Cloud Cover')
    ax.set_ylabel('Cloud Cover (%)', fontweight='bold')
    ax.set_title(f"SKY CONDITIONS: {loc_name}", fontweight='bold', fontsize=14)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.grid(True, alpha=0.3)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=140, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf

# ============================================================
# 3. PDF BUILDER
# ============================================================
def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    """Generate night sky report"""
    lat, lon = coords
    df = fetch_sky_data(lat, lon)
    if df is None:
        raise Exception("Failed to fetch sky data.")

    # Folder Handling
    loc_dir = os.path.join(output_dir, location)
    os.makedirs(loc_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"Sky_Report_{location.replace(' ', '_')}_{timestamp}.pdf"
    save_path = os.path.join(loc_dir, filename)

    # Moon Phase Calculation
    phase_name, phase_icon = get_moon_phase()

    doc = SimpleDocTemplate(save_path, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm)
    styles = getSampleStyleSheet()

    # Strategy Table
    t_data = [
        ['SKY STRATEGY', f"TARGET SITE: {location.upper()}"],
        ['MOON PHASE', f"{phase_icon} {phase_name.upper()}"]
    ]
    
    t = Table(t_data, colWidths=[5*cm, 13.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,0),colors.black),
        ('TEXTCOLOR',(0,0),(0,0),colors.white),
        ('BACKGROUND',(0,1),(0,1),colors.indigo),
        ('TEXTCOLOR',(0,1),(0,1),colors.white),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),
        ('GRID',(0,0),(-1,-1),0.5,colors.lightgrey)
    ]))

    story = [
        Paragraph(f"<b>NIGHT SKY SENTINEL REPORT</b>", styles["Title"]),
        t, Spacer(1,15),
        Image(generate_sky_daily(df, location), 19*cm, 10*cm),
        Spacer(1,15),
        Paragraph(f"<b>Astro Analysis:</b> Gold Stars indicate 70%+ Clarity (Optimal for Viewing).<br/>Coords: {coords} | Time: {datetime.now().strftime('%H:%M')}", styles["Normal"])
    ]
    doc.build(story)
    
    return save_path