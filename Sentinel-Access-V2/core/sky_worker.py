"""
Night Sky Report Generator
Generates comprehensive sky forecasts with 3 charts:
1. Tonight's sky clarity
2. Best night for viewing
3. 7-night sky forecast
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
import requests

from config.settings import BASE_OUTPUT

# =============================================
# MOON PHASE LOGIC
# =============================================

def get_moon_phase(d=None):
    """Calculates moon phase and returns name and emoji"""
    if d is None:
        d = datetime.now()
    
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

def check_astro_window(cloud_cover):
    """Determine if sky conditions are good for viewing"""
    if cloud_cover <= 15: return "CLEAR SKY", "⭐"
    elif cloud_cover <= 30: return "MOSTLY CLEAR", "🌙"
    elif cloud_cover <= 60: return "PARTLY CLOUDY", "⛅"
    else: return "CLOUDY", "☁️"

# =============================================
# SKY DATA FETCHING
# =============================================

def fetch_sky_data(lat, lon):
    """Fetch sky data from Open-Meteo API (7 day forecast)"""
    try:
        print(f"\n🌌 FETCHING SKY DATA")
        print(f"   Latitude: {lat}")
        print(f"   Longitude: {lon}")
        
        # Only cloud_cover - no visibility or humidity
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=cloud_cover&forecast_days=7&timezone=auto"
        print(f"   URL: {url}")
        
        print(f"   Sending request...")
        response = requests.get(url, timeout=15)
        
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"   ❌ API returned status {response.status_code}")
            print(f"   Response: {response.text[:500]}")
            return None
        
        data = response.json()
        print(f"   ✅ Response received")
        
        if 'hourly' not in data:
            print(f"   ❌ No 'hourly' key in response")
            return None
        
        hourly_data = data['hourly']
        df = pd.DataFrame(hourly_data)
        df['time'] = pd.to_datetime(df['time'])
        
        print(f"   ✅ DataFrame created: {len(df)} rows")
        print(f"   Columns: {list(df.columns)}")
        
        return df
        
    except requests.exceptions.Timeout:
        print(f"   ❌ TIMEOUT: API server not responding")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ CONNECTION ERROR: {e}")
        return None
    except Exception as e:
        print(f"   ❌ ERROR: {type(e).__name__}: {e}")
        return None

def find_best_viewing_night(df):
    """Find the best night for stargazing in the next 7 days"""
    try:
        df_copy = df.copy()
        df_copy['date'] = df_copy['time'].dt.date
        df_copy['hour'] = df_copy['time'].dt.hour
        
        # Remove None/NaN values
        df_copy = df_copy.dropna(subset=['cloud_cover'])
        
        # Only look at night hours (20:00 to 04:00)
        night_df = df_copy[(df_copy['hour'] >= 20) | (df_copy['hour'] <= 4)]
        
        if len(night_df) == 0:
            print("No night data available")
            return None, 0
        
        # Calculate average cloud cover for each night
        nightly_clouds = night_df.groupby('date')['cloud_cover'].agg(['mean', 'min']).reset_index()
        nightly_clouds.columns = ['date', 'avg_cloud', 'min_cloud']
        
        # Find night with lowest cloud cover (clearest night)
        if len(nightly_clouds) > 0:
            best_idx = nightly_clouds['avg_cloud'].idxmin()
            best_date = nightly_clouds.loc[best_idx, 'date']
            best_clarity = 100 - nightly_clouds.loc[best_idx, 'avg_cloud']
            return best_date, best_clarity
        
        return None, 0
    except Exception as e:
        print(f"Error finding best viewing night: {e}")
        return None, 0

# =============================================
# CHART GENERATION
# =============================================

def generate_tonight_sky_chart(df, location):
    """Chart 1: Tonight's sky clarity"""
    try:
        now = datetime.now()
        night_start = now.replace(hour=20, minute=0, second=0, microsecond=0)
        night_end = now.replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        night_df = df[(df["time"] >= night_start) & (df["time"] <= night_end)].copy()
        
        if len(night_df) == 0:
            night_df = df[df["time"].dt.date == now.date()].copy()
        
        # Remove NaN values
        night_df = night_df.dropna(subset=['cloud_cover'])
        
        if len(night_df) == 0:
            print("No data for tonight's chart")
            return None
        
        fig, ax = plt.subplots(figsize=(10, 3.5))
        
        clarity = 100 - night_df["cloud_cover"]
        ax.plot(night_df["time"], clarity, color="#4b0082", lw=3, label="Sky Clarity %")
        ax.fill_between(night_df["time"], clarity, color="#4b0082", alpha=0.3)
        
        # Mark excellent viewing windows
        for i, row in night_df.iterrows():
            if pd.notna(row['cloud_cover']) and row['cloud_cover'] <= 15:
                ax.scatter(row["time"], 100 - row["cloud_cover"], color="gold", marker="*", s=200, zorder=5, edgecolor='yellow', linewidth=1.5)
        
        ax.axvline(now, color="red", lw=2, ls="--", label="Current Time")
        ax.set_ylabel("Clarity (%)", fontsize=11, fontweight="bold")
        ax.set_title("TONIGHT'S SKY CONDITIONS", fontsize=12, fontweight="bold")
        ax.set_ylim(0, 110)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc="upper left", fontsize=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        plt.xticks(rotation=45, fontsize=9)
        
        plt.tight_layout(pad=0.5)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error generating tonight chart: {e}")
        return None

def generate_best_night_chart(df, location):
    """Chart 2: Best night for viewing"""
    try:
        best_date, _ = find_best_viewing_night(df)
        
        if best_date is None:
            best_date = datetime.now().date() + timedelta(days=1)
        
        best_night_start = datetime.combine(best_date, datetime.min.time()).replace(hour=20)
        best_night_end = best_night_start + timedelta(hours=8)
        
        best_df = df[(df["time"] >= best_night_start) & (df["time"] <= best_night_end)].copy()
        
        # Remove NaN values
        best_df = best_df.dropna(subset=['cloud_cover'])
        
        if len(best_df) == 0:
            print("No data for best night chart")
            return None
        
        fig, ax = plt.subplots(figsize=(10, 3.5))
        
        clarity = 100 - best_df["cloud_cover"]
        ax.plot(best_df["time"], clarity, color="#FFD700", lw=3, label="Sky Clarity %")
        ax.fill_between(best_df["time"], clarity, color="#FFD700", alpha=0.3)
        
        # Mark excellent viewing windows
        for i, row in best_df.iterrows():
            if pd.notna(row['cloud_cover']) and row['cloud_cover'] <= 15:
                ax.scatter(row["time"], 100 - row["cloud_cover"], color="gold", marker="*", s=200, zorder=5, edgecolor='yellow', linewidth=1.5)
        
        ax.set_ylabel("Clarity (%)", fontsize=11, fontweight="bold")
        ax.set_title(f"BEST VIEWING NIGHT: {best_date.strftime('%A, %B %d')}", fontsize=12, fontweight="bold")
        ax.set_ylim(0, 110)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc="upper left", fontsize=10)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        plt.xticks(rotation=45, fontsize=9)
        
        plt.tight_layout(pad=0.5)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error generating best night chart: {e}")
        return None

def generate_weekly_sky_chart(df, location):
    """Chart 3: 7-night sky forecast"""
    try:
        df_copy = df.copy()
        df_copy = df_copy.dropna(subset=['cloud_cover'])
        
        df_copy['date'] = df_copy['time'].dt.date
        df_copy['hour'] = df_copy['time'].dt.hour
        
        # Focus on night hours only
        night_df = df_copy[(df_copy['hour'] >= 20) | (df_copy['hour'] <= 4)]
        
        if len(night_df) == 0:
            print("No night data for weekly chart")
            return None
        
        # Calculate average cloud cover for each night
        nightly = night_df.groupby('date')['cloud_cover'].agg(['mean', 'min']).reset_index()
        nightly.columns = ['date', 'avg_cloud', 'min_cloud']
        nightly['clarity'] = 100 - nightly['avg_cloud']
        
        if len(nightly) == 0:
            print("No nightly data for weekly chart")
            return None
        
        # Identify best night
        best_idx = nightly['avg_cloud'].idxmin()
        
        fig, ax = plt.subplots(figsize=(10, 3.5))
        
        # Bar chart with best night highlighted
        colors_list = ['#FFD700' if i == best_idx else '#4b0082' for i in range(len(nightly))]
        
        x_pos = np.arange(len(nightly))
        bars = ax.bar(x_pos, nightly['clarity'], color=colors_list, alpha=0.7, edgecolor='black', linewidth=1.5)
        
        # Add clarity percentage on top of bars
        for i, (bar, clarity) in enumerate(zip(bars, nightly['clarity'])):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 2,
                    f'{clarity:.0f}%', ha='center', va='bottom', fontsize=9, fontweight='bold')
        
        ax.set_ylabel("Sky Clarity (%)", fontsize=11, fontweight="bold")
        ax.set_xlabel("Date", fontsize=11, fontweight="bold")
        ax.set_title("7-NIGHT SKY FORECAST", fontsize=12, fontweight="bold")
        ax.set_xticks(x_pos)
        ax.set_xticklabels([d.strftime('%a\n%m/%d') for d in nightly['date']], fontsize=9)
        ax.set_ylim(0, 110)
        ax.grid(True, alpha=0.3, axis='y', linestyle='--')
        
        plt.tight_layout(pad=0.5)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf
    except Exception as e:
        print(f"Error generating weekly chart: {e}")
        return None
# =============================================
# PDF GENERATION
# =============================================

def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    """Generate complete night sky report PDF with 3 charts"""
    try:
        print(f"\n{'='*50}")
        print(f"GENERATING SKY REPORT")
        print(f"{'='*50}")
        print(f"Location: {location}")
        print(f"Coordinates: {coords}")
        
        lat, lon = coords
        df = fetch_sky_data(lat, lon)
        
        if df is None or len(df) == 0:
            raise RuntimeError("Failed to fetch sky data or no data returned")
        
        print(f"✅ Data fetched successfully")
        
        # Create location folder
        loc_dir = os.path.join(output_dir, location)
        os.makedirs(loc_dir, exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        filename = f"Sky_Report_{location.replace(' ', '_')}_{timestamp}.pdf"
        save_path = os.path.join(loc_dir, filename)
        
                # Get current conditions
        current_cloud = df.iloc[-1]['cloud_cover']
        
        # Handle None/NaN values
        if pd.isna(current_cloud):
            # Find last valid cloud cover value
            valid_data = df[df['cloud_cover'].notna()]
            if len(valid_data) > 0:
                current_cloud = valid_data.iloc[-1]['cloud_cover']
            else:
                current_cloud = 50  # Default fallback
        
        current_clarity = 100 - current_cloud
        condition, symbol = check_astro_window(current_cloud)
        
        # Moon phase
        phase_name, phase_icon = get_moon_phase()
        
        # Best viewing night
        best_date, best_clarity = find_best_viewing_night(df)
        
        print(f"Current Clarity: {current_clarity:.0f}%")
        print(f"Moon Phase: {phase_name}")
        print(f"Best Night: {best_date}")
        
        # Build PDF
        doc = SimpleDocTemplate(save_path, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm, leftMargin=0.5*cm, rightMargin=0.5*cm)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph("<b>🌌 SENTINEL NIGHT SKY REPORT</b>", styles["Title"]))
        story.append(Spacer(1, 10))
        
        # Info Table
        info_data = [
            ['LOCATION', location.upper()],
            ['COORDINATES', f"{lat:.4f}, {lon:.4f}"],
            ['MOON PHASE', f"{phase_icon} {phase_name}"],
            ['CURRENT CONDITION', f"{symbol} {condition}"],
            ['CURRENT CLARITY', f"{current_clarity:.0f}%"],
            ['BEST VIEWING NIGHT', f"{best_date.strftime('%A') if best_date else 'N/A'} - {best_clarity:.0f}% Clarity" if best_date else "No data"],
            ['GENERATED', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ]
        
        t = Table(info_data, colWidths=[4*cm, 12*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#4b0082')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f5f5f5')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        story.append(t)
        story.append(Spacer(1, 12))
        
        # Chart 1
        story.append(Paragraph("<b>Chart 1: Tonight's Sky Clarity</b>", styles["Normal"]))
        tonight_buf = generate_tonight_sky_chart(df, location)
        if tonight_buf:
            story.append(Image(tonight_buf, width=18*cm, height=5*cm))
        story.append(Spacer(1, 10))
        
        # Chart 2
        story.append(Paragraph("<b>Chart 2: Best Night for Viewing</b>", styles["Normal"]))
        best_buf = generate_best_night_chart(df, location)
        if best_buf:
            story.append(Image(best_buf, width=18*cm, height=5*cm))
        story.append(Spacer(1, 10))
        
        # Chart 3
        story.append(Paragraph("<b>Chart 3: 7-Night Sky Forecast</b>", styles["Normal"]))
        weekly_buf = generate_weekly_sky_chart(df, location)
        if weekly_buf:
            story.append(Image(weekly_buf, width=18*cm, height=5*cm))
        story.append(Spacer(1, 8))
        
        # Analysis
        story.append(Paragraph(
            f"<b>Analysis:</b> Gold stars (⭐) indicate cloud cover <15% (optimal for stargazing). "
            f"Analysis based on night hours (20:00-04:00). Report generated at {datetime.now().strftime('%H:%M')}.",
            styles["Normal"]
        ))
        
        # Build PDF
        doc.build(story)
        print(f"✅ PDF saved: {save_path}")
        print(f"{'='*50}\n")
        return save_path
        
    except Exception as e:
        print(f"\n❌ SKY REPORT GENERATION FAILED")
        print(f"Error: {type(e).__name__}: {e}")
        print(f"{'='*50}\n")
        raise