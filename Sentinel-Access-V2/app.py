import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import streamlit as st
from datetime import datetime

from core.email_sender import send_report_email
from core.location_manager import LocationManager
from core.report_wrapper import generate_report

st.set_page_config(page_title='Sentinel Access', layout='wide')

# Load locations from config/locations.json, with fallback to hardcoded defaults
_FALLBACK_COORDS = {
    'Bells Beach': (-38.371, 144.282),
    'Point Leo':   (-38.423, 145.074),
    'Melbourne':   (-37.814, 144.963),
    'Sydney':      (-33.869, 151.209),
}

def _load_locations_from_json():
    json_path = Path(__file__).parent / 'config' / 'locations.json'
    coords_dict = {}
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        for key, coord_data in data.items():
            # Handle array format: [lat, lon]
            if isinstance(coord_data, (list, tuple)) and len(coord_data) >= 2:
                label = key
                coords_dict[label] = (float(coord_data[0]), float(coord_data[1]))
            # Handle dict format: {latitude: ..., longitude: ..., display_name: ...}
            elif isinstance(coord_data, dict):
                if 'latitude' in coord_data and 'longitude' in coord_data:
                    label = coord_data.get('display_name', key)
                    coords_dict[label] = (float(coord_data['latitude']), float(coord_data['longitude']))
        return coords_dict if coords_dict else _FALLBACK_COORDS
    except Exception as e:
        print(f"⚠️ Could not load locations.json, using defaults: {e}")
        return _FALLBACK_COORDS

location_manager = LocationManager()

# Initialize session state
if 'locations_list' not in st.session_state or 'locations_coords' not in st.session_state:
    _coords = _load_locations_from_json()
    st.session_state.locations_coords = _coords
    st.session_state.locations_list = sorted(_coords.keys())
if 'selected_reports' not in st.session_state:
    st.session_state.selected_reports = []
if 'progress_status' not in st.session_state:
    st.session_state.progress_status = ""
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'user_email' not in st.session_state:
    st.session_state.user_email = ""
if 'geocode_result' not in st.session_state:
    st.session_state.geocode_result = None
if 'geocode_search_term' not in st.session_state:
    st.session_state.geocode_search_term = ""

def add_location(name, lat, lon, state=None, display_name=None, source=None, verified=False):
    label = display_name or (f"{name}, {state}" if state else name)
    st.session_state.locations_list.append(label)
    st.session_state.locations_list = sorted(list(set(st.session_state.locations_list)))
    st.session_state.locations_coords[label] = (float(lat), float(lon))
    location_manager.add_location(name, lat, lon, state=state, display_name=label,
                                   source=source, verified=verified)

col1, col2, col3 = st.columns([1, 1.5, 1])

# LEFT COLUMN
with col1:
    st.write("### 📋 User Instructions")
    st.info("""
    **How to use Sentinel Access:**
    
    1. Enter your name & email
    2. Select a report type
    3. Click "Add Report"
    4. Choose location(s)
    5. Add multiple reports as needed
    6. Click "Generate & Pay"
    7. System processes & emails results
    """)
    
    st.write("### 👤 Your Details")
    st.session_state.username = st.text_input("Username", value=st.session_state.username, placeholder="Enter your name")
    st.session_state.user_email = st.text_input("Email Address", value=st.session_state.user_email, placeholder="your.email@example.com")
    
    st.write("### 🔄 Controls")
    if st.button("🔄 Refresh Page"):
        st.rerun()

# MIDDLE COLUMN
with col2:
    st.write("### 📊 Generate Reports")
    
    # Step 1: Select Report Type
    st.write("**Step 1: Select Report Type**")
    report_type = st.selectbox("Report Type", 
                               ["Surf Report", "Night Sky Report", "Weather Report", "Trip Report"],
                               key="report_type")
    
    # Step 2: Select Location(s)
    st.write("**Step 2: Select Location(s)**")
    
    if report_type == "Trip Report":
        st.write("🚗 **Trip Report requires Start and End locations**")
        start_location = st.selectbox("Start Location", 
                                     st.session_state.locations_list,
                                     key="start_location")
        end_location = st.selectbox("End Location", 
                                   st.session_state.locations_list,
                                   key="end_location")
    else:
        selected_location = st.selectbox("Choose Location", 
                                        st.session_state.locations_list,
                                        key="location")
    
    # Step 3: Add Report Button
    st.write("**Step 3: Add Report**")
    
    if st.button("➕ Add Report"):
        if report_type == "Trip Report":
            if start_location == end_location:
                st.error("⚠️ Start and End locations must be different")
            else:
                report_data = {
                    'type': report_type,
                    'start_location': start_location,
                    'end_location': end_location
                }
                st.session_state.selected_reports.append(report_data)
                st.success(f"✅ Added: Trip Report ({start_location} → {end_location})")
                st.rerun()
        else:
            report_data = {
                'type': report_type,
                'location': selected_location
            }
            st.session_state.selected_reports.append(report_data)
            st.success(f"✅ Added: {report_type} - {selected_location}")
            st.rerun()
    
    # Create New Location if needed
    with st.expander("➕ Create New Location"):
        new_loc_name = st.text_input("Location Name (e.g., 'Bondi Beach')", key="new_loc_name")

        if st.button("🔍 Search Location"):
            if new_loc_name:
                with st.spinner("Searching..."):
                    result = location_manager.geocode_location(new_loc_name)
                if result:
                    st.session_state.geocode_result = result
                    st.session_state.geocode_search_term = new_loc_name
                else:
                    st.session_state.geocode_result = None
                    st.session_state.geocode_search_term = ""
                    st.error(f"❌ Location not found: '{new_loc_name}'. Try a different search term.")
            else:
                st.error("Please enter a location name")

        if (st.session_state.geocode_result
                and st.session_state.geocode_search_term == new_loc_name):
            result = st.session_state.geocode_result
            lat = result.get('latitude', 0)
            lon = result.get('longitude', 0)
            st.success(f"📍 Found: {result.get('display_name', 'Location')}")
            st.write(f"**Coordinates:** {lat}, {lon}")
            if result.get('source'):
                st.caption(f"Source: {result['source']}")

            if st.button("✅ Confirm & Add Location"):
                add_location(
                    new_loc_name,
                    float(lat),
                    float(lon),
                    state=result.get('state'),
                    display_name=result.get('display_name'),
                    source=result.get('source'),
                    verified=result.get('verified', False)
                )
                st.session_state.geocode_result = None
                st.session_state.geocode_search_term = ""
                st.success(f"✅ Added: {new_loc_name} ({lat}, {lon})")
                st.rerun()
    
    # Display Selected Reports
    st.write("### 📋 Your Reports")
    if st.session_state.selected_reports:
        for idx, report in enumerate(st.session_state.selected_reports, 1):
            if report['type'] == "Trip Report":
                st.write(f"**Report {idx}:** 🚗 {report['type']} | {report['start_location']} → {report['end_location']}")
            else:
                st.write(f"**Report {idx}:** {report['type']} | 📍 {report['location']}")
        
        price_per_report = 5.00
        total_price = len(st.session_state.selected_reports) * price_per_report
        
        st.metric("Total Price", f"${total_price:.2f}")
        
        if st.button("✅ Generate & Pay"):
            # Validate user details
            if not st.session_state.username or not st.session_state.user_email:
                st.error("⚠️ Please enter your name and email before generating reports")
            else:
                st.session_state.progress_status = "processing"
    else:
        st.info("No reports added yet. Add a report to get started!")
    
    # System Progress Box
    if st.session_state.progress_status == "processing":
        st.write("### ⚙️ System Progress")
        progress_bar = st.progress(0)

        # Map UI report type labels to worker keywords
        type_map = {
            "Surf Report":      "surf",
            "Night Sky Report": "sky",
            "Weather Report":   "weather",
            "Trip Report":      "trip",
        }

        # Step 1: Validate locations
        st.info("Step 1/4: Validating locations...")
        progress_bar.progress(25)
        missing = []
        for r in st.session_state.selected_reports:
            if r['type'] == "Trip Report":
                if r['start_location'] not in st.session_state.locations_coords or r['end_location'] not in st.session_state.locations_coords:
                    missing.append(f"{r['start_location']} or {r['end_location']}")
            else:
                if r['location'] not in st.session_state.locations_coords:
                    missing.append(r['location'])
        
        if missing:
            st.error(f"⚠️ Missing coordinates for: {', '.join(set(missing))}")
            st.session_state.progress_status = ""
        else:
            # Step 2: Generate reports
            st.info("Step 2/4: Generating reports...")
            progress_bar.progress(50)
            output_dir = tempfile.mkdtemp(prefix="sentinel_reports_")
            pdf_paths = []
            errors = []
            for report in st.session_state.selected_reports:
                try:
                    worker_type = type_map.get(report['type'], report['type'].lower())
                    
                    if report['type'] == "Trip Report":
                        start_coords = st.session_state.locations_coords[report['start_location']]
                        end_coords = st.session_state.locations_coords[report['end_location']]
                        trip_details = {
                            'start_location': report['start_location'],
                            'end_location': report['end_location'],
                            'start_coords': start_coords,
                            'end_coords': end_coords
                        }
                        pdf_path = generate_report(
                            f"{report['start_location']}_to_{report['end_location']}", 
                            worker_type, 
                            start_coords, 
                            output_dir,
                            trip_details
                        )
                    else:
                        coords = st.session_state.locations_coords[report['location']]
                        pdf_path = generate_report(
                            report['location'], 
                            worker_type, 
                            coords, 
                            output_dir
                        )
                    pdf_paths.append(pdf_path)
                except Exception as e:
                    errors.append(f"{report['type']}: {e}")

            if errors:
                for err in errors:
                    st.error(f"⚠️ Report error: {err}")
                st.session_state.progress_status = ""
            else:
                # Step 3: Processing payment (placeholder)
                st.info("Step 3/4: Processing payment...")
                progress_bar.progress(75)
                time.sleep(0.3)

                # Step 4: Send email
                st.info(f"Step 4/4: Sending email to {st.session_state.user_email}...")
                progress_bar.progress(100)
                success, err_msg = send_report_email(
                    st.session_state.user_email,
                    st.session_state.username,
                    pdf_paths,
                )
                if success:
                    st.success(f"✅ All reports generated and sent to {st.session_state.user_email}!")
                    st.session_state.selected_reports = []
                else:
                    st.error(f"⚠️ Reports generated but email failed: {err_msg}")
                st.session_state.progress_status = ""
                shutil.rmtree(output_dir, ignore_errors=True)

# RIGHT COLUMN
with col3:
    st.write("### 📚 Example Reports")
    
    st.write("**Surf Report**")
    st.write("Location: Bells Beach | Waves: 2.1m | Condition: EXCELLENT")
    st.divider()
    
    st.write("**Night Sky Report**")
    st.write("Location: Point Leo | Moon: Waxing | Clarity: 92%")
    st.divider()
    
    st.write("**Weather Report**")
    st.write("Location: Melbourne | Temp: 22C | Wind: 15 km/h")
    st.divider()

    st.write("**Trip Report**")
    st.write("Start: Sydney | End: Melbourne | Distance: 880km | Fuel Cost: $158.40")
         
st.divider()
st.caption(f"© 2026 Sentinel Access | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")