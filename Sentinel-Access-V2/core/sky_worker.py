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
from config.settings import BASE_OUTPUT

# ----------------------
# 1. ASTRO LOGIC
# ----------------------
def get_moon_phase(d=None):
    """Calculates moon phase (0-30 days) and returns name and icon."""
    if d is None: d = datetime.now()
    # Conway's Moon Phase Algorithm
    year, month, day = d.year, d.month, d.day
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = a // 4
    c = 2 - a + b
    e = int(365.25 * (year + 4716))
    f = int(30.6001 * (month + 1))
    jd = e + f + day + c - 1524.5
    days_since_new = (jd - 2451549.5) % 29.53
    
    if days_since_new < 1.84: return "New Moon", "🌑"
    elif days_since_new < 5.53: return "Waxing Crescent", "🌒"
    elif days_since_new < 9.22: return "First Quarter", "🌓"
    elif days_since_new < 12.91: return "Waxing Gibbous", "🌔"
    elif days_since_new < 16.61: return "Full Moon", "🌕"
    elif days_since_new < 20.30: return "Waning Gibbous", "🌖"
    elif days_since_new < 23.99: return "Last Quarter", "🌗"
    elif days_since_new < 27.68: return "Waning Crescent", "🌘"
    else: return "New Moon", "🌑"

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
    now = datetime.now()
    day_df = df[df["time"].dt.date == now.date()].copy()
    fig, ax1 = plt.subplots(figsize=(11,5.5))

    ax1.plot(day_df["time"], 100 - day_df["cloud_cover"], color="#4b0082", lw=3, label="Clarity %")
    ax1.fill_between(day_df["time"], 100 - day_df["cloud_cover"], color="#4b0082", alpha=0.1)

    for i, row in day_df.dropna(subset=['cloud_cover']).iterrows():
        if check_astro_window(row):
            ax1.scatter(row["time"], 100 - row["cloud_cover"], color="gold", marker="*", s=100, zorder=5)

    ax1.axvline(now, color="red", lw=2, ls="--", label="Current Time")
    ax1.set_ylim(0,110)
    ax1.set_title(f"ASTRO STRATEGY: {loc_name.upper()}", fontweight="bold", fontsize=15)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=140)
    plt.close()
    buf.seek(0)
    return buf

# ----------------------
# 3. PDF BUILDER (V3.10 Optimized)
# ----------------------
def generate_report(location, coords, output_dir=BASE_OUTPUT):
    lat, lon = coords
    df = fetch_sky_data(lat, lon)
    if df is None: raise RuntimeError("Failed to fetch sky data.")

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