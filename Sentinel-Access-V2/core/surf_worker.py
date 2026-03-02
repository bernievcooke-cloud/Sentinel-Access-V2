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

# Import settings from config
try:
    from config.settings import BASE_OUTPUT
except ImportError:
    BASE_OUTPUT = r"C:\OneDrive\Public Reports A\OUTPUT"

# ============================================================
# 1. THE ENGINE (Strategy Integrity Maintained)
# ============================================================
def deg_to_compass(deg):
    if deg is None or (isinstance(deg, float) and np.isnan(deg)): return "N/A"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", 
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((deg + 11.25) / 22.5) % 16
    return dirs[idx]

def check_x_factor(row):
    # Fetching values with 0.0 fallback to prevent NoneType crashes
    w = row.get('wind_direction_10m', 0.0)
    s = row.get('swell_wave_height', 0.0)
    t = row.get('tide_height', 0.0)
    
    # Original Strategy Logic Integrity
    if (25 <= w <= 85) and (0.8 <= s <= 2.5) and (t >= 1.4): return "Woolamai"
    if (310 <= w <= 355) and (0.9 <= s <= 2.2) and (0.9 <= t <= 1.7): return "Smiths"
    if (140 <= w <= 220) and (s >= 2.4) and (t >= 1.5): return "Cat Bay"
    return None

def fetch_surf_data(lat, lon):
    try:
        m_url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lon}&hourly=swell_wave_height,swell_wave_direction&timezone=auto"
        w_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wind_speed_10m,wind_direction_10m&timezone=auto"
        
        m_resp = requests.get(m_url).json()
        w_resp = requests.get(w_url).json()
        
        df_m = pd.DataFrame(m_resp['hourly'])
        df_w = pd.DataFrame(w_resp['hourly'])
        
        # Merge and Sanitize
        df = pd.merge(df_m, df_w, on="time", how="inner")
        
        target_cols = ['swell_wave_height', 'swell_wave_direction', 'wind_speed_10m', 'wind_direction_10m']
        for col in target_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

        df['time'] = pd.to_datetime(df['time'])
        df['tide_height'] = 1.35 + 0.85 * np.sin(np.arange(len(df)) * (2 * np.pi / 12.4))
        
        return df
    except Exception as e:
        print(f"Data Fetch Error: {e}")
        return None

# ============================================================
# 2. CHARTING ENGINE
# ============================================================
def generate_daily(df, location_name):
    tomorrow = (datetime.now() + timedelta(days=1)).date()
    day_df = df[df["time"].dt.date == tomorrow].copy()
    
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax2, ax3 = ax1.twinx(), ax1.twinx()
    ax3.spines.right.set_position(("axes", 1.08))

    l1, = ax1.plot(day_df["time"], day_df["swell_wave_height"], color="#1f77b4", lw=3.5, label="Swell (m)")
    l2, = ax2.plot(day_df["time"], day_df["wind_speed_10m"], color="#2ca02c", lw=1.5, ls="--", alpha=0.4, label="Wind (km/h)")
    l3, = ax3.plot(day_df["time"], day_df["tide_height"], color="#17becf", lw=1.5, alpha=0.2, label="Tide (m)")

    for i, row in day_df.iloc[::3].iterrows():
        compass = deg_to_compass(row['wind_direction_10m'])
        ax1.text(row["time"], 0.94, compass, transform=ax1.get_xaxis_transform(), ha='center', fontsize=9, color='darkgreen', fontweight='bold')

    day_df['active_x'] = day_df.apply(check_x_factor, axis=1)
    x_only = day_df.dropna(subset=['active_x'])
    
    if not x_only.empty:
        max_swell = x_only['swell_wave_height'].max()
        for i, row in x_only.iterrows():
            color_choice = "green" if row['swell_wave_height'] == max_swell else "blue"
            ax1.scatter(row["time"], row["swell_wave_height"], color=color_choice, marker="x", s=80, zorder=10)
            ax1.annotate(f"{row['active_x']}", xy=(row["time"], row["swell_wave_height"]), xytext=(0, -15), textcoords="offset points", color=color_choice, fontweight="bold", ha="center", size=8, bbox=dict(facecolor='white', alpha=0.8, edgecolor='none', pad=1))

    ax1.set_ylabel("Swell (m)", color="#1f77b4", fontweight='bold')
    ax1.set_title(f"{location_name.upper()} STRATEGY FOR {tomorrow.strftime('%A %d %b').upper()}", fontweight="bold", fontsize=14)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax1.legend(handles=[l1, l2, l3], loc='upper left')
    ax1.grid(True, alpha=0.15)
    
    buf = BytesIO(); plt.savefig(buf, format='png', dpi=140); plt.close(); buf.seek(0); return buf

def generate_weekly(df, location_name):
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax2, ax3 = ax1.twinx(), ax1.twinx()
    ax3.spines.right.set_position(("axes", 1.10))
    
    l1, = ax1.plot(df['time'], df['swell_wave_height'], color="#1f77b4", lw=2.5, label="Swell (m)")
    l2, = ax2.plot(df['time'], df['wind_speed_10m'], color="#2ca02c", lw=1, ls="--", alpha=0.4, label="Wind (km/h)")
    l3, = ax3.plot(df['time'], df['tide_height'], color="#17becf", lw=0.8, alpha=0.2, label="Tide (m)")

    for i, row in df.iloc[::12].iterrows():
        compass = deg_to_compass(row['wind_direction_10m'])
        ax1.text(row["time"], 0.94, compass, transform=ax1.get_xaxis_transform(), ha='center', fontsize=8, color='darkgreen')

    ax1.set_title(f"7-DAY OUTLOOK: {location_name}", fontweight="bold", fontsize=14)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax1.grid(True, alpha=0.15)
    
    buf = BytesIO(); plt.savefig(buf, format='png', dpi=140); plt.close(); buf.seek(0); return buf

# ============================================================
# 3. PDF BUILDER
# ============================================================
def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    lat, lon = coords
    df = fetch_surf_data(lat, lon)
    
    if df is None:
        raise Exception("API TIMEOUT: Data could not be retrieved.")

    final_folder = os.path.join(output_dir, location)
    if not os.path.exists(final_folder): os.makedirs(final_folder)
    
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filename = f"Surf_Report_{location}_{timestamp}.pdf"
    ppath = os.path.join(final_folder, filename)

    doc = SimpleDocTemplate(ppath, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm)
    styles = getSampleStyleSheet()
    
    t = Table([['STRATEGY PREVIEW', f"LOCATION: {location.upper()}"]], colWidths=[5*cm, 13.5*cm])
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(0,0),colors.black),('TEXTCOLOR',(0,0),(0,0),colors.white),('ALIGN',(0,0),(-1,-1),'CENTER')]))

    story = [
        Paragraph(f"<b>SURF SENTINEL REPORT</b>", styles["Title"]),
        t, Spacer(1, 10),
        Image(generate_daily(df, location), 19*cm, 9*cm), Spacer(1, 10),
        Image(generate_weekly(df, location), 19*cm, 9.5*cm),
        Paragraph(f"<font size=8>Generated for Bernie | {datetime.now().strftime('%H:%M')}</font>", styles["Normal"])
    ]
    doc.build(story)
    
    return ppath
