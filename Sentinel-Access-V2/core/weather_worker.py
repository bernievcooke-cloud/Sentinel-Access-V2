#!/usr/bin/env python3
import os
import requests
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
import matplotlib.ticker

# Import settings from config
try:
    from config.settings import BASE_OUTPUT
except ImportError:
    BASE_OUTPUT = r"C:\OneDrive\Public Reports A\OUTPUT"

# ============================================================
# 1. THE ENGINE (Strategy Integrity Maintained)
# ============================================================
def deg_to_compass(deg):
    if deg is None or (isinstance(deg, float) and np.isnan(deg)): 
        return "N/A"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((deg + 11.25) / 22.5) % 16
    return dirs[idx]

def check_weather_alerts(row):
    """Identify alert conditions for weather data"""
    t = row.get('temperature_2m', 0.0)
    d = row.get('wind_direction_10m', 0.0)
    g = row.get('wind_gusts_10m', 0.0)
    p = row.get('precipitation', 0.0)
    w_code = row.get('weather_code', 0)
    
    # Alert Logic - Maintained from original weather_worker
    alerts = []
    if t > 28 and (d >= 315 or d <= 45):
        alerts.append("fire")
    if w_code in [95, 96, 99]:
        alerts.append("storm")
    if g > 45:
        alerts.append("wind")
    if p >= 1:
        alerts.append("rain")
    
    return alerts if alerts else None

def fetch_weather_data(lat, lon):
    """Fetch hourly and daily weather data from Open-Meteo API"""
    try:
        h_url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                 f"&hourly=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code&timezone=auto&forecast_days=3")
        d_url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                 f"&daily=temperature_2m_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,precipitation_sum,weather_code&timezone=auto&forecast_days=7")
        
        h_resp = requests.get(h_url).json()
        d_resp = requests.get(d_url).json()
        
        h_df = pd.DataFrame(h_resp['hourly'])
        d_df = pd.DataFrame(d_resp['daily'])
        
        # Sanitize hourly data
        for col in ['temperature_2m', 'precipitation', 'wind_speed_10m', 'wind_direction_10m', 'wind_gusts_10m', 'weather_code']:
            if col in h_df.columns:
                h_df[col] = pd.to_numeric(h_df[col], errors='coerce').fillna(0.0)
        
        # Sanitize daily data
        for col in ['temperature_2m_max', 'wind_speed_10m_max', 'wind_gusts_10m_max', 'wind_direction_10m_dominant', 'precipitation_sum', 'weather_code']:
            if col in d_df.columns:
                d_df[col] = pd.to_numeric(d_df[col], errors='coerce').fillna(0.0)
        
        h_df['time'] = pd.to_datetime(h_df['time']).dt.tz_localize(None)
        d_df['time'] = pd.to_datetime(d_df['time']).dt.tz_localize(None)
        
        return h_df, d_df
    except Exception as e:
        print(f"Data Fetch Error: {e}")
        return None, None

# ============================================================
# 2. CHARTING ENGINE
# ============================================================
def generate_daily(df, location_name):
    """Generate hourly weather chart for current day"""
    now_dt = datetime.now()
    start_bound = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_df = df[(df["time"] >= start_bound) & (df["time"] <= start_bound + timedelta(hours=23))].copy()
    
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax_wind = ax1.twinx()
    ax_rain = ax1.twinx()
    ax_rain.spines["right"].set_position(("axes", 1.12))

    # Plot temperature - actual vs forecast
    actual = day_df[day_df["time"] <= now_dt].copy()
    forecast = day_df[day_df["time"] >= now_dt].copy()
    
    l1a, = ax1.plot(actual["time"], actual["temperature_2m"], 'r-', lw=2.5, label="Actual Temp")
    l1f, = ax1.plot(forecast["time"], forecast["temperature_2m"], 'r--', lw=2.5, label="Forecast Temp")
    
    # Plot wind - actual vs forecast
    l2a, = ax_wind.plot(actual["time"], actual["wind_speed_10m"], 'g-', lw=1.5, label="Actual Wind")
    l2f, = ax_wind.plot(forecast["time"], forecast["wind_speed_10m"], 'g--', lw=1.5, label="Forecast Wind")
    
    # Plot rain
    l3, = ax_rain.bar(day_df["time"], day_df["precipitation"], color="blue", alpha=0.2, width=0.04, label="Rain")

    # Wind direction markers and alert markers (every 3 hours)
    for i, row in day_df.iloc[::3].iterrows():
        compass = deg_to_compass(row['wind_direction_10m'])
        ax_wind.annotate(compass, (row["time"], row['wind_speed_10m']), xytext=(0, 7), 
                         textcoords="offset points", ha='center', fontsize=9, fontweight='bold', color='darkgreen')
        
        # Alert markers
        alerts = check_weather_alerts(row)
        if alerts:
            if 'fire' in alerts:
                ax1.scatter(row["time"], row["temperature_2m"], color='red', marker='x', s=120, zorder=5)
            if 'wind' in alerts:
                ax_wind.scatter(row["time"], row["wind_speed_10m"], color='red', marker='x', s=120, zorder=5)
            if 'rain' in alerts:
                ax_rain.scatter(row["time"], row["precipitation"], color='red', marker='x', s=120, zorder=5)

    ax1.axvline(now_dt, color="black", linestyle=":", lw=2)
    ax1.set_ylabel("Temp (°C)", color="red", fontweight="bold")
    ax_wind.set_ylabel("Wind (km/h)", color="darkgreen", fontweight="bold")
    ax_rain.set_ylabel("Rain (mm)", color="blue", fontweight="bold")
    
    ax1.set_title(f"{location_name.upper()} WEATHER FOR {start_bound.strftime('%A %d %b').upper()}", fontweight="bold", fontsize=14)
    ax1.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 3, 6, 9, 12, 15, 18, 21]))
    ax1.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, p: mdates.DateFormatter("%I%p")(x).replace("AM", "A").replace("PM", "P").lstrip("0")))
    ax1.grid(True, alpha=0.15)
    
    ax1.legend([l1a, l1f, l2a, l2f, l3], ['Actual Temp', 'Forecast Temp', 'Actual Wind', 'Forecast Wind', 'Rain'], 
               loc='upper left', fontsize=8)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches="tight", dpi=140)
    plt.close()
    buf.seek(0)
    return buf

def generate_weekly(df, location_name):
    """Generate daily weather chart for 7-day outlook"""
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax_wind = ax1.twinx()
    ax_rain = ax1.twinx()
    ax_rain.spines["right"].set_position(("axes", 1.12))

    # Plot max temperature
    l1, = ax1.plot(df["time"], df["temperature_2m_max"], 'r-', lw=2.5, label="Max Temp")
    
    # Plot max wind
    l2, = ax_wind.plot(df["time"], df["wind_speed_10m_max"], 'g-', lw=1.5, label="Max Wind")
    
    # Plot rain
    l3, = ax_rain.bar(df["time"], df["precipitation_sum"], color="blue", alpha=0.2, width=0.4, label="Rain")

    # Wind direction markers and alert markers
    for i, row in df.iterrows():
        compass = deg_to_compass(row['wind_direction_10m_dominant'])
        ax_wind.annotate(compass, (row["time"], row['wind_speed_10m_max']), xytext=(0, 7), 
                         textcoords="offset points", ha='center', fontsize=8, fontweight='bold', color='darkgreen')
        
        # Alert markers
        alerts = check_weather_alerts(row)
        if alerts:
            if 'fire' in alerts:
                ax1.scatter(row["time"], row["temperature_2m_max"], color='red', marker='x', s=120, zorder=5)
            if 'wind' in alerts:
                ax_wind.scatter(row["time"], row["wind_speed_10m_max"], color='red', marker='x', s=120, zorder=5)
            if 'rain' in alerts:
                ax_rain.scatter(row["time"], row["precipitation_sum"], color='red', marker='x', s=120, zorder=5)

    ax1.set_ylabel("Max Temp (°C)", color="red", fontweight="bold")
    ax_wind.set_ylabel("Max Wind (km/h)", color="darkgreen", fontweight="bold")
    ax_rain.set_ylabel("Rain (mm)", color="blue", fontweight="bold")
    
    ax1.set_title(f"7-DAY WEATHER OUTLOOK: {location_name}", fontweight="bold", fontsize=14)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax1.grid(True, alpha=0.15)
    
    ax1.legend([l1, l2, l3], ['Max Temp', 'Max Wind', 'Rain'], 
               loc='upper left', fontsize=8)
    
    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches="tight", dpi=140)
    plt.close()
    buf.seek(0)
    return buf

# ============================================================
# 3. PDF BUILDER
# ============================================================
def generate_report(location, coords, output_dir=BASE_OUTPUT):
    """Generate weather report with hourly and 7-day charts"""
    lat, lon = coords
    h_df, d_df = fetch_weather_data(lat, lon)
    
    if h_df is None or d_df is None:
        raise Exception("API TIMEOUT: Data could not be retrieved.")

    # Determine alert status from hourly data
    now = datetime.now()
    today_check = h_df[(h_df['time'] >= now.replace(hour=0, minute=0, second=0, microsecond=0)) & 
                       (h_df['time'] <= now + timedelta(hours=24))].copy()
    
    alerts_found = []
    for i, row in today_check.iterrows():
        row_alerts = check_weather_alerts(row)
        if row_alerts:
            alerts_found.extend(row_alerts)
    
    # Build status message
    status = "✓ NORMAL CONDITIONS"
    bg = colors.honeydew
    
    if alerts_found:
        alerts_found = list(set(alerts_found))  # Remove duplicates
        status = "❌ "
        if 'fire' in alerts_found:
            status += "🔥 FIRE ALERT: HEAT & NORTH WIND"
            bg = colors.orange
        elif 'storm' in alerts_found:
            status += "⛈️ STORM ALERT"
            bg = colors.lightsalmon
        elif 'wind' in alerts_found:
            status += "💨 WIND ALERT"
            bg = colors.lightyellow
        elif 'rain' in alerts_found:
            status += "🌧️ RAIN ALERT"
            bg = colors.lightblue
    
    # Create output directory
    final_folder = os.path.join(output_dir, location)
    if not os.path.exists(final_folder):
        os.makedirs(final_folder)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"Weather_Report_{location}_{timestamp}.pdf"
    ppath = os.path.join(final_folder, filename)

    # Build PDF
    doc = SimpleDocTemplate(ppath, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm)
    styles = getSampleStyleSheet()
    
    # Status table
    stat_t = Table([['WEATHER STATUS', status]], colWidths=[4.5*cm, 13.5*cm])
    stat_t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.black),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
        ('BACKGROUND', (1, 0), (1, 0), bg),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold')
    ]))

    story = [
        Paragraph(f"<b>WEATHER SENTINEL REPORT</b>", styles["Title"]),
        stat_t, Spacer(1, 10),
        Image(generate_daily(h_df, location), 19*cm, 9*cm), Spacer(1, 10),
        Image(generate_weekly(d_df, location), 19*cm, 9.5*cm),
        Paragraph(f"<font size=8>Generated for Bernie | {datetime.now().strftime('%H:%M')}</font>", styles["Normal"])
    ]
    doc.build(story)
    
    return ppath

# ============================================================
# 4. EXECUTION
# ============================================================
if __name__ == "__main__":
    # Example usage - customize with your location details
    LOCATION = "Melbourne"
    COORDS = (-37.8136, 144.9631)  # Melbourne coordinates
    
    try:
        report_path = generate_report(LOCATION, COORDS)
        print(f"✓ SUCCESS: Weather report generated as '{os.path.basename(report_path)}'")
    except Exception as e:
        print(f"✗ ERROR: {e}")
