"""
Weather Report Generator - Working Version
Adapted from proven weather script pattern
Supports multiple locations and report types
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
from io import BytesIO
import requests
import shutil

from config.settings import BASE_OUTPUT

# =============================================
# ANALYSIS FUNCTIONS
# =============================================

def deg_to_nsew(deg):
    """Convert degrees to compass direction"""
    if pd.isna(deg): 
        return ""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[int((deg + 11.25) // 22.5) % 16]

def fetch_weather_data(lat, lon):
    """Fetch weather data from Open-Meteo API"""
    try:
        print(f"[FETCH] Fetching weather for {lat}, {lon}")
        
        h_url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                 f"&hourly=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code"
                 f"&models=best_match&timezone=auto&forecast_days=3")
        
        d_url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                 f"&daily=temperature_2m_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,precipitation_sum,weather_code"
                 f"&models=best_match&timezone=auto&forecast_days=7")
        
        h = requests.get(h_url, timeout=15).json()
        d = requests.get(d_url, timeout=15).json()
        
        print(f"[OK] Hourly: {len(h['hourly']['time'])} records, Daily: {len(d['daily']['time'])} records")
        return pd.DataFrame(h["hourly"]), pd.DataFrame(d["daily"])
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch weather data: {e}")
        return None, None

# =============================================
# ALERT LOGIC
# =============================================

def check_alerts(h_df, hours_ahead=24):
    """Check for weather alerts"""
    try:
        now = datetime.now()
        cutoff = now + timedelta(hours=hours_ahead)
        
        h_df["time"] = pd.to_datetime(h_df["time"]).dt.tz_localize(None)
        next_period = h_df[(h_df["time"] >= now) & (h_df["time"] <= cutoff)]
        
        has_storm = any(next_period['weather_code'].isin([95, 96, 99]))
        has_fire = any((next_period['temperature_2m'] >= 25) & 
                      ((next_period['wind_direction_10m'] >= 315) | (next_period['wind_direction_10m'] <= 45)))
        has_high_wind = any(next_period['wind_gusts_10m'] >= 35)
        
        if has_storm:
            return "THUNDERSTORM", colors.mediumpurple
        elif has_fire:
            return "FIRE RISK", colors.orange
        elif has_high_wind:
            return "HIGH WIND", colors.lightsalmon
        else:
            return "NORMAL", colors.honeydew
    except:
        return "NORMAL", colors.honeydew

# =============================================
# CHART 1: DAILY WEATHER
# =============================================

def generate_daily_chart(h_df):
    """Generate daily weather chart"""
    try:
        h_df = h_df.copy()
        h_df["time"] = pd.to_datetime(h_df["time"]).dt.tz_localize(None)
        
        now_dt = datetime.now()
        today_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_df = h_df[(h_df["time"] >= today_start) & (h_df["time"] <= today_start + timedelta(hours=23, minutes=59))].copy()
        
        if len(day_df) == 0:
            return None
        
        fig, ax1 = plt.subplots(figsize=(11, 5.5))
        ax2, ax4 = ax1.twinx(), ax1.twinx()
        ax4.spines["right"].set_position(("axes", 1.15))
        
        ax1.set_ylabel("Temp (C)", color="red", fontweight="bold")
        ax2.set_ylabel("Wind (km/h)", color="darkgreen", fontweight="bold")
        ax4.set_ylabel("Rain (mm)", color="blue", fontweight="bold")
        
        ax1.plot(day_df["time"], day_df["temperature_2m"], 'r-', lw=2.5)
        ax2.plot(day_df["time"], day_df["wind_speed_10m"], 'g-', lw=1.5, alpha=0.8)
        ax2.fill_between(day_df["time"], day_df["wind_speed_10m"], day_df["wind_gusts_10m"], color='green', alpha=0.1)
        ax4.bar(day_df["time"], day_df["precipitation"], color="blue", alpha=0.2, width=0.02)
        
        # Current time marker
        ax1.axvline(now_dt, color="black", linestyle="--", lw=2)
        ylim = ax1.get_ylim()
        ax1.text(now_dt, ylim[1], f" {now_dt.strftime('%H:%M')}", color='black', 
                 fontweight='bold', va='bottom', ha='left', fontsize=9, bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        # Fire risk shading
        fire_risk = day_df[(day_df["temperature_2m"] >= 25) & 
                          ((day_df["wind_direction_10m"] >= 315) | (day_df["wind_direction_10m"] <= 45))]
        if not fire_risk.empty:
            ax1.axvspan(fire_risk["time"].min(), fire_risk["time"].max(), color='orange', alpha=0.15)
        
        # Annotations every 3 hours
        for _, row in day_df.iterrows():
            if row["time"].hour % 3 == 0:
                label_suffix = "C" if row["time"] < now_dt else "F"
                ax1.annotate(f"{row['temperature_2m']:.1f}°{label_suffix}", 
                            (row["time"], row["temperature_2m"]), 
                            xytext=(0,7), textcoords="offset points", ha='center', size=8, fontweight='bold')
                
                is_n = (row["wind_direction_10m"] >= 315 or row["wind_direction_10m"] <= 45)
                ax2.annotate(deg_to_nsew(row["wind_direction_10m"]), 
                            (row["time"], row["wind_speed_10m"]), 
                            xytext=(0,-15), textcoords="offset points", ha='center', size=8, 
                            fontweight='bold', color='red' if is_n else 'darkgreen')
        
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax1.set_xlim(today_start, today_start + timedelta(hours=23, minutes=59))
        ax1.set_title(f"Daily Weather {today_start.strftime('%d %b')}", fontweight='bold', fontsize=12, pad=15)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches="tight", dpi=130)
        buf.seek(0)
        plt.close(fig)
        
        print(f"[OK] Daily chart generated")
        return buf
    except Exception as e:
        print(f"[ERROR] Daily chart: {e}")
        import traceback
        traceback.print_exc()
        return None

# =============================================
# CHART 2: WEEKLY FORECAST
# =============================================

def generate_weekly_chart(d_df):
    """Generate weekly forecast chart"""
    try:
        d_df = d_df.copy()
        d_df["time"] = pd.to_datetime(d_df["time"]).dt.tz_localize(None)
        
        fig, ax1 = plt.subplots(figsize=(11, 4.5))
        ax2, ax4 = ax1.twinx(), ax1.twinx()
        ax4.spines["right"].set_position(("axes", 1.15))
        
        ax1.plot(d_df["time"], d_df["temperature_2m_max"], 'r-o', lw=2)
        ax2.plot(d_df["time"], d_df["wind_speed_10m_max"], 'g-s', lw=1.2)
        ax4.bar(d_df["time"], d_df["precipitation_sum"], color="blue", alpha=0.15, width=0.4)
        
        for _, row in d_df.iterrows():
            ax1.annotate(f"{row['temperature_2m_max']:.0f}°", 
                        (row["time"], row["temperature_2m_max"]), 
                        xytext=(0,8), textcoords="offset points", ha='center', size=8, fontweight='bold')
            
            is_n = (row["wind_direction_10m_dominant"] >= 315 or row["wind_direction_10m_dominant"] <= 45)
            ax2.annotate(deg_to_nsew(row["wind_direction_10m_dominant"]), 
                        (row["time"], row["wind_speed_10m_max"]), 
                        xytext=(0,10), textcoords="offset points", ha='center', size=8, 
                        color='red' if is_n else 'darkgreen', fontweight='bold')
            
            if (row["temperature_2m_max"] >= 25 and is_n):
                ax1.annotate("FIRE", (row["time"], row["temperature_2m_max"]), 
                            xytext=(0,-20), textcoords="offset points", ha='center', 
                            color='darkorange', fontweight='bold')
            
            if int(row["weather_code"]) in [95, 96, 99]:
                ax1.annotate("STORM", (row["time"], row["temperature_2m_max"]), 
                            xytext=(0,20), textcoords="offset points", ha='center', 
                            color='purple', fontweight='bold')
        
        ax1.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
        ax1.set_title(f"Weekly Forecast", fontweight='bold', fontsize=12, pad=10)
        
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches="tight", dpi=130)
        buf.seek(0)
        plt.close(fig)
        
        print(f"[OK] Weekly chart generated")
        return buf
    except Exception as e:
        print(f"[ERROR] Weekly chart: {e}")
        import traceback
        traceback.print_exc()
        return None

# =============================================
# PDF BUILDER
# =============================================

def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    """Generate complete weather report PDF"""
    try:
        print(f"\n{'='*50}")
        print(f"GENERATING WEATHER REPORT: {location}")
        print(f"{'='*50}")
        
        lat, lon = coords
        h_df, d_df = fetch_weather_data(lat, lon)
        
        if h_df is None or d_df is None:
            raise Exception("Failed to fetch weather data")
        
        # Create output directory
        loc_dir = os.path.join(output_dir, location)
        os.makedirs(loc_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        filename = f"Weather_Report_{location}_{timestamp}.pdf"
        save_path = os.path.join(loc_dir, filename)
        
        # Check alerts
        alert_status, alert_color = check_alerts(h_df)
        
        print(f"Alert status: {alert_status}")
        
        # Generate charts
        print("[INFO] Generating charts...")
        buf_daily = generate_daily_chart(h_df)
        buf_weekly = generate_weekly_chart(d_df)
        
        # Build PDF
        doc = SimpleDocTemplate(save_path, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm, leftMargin=1*cm, rightMargin=2.5*cm)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph(f"<b>SENTINEL WEATHER & WARNINGS REPORT</b>", styles["Title"]))
        
        # Alert status table
        t = Table([['STATUS', f"{alert_status} - {location.upper()}"]], colWidths=[3*cm, 14.5*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.black),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (1, 0), (1, 0), alert_color)
        ]))
        story.append(t)
        story.append(Spacer(1, 12))
        
        # Daily chart
        if buf_daily:
            story.append(Image(buf_daily, 18.5*cm, 9.2*cm))
        story.append(Spacer(1, 15))
        
        # Weekly chart
        if buf_weekly:
            story.append(Image(buf_weekly, 18.5*cm, 7.8*cm))
        
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            f"<font size=7>Report Type: {report_type} | C = Current, F = Forecast | Updated: {datetime.now().strftime('%H:%M')}</font>",
            styles["Normal"]
        ))
        
        doc.build(story)
        
        print(f"[OK] Report saved: {save_path}")
        print(f"{'='*50}\n")
        return save_path
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*50}\n")
        raise