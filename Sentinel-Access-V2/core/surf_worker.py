"""
Surf Report Generator - Real API Data
Generates comprehensive surf forecasts with 3 charts
Using temporary PNG files that are referenced in PDF
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
import requests
import tempfile
import shutil

from config.settings import BASE_OUTPUT

# =============================================
# FETCH REAL SURF DATA
# =============================================

def fetch_surf_data(lat, lon):
    """Fetch wave data from Open-Meteo API"""
    try:
        print(f"[FETCH] Fetching surf data for {lat}, {lon}")
        
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=wave_height,wave_period&forecast_days=7&timezone=auto"
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data['hourly'])
        df['time'] = pd.to_datetime(df['time'])
        
        df['wave_height'] = pd.to_numeric(df['wave_height'], errors='coerce')
        df['wave_period'] = pd.to_numeric(df['wave_period'], errors='coerce')
        
        print(f"[OK] Got {len(df)} records")
        return df
        
    except Exception as e:
        print(f"[ERROR] Error fetching surf data: {e}")
        return None

# =============================================
# ANALYSIS FUNCTIONS
# =============================================

def get_condition_text(wave_height):
    """Condition for wave height"""
    try:
        wave_height = float(wave_height)
        if wave_height >= 2.0: return "EXCELLENT"
        elif wave_height >= 1.5: return "GOOD"
        elif wave_height >= 1.0: return "FAIR"
        else: return "POOR"
    except:
        return "N/A"

def find_best_swell_day(df):
    """Find day with best average waves"""
    try:
        df_copy = df.copy()
        df_copy['wave_height'] = pd.to_numeric(df_copy['wave_height'], errors='coerce')
        df_copy['date'] = df_copy['time'].dt.date
        df_copy = df_copy.dropna(subset=['wave_height'])
        
        if len(df_copy) == 0:
            return None, 0.0
        
        daily = df_copy.groupby('date')['wave_height'].agg(['mean', 'max'])
        
        if len(daily) == 0:
            return None, 0.0
        
        best_idx = daily['mean'].idxmax()
        best_height = float(daily.loc[best_idx, 'mean'])
        
        return best_idx, best_height
    except Exception as e:
        print(f"[ERROR] find_best_swell_day: {e}")
        return None, 0.0

# =============================================
# CHART 1: TODAY'S CONDITIONS
# =============================================

def generate_today_chart(df, chart_path):
    """Chart 1: Today's wave conditions - saves to file"""
    try:
        now = datetime.now()
        day_df = df[df["time"].dt.date == now.date()].copy()
        
        if len(day_df) == 0:
            day_df = df.head(24).copy()
        
        day_df['wave_height'] = pd.to_numeric(day_df['wave_height'], errors='coerce')
        day_df = day_df.dropna(subset=['wave_height'])
        
        if len(day_df) == 0:
            return False
        
        fig, ax = plt.subplots(figsize=(11, 5.5))
        
        ax.plot(day_df["time"], day_df["wave_height"], color="#1f77b4", lw=3.5, label="Wave Height (m)")
        ax.fill_between(day_df["time"], day_df["wave_height"], alpha=0.3, color="#1f77b4")
        
        good_waves = day_df[day_df['wave_height'] >= 2.0]
        if len(good_waves) > 0:
            ax.scatter(good_waves["time"], good_waves["wave_height"], color="green", marker="x", s=120, zorder=10, lw=3, label="Excellent (>2.0m)")
        
        ax.axvline(now, color="red", lw=2, label="Current Time")
        ax.set_ylabel("Wave Height (m)", fontweight='bold', fontsize=11)
        ax.set_title("TODAY'S WAVE CONDITIONS", fontweight='bold', fontsize=15)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.legend(loc='upper left', fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plt.savefig(chart_path, format='png', dpi=140)
        plt.close(fig)
        
        print(f"[OK] Chart 1 saved: {chart_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Chart 1: {e}")
        import traceback
        traceback.print_exc()
        return False

# =============================================
# CHART 2: BEST SWELL DAY
# =============================================

def generate_best_day_chart(df, chart_path):
    """Chart 2: Best day for surfing - saves to file"""
    try:
        best_date, _ = find_best_swell_day(df)
        
        if best_date is None:
            best_date = datetime.now().date() + timedelta(days=1)
        
        day_df = df[df["time"].dt.date == best_date].copy()
        
        if len(day_df) == 0:
            day_df = df.iloc[24:48].copy()
        
        day_df['wave_height'] = pd.to_numeric(day_df['wave_height'], errors='coerce')
        day_df = day_df.dropna(subset=['wave_height'])
        
        if len(day_df) == 0:
            return False
        
        fig, ax = plt.subplots(figsize=(11, 5.5))
        
        ax.plot(day_df["time"], day_df["wave_height"], color="#ff7f0e", lw=3.5, label="Wave Height (m)")
        ax.fill_between(day_df["time"], day_df["wave_height"], alpha=0.3, color="#ff7f0e")
        
        good_waves = day_df[day_df['wave_height'] >= 2.0]
        if len(good_waves) > 0:
            ax.scatter(good_waves["time"], good_waves["wave_height"], color="red", marker="x", s=120, zorder=10, lw=3, label="Excellent (>2.0m)")
        
        ax.set_ylabel("Wave Height (m)", fontweight='bold', fontsize=11)
        
        if best_date is not None:
            try:
                title_date = best_date.strftime('%A, %B %d')
            except:
                title_date = str(best_date)
        else:
            title_date = "Best Day"
        
        ax.set_title(f"BEST SWELL DAY: {title_date}", fontweight='bold', fontsize=15)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.legend(loc='upper left', fontsize=10)
        ax.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        plt.savefig(chart_path, format='png', dpi=140)
        plt.close(fig)
        
        print(f"[OK] Chart 2 saved: {chart_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Chart 2: {e}")
        import traceback
        traceback.print_exc()
        return False

# =============================================
# CHART 3: 7-DAY FORECAST
# =============================================

def generate_weekly_chart(df, chart_path):
    """Chart 3: 7-day swell forecast - saves to file"""
    try:
        df_copy = df.copy()
        df_copy['wave_height'] = pd.to_numeric(df_copy['wave_height'], errors='coerce')
        df_copy['date'] = df_copy['time'].dt.date
        df_copy = df_copy.dropna(subset=['wave_height'])
        
        daily = df_copy.groupby('date')['wave_height'].agg(['mean', 'max'])
        
        if len(daily) == 0:
            return False
        
        fig, ax = plt.subplots(figsize=(11, 5.5))
        
        best_idx = daily['mean'].idxmax()
        colors_list = ['#ff7f0e' if d == best_idx else '#1f77b4' for d in daily.index]
        
        bars = ax.bar(range(len(daily)), daily['mean'], color=colors_list, alpha=0.7, edgecolor='black', lw=2)
        
        for i, (bar, max_h) in enumerate(zip(bars, daily['max'])):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.1, 
                   f'{max_h:.1f}m', ha='center', fontsize=9, fontweight='bold')
        
        ax.set_ylabel("Average Wave Height (m)", fontweight='bold', fontsize=11)
        ax.set_title("7-DAY SWELL FORECAST", fontweight='bold', fontsize=15)
        ax.set_xticks(range(len(daily)))
        
        date_labels = [d.strftime('%a %d') for d in daily.index]
        ax.set_xticklabels(date_labels, fontsize=10)
        ax.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()
        
        plt.savefig(chart_path, format='png', dpi=140)
        plt.close(fig)
        
        print(f"[OK] Chart 3 saved: {chart_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Chart 3: {e}")
        import traceback
        traceback.print_exc()
        return False

# =============================================
# GENERATE COMPLETE PDF REPORT
# =============================================

def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    """Generate complete surf report PDF"""
    temp_dir = tempfile.mkdtemp()
    
    try:
        print(f"\n{'='*50}")
        print(f"GENERATING SURF REPORT: {location}")
        print(f"{'='*50}")
        
        lat, lon = coords
        df = fetch_surf_data(lat, lon)
        
        if df is None or len(df) == 0:
            raise Exception("No surf data fetched")
        
        # Create output directory
        loc_dir = os.path.join(output_dir, location)
        os.makedirs(loc_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        filename = f"Surf_Report_{location}_{timestamp}.pdf"
        save_path = os.path.join(loc_dir, filename)
        
        # Get current conditions
        try:
            current_height = float(df.iloc[-1]['wave_height'])
        except:
            current_height = 0.0
        
        best_date, best_height = find_best_swell_day(df)
        best_day_text = best_date.strftime('%A') if best_date else "N/A"
        
        print(f"Current height: {current_height:.2f}m")
        print(f"Best day: {best_day_text}, height: {best_height:.2f}m")
        
        # Generate charts to temp files
        print("[INFO] Generating charts...")
        chart1_path = os.path.join(temp_dir, 'chart1.png')
        chart2_path = os.path.join(temp_dir, 'chart2.png')
        chart3_path = os.path.join(temp_dir, 'chart3.png')
        
        c1_ok = generate_today_chart(df, chart1_path)
        c2_ok = generate_best_day_chart(df, chart2_path)
        c3_ok = generate_weekly_chart(df, chart3_path)
        
        # Build PDF
        doc = SimpleDocTemplate(save_path, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        story.append(Paragraph(f"<b>SENTINEL SURF REPORT: {location.upper()}</b>", styles["Title"]))
        
        # Info Table
        t = Table([
            ['LOCATION', location.upper()],
            ['COORDINATES', f"{lat:.4f}, {lon:.4f}"],
            ['CURRENT WAVE', f"{current_height:.1f}m - {get_condition_text(current_height)}"],
            ['BEST SWELL DAY', f"{best_day_text} - {best_height:.1f}m"],
            ['GENERATED', datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        ], colWidths=[5*cm, 13.5*cm])
        
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#1f77b4')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f0f0f0')]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        
        story.append(t)
        story.append(Spacer(1, 10))
        
        # Add Charts if they exist
        if c1_ok and os.path.exists(chart1_path):
            story.append(Image(chart1_path, 19*cm, 9*cm))
            story.append(Spacer(1, 10))
        
        if c2_ok and os.path.exists(chart2_path):
            story.append(Image(chart2_path, 19*cm, 9*cm))
            story.append(Spacer(1, 10))
        
        if c3_ok and os.path.exists(chart3_path):
            story.append(Image(chart3_path, 19*cm, 9*cm))
            story.append(Spacer(1, 10))
        
        story.append(Paragraph(
            f"<font size=8><b>Legend:</b> Green X = Excellent (>2.0m) | Red X = Weekly Peak</font>",
            styles["Normal"]
        ))
        
        # Build PDF
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
    finally:
        # Cleanup temp files AFTER PDF is built
        try:
            shutil.rmtree(temp_dir)
            print(f"[OK] Temp files cleaned up")
        except:
            pass