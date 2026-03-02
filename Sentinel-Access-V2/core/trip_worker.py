#!/usr/bin/env python3
"""
Trip Report Generator
Generates comprehensive trip reports with distance, fuel cost, and route planning
Maintains consistent structure with weather_worker and surf_worker
"""

import os
import math
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

# Import LocationManager if available
try:
    from core.location_manager import LocationManager as _LocationManager
except ImportError:
    _LocationManager = None

# ============================================================
# 1. THE ENGINE (Strategy Integrity Maintained)
# ============================================================
def extract_coords(coords_data):
    """Extract lat/lon from various formats"""
    try:
        if isinstance(coords_data, dict):
            # Handle both string and actual keys
            lat = coords_data.get('latitude') or coords_data.get('lat')
            lon = coords_data.get('longitude') or coords_data.get('lon')
            
            # Convert to float, handling string values
            if lat is not None:
                lat = float(lat)
            if lon is not None:
                lon = float(lon)
            
            if lat is None or lon is None:
                lat, lon = 0, 0
                
        elif isinstance(coords_data, (list, tuple)):
            lat = float(coords_data[0])
            lon = float(coords_data[1])
        else:
            lat, lon = 0, 0
        return lat, lon
    except Exception as e:
        print(f"Error extracting coords from {coords_data}: {e}")
        return 0, 0

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate distance between two coordinates in km using Haversine formula"""
    R = 6371  # Earth's radius in km
    
    try:
        lat1 = float(lat1)
        lon1 = float(lon1)
        lat2 = float(lat2)
        lon2 = float(lon2)
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c
        return distance
    except Exception as e:
        print(f"Error calculating distance: {e}")
        return 0

def calculate_fuel_cost(distance_km, fuel_consumption_per_100km=10, fuel_price_per_liter=1.80):
    """Calculate fuel cost based on distance"""
    liters_needed = (float(distance_km) / 100) * fuel_consumption_per_100km
    fuel_cost = liters_needed * fuel_price_per_liter
    return liters_needed, fuel_cost

def resolve_missing_coords(start_location, start_lat, start_lon, end_location, end_lat, end_lon):
    """Use LocationManager to geocode locations with missing coordinates"""
    if _LocationManager is None:
        return start_lat, start_lon, end_lat, end_lon
    
    lm = _LocationManager()
    
    if start_lat == 0 and start_lon == 0:
        coord_dict = lm.geocode_location(start_location)
        start_lat = coord_dict.get('latitude', 0)
        start_lon = coord_dict.get('longitude', 0)
    
    if end_lat == 0 and end_lon == 0:
        coord_dict = lm.geocode_location(end_location)
        end_lat = coord_dict.get('latitude', 0)
        end_lon = coord_dict.get('longitude', 0)
    
    return start_lat, start_lon, end_lat, end_lon

def check_trip_alerts(distance, fuel_cost, travel_hours):
    """Identify alert conditions for trip data"""
    alerts = []
    
    # Long distance alert (>1000 km)
    if distance > 1000:
        alerts.append("long_distance")
    
    # Extended travel time alert (>12 hours)
    if travel_hours > 12:
        alerts.append("extended_travel")
    
    # High fuel cost alert (>$100)
    if fuel_cost > 100:
        alerts.append("high_cost")
    
    return alerts if alerts else None

# ============================================================
# 2. CHARTING ENGINE
# ============================================================
def generate_daily(trip_data):
    """Generate trip summary chart"""
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(11, 8))
    
    # Extract data
    distance = trip_data.get('distance', 0)
    fuel_needed = trip_data.get('fuel_needed', 0)
    fuel_cost = trip_data.get('fuel_cost', 0)
    travel_hours = trip_data.get('travel_hours', 0)
    start_loc = trip_data.get('start_location', 'Unknown')
    end_loc = trip_data.get('end_location', 'Unknown')
    
    # Chart 1: Distance Breakdown (pie)
    segments = [distance * 0.25, distance * 0.25, distance * 0.50]
    labels = ['First Quarter', 'Second Quarter', 'Final Half']
    colors_pie = ['#ff9999', '#66b3ff', '#99ff99']
    ax1.pie(segments, labels=labels, colors=colors_pie, autopct='%1.1f%%', startangle=90)
    ax1.set_title(f'Distance Breakdown\n{distance:.1f} km', fontweight='bold', fontsize=11)
    
    # Chart 2: Fuel & Cost
    categories = ['Fuel (L)', 'Cost (AUD)']
    values = [fuel_needed, fuel_cost / 10]  # Scale cost for visibility
    bars = ax2.bar(categories, values, color=['#1f77b4', '#ff7f0e'], alpha=0.7, edgecolor='black', linewidth=1.5)
    ax2.set_ylabel('Value', fontweight='bold')
    ax2.set_title('Fuel & Cost Summary', fontweight='bold', fontsize=11)
    ax2.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}', ha='center', va='bottom', fontweight='bold')
    
    # Chart 3: Travel Profile
    time_segments = np.linspace(0, travel_hours, int(travel_hours) + 1)
    distance_per_hour = distance / travel_hours if travel_hours > 0 else 0
    cumulative_distance = time_segments * distance_per_hour
    
    ax3.plot(time_segments, cumulative_distance, 'g-', lw=3, marker='o', markersize=6)
    ax3.fill_between(time_segments, cumulative_distance, alpha=0.2, color='green')
    ax3.set_xlabel('Time (hours)', fontweight='bold')
    ax3.set_ylabel('Distance (km)', fontweight='bold')
    ax3.set_title(f'Travel Progress (Avg {distance_per_hour:.1f} km/h)', fontweight='bold', fontsize=11)
    ax3.grid(True, alpha=0.3)
    
    # Chart 4: Trip Information (text box)
    ax4.axis('off')
    info_text = f"""
    TRIP SUMMARY
    
    Route: {start_loc} → {end_loc}
    
    Total Distance: {distance:.2f} km
    Estimated Travel: {travel_hours:.1f} hours
    Average Speed: 80 km/h
    
    Fuel Consumption: 10 L/100km
    Fuel Needed: {fuel_needed:.2f} liters
    Fuel Cost @ $1.80/L: ${fuel_cost:.2f}
    
    Break Recommendation: Every 2 hours
    """
    ax4.text(0.1, 0.5, info_text, fontsize=10, verticalalignment='center',
            family='monospace', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=140, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf

def generate_weekly(trip_data):
    """Generate detailed itinerary/waypoint chart"""
    distance = trip_data.get('distance', 0)
    travel_hours = trip_data.get('travel_hours', 0)
    start_loc = trip_data.get('start_location', 'Unknown')
    end_loc = trip_data.get('end_location', 'Unknown')
    
    # Generate waypoint data
    num_waypoints = 6
    waypoint_distances = np.linspace(0, distance, num_waypoints)
    waypoint_times = np.linspace(0, travel_hours, num_waypoints)
    break_points = [waypoint_times[i] for i in range(1, len(waypoint_times)) if (i % 2) == 0]
    
    fig, ax1 = plt.subplots(figsize=(11, 5.5))
    ax2 = ax1.twinx()
    
    # Main distance line
    l1, = ax1.plot(waypoint_times, waypoint_distances, 'b-', lw=3, marker='o', markersize=8, label='Route Progress')
    
    # Break point markers
    if break_points:
        break_distances = [distance * (t / travel_hours) for t in break_points]
        l2, = ax2.plot(break_points, [1] * len(break_points), 'rs', markersize=12, label='Recommended Breaks', linestyle='none')
        for t, d in zip(break_points, break_distances):
            ax1.annotate('BREAK', xy=(t, d), xytext=(0, 20), textcoords='offset points',
                        ha='center', fontweight='bold', color='red', fontsize=9,
                        bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7))
    
    ax1.set_xlabel('Time (hours)', fontweight='bold')
    ax1.set_ylabel('Distance (km)', color='blue', fontweight='bold')
    ax1.set_title(f'DETAILED TRIP ITINERARY: {start_loc} → {end_loc}', fontweight='bold', fontsize=14)
    ax1.grid(True, alpha=0.3)
    
    # Shade break zones
    for break_time in break_points:
        ax1.axvspan(break_time - 0.1, break_time + 0.5, alpha=0.1, color='red')
    
    ax2.set_ylabel('Break Points', color='red', fontweight='bold')
    ax2.set_yticks([])
    
    ax1.legend([l1], ['Route Progress'], loc='upper left', fontsize=10)
    
    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=140, bbox_inches='tight')
    plt.close()
    buf.seek(0)
    return buf

# ============================================================
# 3. PDF BUILDER
# ============================================================
def generate_report(location, trip_details, output_dir=BASE_OUTPUT):
    """Generate comprehensive trip report with distance, fuel cost, and route planning"""
    try:
        # Extract trip information
        start_location = str(trip_details.get('start_location', 'Unknown'))
        end_location = str(trip_details.get('end_location', 'Unknown'))
        start_coords_raw = trip_details.get('start_coords')
        end_coords_raw = trip_details.get('end_coords')
        
        # Extract coordinates
        start_lat, start_lon = extract_coords(start_coords_raw)
        end_lat, end_lon = extract_coords(end_coords_raw)
        
        # Resolve missing coordinates using LocationManager
        start_lat, start_lon, end_lat, end_lon = resolve_missing_coords(
            start_location, start_lat, start_lon,
            end_location, end_lat, end_lon
        )
        
        # Calculate trip metrics
        distance = calculate_distance(start_lat, start_lon, end_lat, end_lon)
        travel_hours = distance / 80  # Assume 80 km/h average
        liters_needed, fuel_cost = calculate_fuel_cost(distance)
        
        # Prepare trip data dictionary
        trip_data = {
            'start_location': start_location,
            'end_location': end_location,
            'start_lat': start_lat,
            'start_lon': start_lon,
            'end_lat': end_lat,
            'end_lon': end_lon,
            'distance': distance,
            'travel_hours': travel_hours,
            'fuel_needed': liters_needed,
            'fuel_cost': fuel_cost
        }
        
        # Check for alerts
        alerts = check_trip_alerts(distance, fuel_cost, travel_hours)
        
        # Determine status
        status = "✓ NORMAL TRIP"
        bg = colors.honeydew
        
        if alerts:
            alerts = list(set(alerts))
            status = "⚠️ "
            if 'long_distance' in alerts:
                status += "LONG DISTANCE TRIP"
                bg = colors.lightyellow
            if 'extended_travel' in alerts:
                status += "EXTENDED TRAVEL TIME"
                bg = colors.lightblue
            if 'high_cost' in alerts:
                status += "HIGH FUEL COST"
                bg = colors.lightsalmon
        
        # Create output directory
        final_folder = os.path.join(output_dir, location)
        if not os.path.exists(final_folder):
            os.makedirs(final_folder)
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        filename = f"Trip_Report_{location.replace(' ', '_')}_{timestamp}.pdf"
        ppath = os.path.join(final_folder, filename)
        
        # Build PDF
        doc = SimpleDocTemplate(ppath, pagesize=A4, topMargin=0.5*cm, bottomMargin=0.5*cm)
        styles = getSampleStyleSheet()
        
        # Status table
        status_t = Table([['TRIP STATUS', status]], colWidths=[4.5*cm, 13.5*cm])
        status_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, 0), colors.black),
            ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
            ('BACKGROUND', (1, 0), (1, 0), bg),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold')
        ]))
        
        # Route details table
        route_data = [
            ['From:', start_location],
            ['To:', end_location],
            ['Distance:', f"{distance:.2f} km"],
            ['Est. Travel Time:', f"{travel_hours:.1f} hours"],
            ['Avg. Speed:', "80 km/h"],
            ['', ''],
            ['Fuel Consumption:', "10 L/100km"],
            ['Fuel Required:', f"{liters_needed:.2f} liters"],
            ['Fuel Cost (@ $1.80/L):', f"${fuel_cost:.2f}"],
        ]
        
        route_t = Table(route_data, colWidths=[4.5*cm, 13.5*cm])
        route_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10)
        ]))
        
        story = [
            Paragraph(f"<b>TRIP SENTINEL REPORT</b>", styles["Title"]),
            status_t, Spacer(1, 10),
            Paragraph(f"<b>Route Details</b>", styles["Heading2"]),
            route_t, Spacer(1, 15),
            Image(generate_daily(trip_data), 19*cm, 12*cm), Spacer(1, 10),
            Image(generate_weekly(trip_data), 19*cm, 9*cm),
            Paragraph(f"<b>Trip Tips:</b>", styles["Heading2"]),
            Paragraph(
                "✓ Check your vehicle before departure<br/>"
                "✓ Fill up fuel tanks at the start<br/>"
                "✓ Take regular breaks every 2 hours<br/>"
                "✓ Stay hydrated and maintain alertness<br/>"
                "✓ Check weather conditions for your route<br/>"
                "✓ Inform someone of your travel plans",
                styles["Normal"]
            ),
            Spacer(1, 10),
            Paragraph(f"<font size=8>Generated for Bernie | {datetime.now().strftime('%H:%M')}</font>", styles["Normal"])
        ]
        
        doc.build(story)
        
        return ppath
        
    except Exception as e:
        print(f"❌ Error generating trip report: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

# ============================================================
# 4. EXECUTION
# ============================================================
if __name__ == "__main__":
    # Example usage
    trip_details = {
        'start_location': 'Melbourne',
        'end_location': 'Sydney',
        'start_coords': {'latitude': -37.8136, 'longitude': 144.9631},
        'end_coords': {'latitude': -33.8688, 'longitude': 151.2093}
    }
    
    try:
        report_path = generate_report('Melbourne_to_Sydney', trip_details)
        print(f"✓ SUCCESS: Trip report generated as '{os.path.basename(report_path)}'")
    except Exception as e:
<<<<<<< HEAD
        print(f"✗ ERROR: {e}")
=======
        print(f"✗ ERROR: {e}")
>>>>>>> 9aec95fb3bdf4ed49caec1d7c7d69e1f974b2ea9
