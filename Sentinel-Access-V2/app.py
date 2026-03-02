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
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
        return {name: tuple(coords) for name, coords in data.items()}
    except Exception as e:
        print(f"⚠️ Could not load locations.json, using defaults: {e}")
        return _FALLBACK_COORDS

location_manager = LocationManager("./output")

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
if 'trip_details' not in st.session_state:
    st.session_state.trip_details = {}

def add_location(name, lat, lon, source=None, verified=False):
    st.session_state.locations_list.append(name)
    st.session_state.locations_list = sorted(list(set(st.session_state.locations_list)))
    st.session_state.locations_coords[name] = (lat, lon)
    location_manager.add_location(name, lat, lon, source=source, verified=verified)

col1, col2, col3 = st.columns([1, 1.5, 1])

# LEFT COLUMN
with col1:
    st.write("### 📋 User Instructions")
    st.info("""
    **How to use Sentinel Access:**
    
    1. Enter your name & email
    2. Select a report type
    3. Choose a location (or create new)
    4. For Trip Report: Fill trip details
    5. Click "Add Report" to add to order
    6. Add multiple reports as needed
    7. Click "Generate & Pay"
    8. System processes & emails results
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
    
    # Trip Planner Form - Show only if Trip Report selected
    if report_type == "Trip Report":
        st.write("### 🚗 Trip Report Details")
        st.info("Fill in your trip details below. These will be included in your generated report.")
        
        with st.form("trip_form", clear_on_submit=True):
            vehicle_type = st.selectbox("Vehicle Type", ["Car", "SUV", "Van", "Truck", "Motorcycle"], key="vehicle_type")
            fuel_type = st.selectbox("Fuel Type", ["Petrol", "Diesel", "Electric", "Hybrid"], key="fuel_type")
            estimated_fuel_cost = st.number_input("Est. Fuel Cost ($)", min_value=0, value=50, step=5, key="fuel_cost")
            activities = st.multiselect("Activities", ["Hiking", "Photography", "Sightseeing", "Camping", "Dining", "Surfing", "Beach"], key="activities")
            accommodation = st.selectbox("Accommodation", ["Hotel", "Airbnb", "Camping", "Hostel", "Free Camping", "Caravan Parks"], key="accommodation")
            trip_duration = st.slider("Trip Duration (days)", 1, 30, 3, key="trip_duration")
            
            submitted = st.form_submit_button("💾 Save Trip Details")
            if submitted:
                if not activities:
                    st.error("Please select at least one activity")
                else:
                    st.session_state.trip_details = {
                        'vehicle_type': vehicle_type,
                        'fuel_type': fuel_type,
                        'fuel_cost': estimated_fuel_cost,
                        'activities': activities,
                        'accommodation': accommodation,
                        'trip_duration': trip_duration
                    }
                    st.success("✅ Trip details saved! Now select location and add report.")
        
        # Display saved trip details
        if st.session_state.trip_details:
            st.write("### 📝 Saved Trip Details")
            col_a, col_b, col_c = st.columns(3)
            with col_a:
                st.metric("Vehicle", st.session_state.trip_details.get('vehicle_type', 'N/A'))
                st.metric("Fuel Type", st.session_state.trip_details.get('fuel_type', 'N/A'))
            with col_b:
                st.metric("Duration", f"{st.session_state.trip_details.get('trip_duration', 0)} days")
                st.metric("Fuel Cost", f"${st.session_state.trip_details.get('fuel_cost', 0)}")
            with col_c:
                st.metric("Accommodation", st.session_state.trip_details.get('accommodation', 'N/A'))
            if st.session_state.trip_details.get('activities'):
                st.write(f"**Activities:** {', '.join(st.session_state.trip_details['activities'])}")
    
    # Step 2: Select Location
    st.write("**Step 2: Select Location**")
    selected_location = st.selectbox("Choose Location", 
                                    st.session_state.locations_list,
                                    key="location")
    
    # Step 3: Create New Location if needed
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
            st.success(f"📍 Found: {result['display_name']}")
            st.write(f"**Coordinates:** {result['latitude']}, {result['longitude']}")
            st.caption(f"Source: {result['source']}")

            if st.button("✅ Confirm & Add Location"):
                add_location(
                    new_loc_name,
                    result['latitude'],
                    result['longitude'],
                    source=result['source'],
                    verified=result['verified']
                )
                st.session_state.geocode_result = None
                st.session_state.geocode_search_term = ""
                st.success(f"✅ Added: {new_loc_name} ({result['latitude']}, {result['longitude']})")
                st.rerun()
    
    # Step 4: Add Report Button
    st.write("**Step 3: Add Report**")
    
    # Validation for Trip Report
    trip_ready = True
    if report_type == "Trip Report":
        if not st.session_state.trip_details:
            st.warning("⚠️ Please save trip details first")
            trip_ready = False
    
    if trip_ready and st.button("➕ Add Report"):
        report_data = {
            'type': report_type,
            'location': selected_location
        }
        # Attach trip details if Trip Report
        if report_type == "Trip Report" and st.session_state.trip_details:
            report_data['details'] = st.session_state.trip_details.copy()
        
        st.session_state.selected_reports.append(report_data)
        st.success(f"✅ Added: {report_type} - {selected_location}")
        st.rerun()
    
    # Display Selected Reports
    st.write("### 📋 Your Reports")
    if st.session_state.selected_reports:
        for idx, report in enumerate(st.session_state.selected_reports, 1):
            with st.expander(f"**Report {idx}:** {report['type']} | 📍 {report['location']}"):
                if report['type'] == "Trip Report" and 'details' in report:
                    st.write(f"🚗 Vehicle: {report['details'].get('vehicle_type')}")
                    st.write(f"⛽ Fuel: {report['details'].get('fuel_type')}")
                    st.write(f"📅 Duration: {report['details'].get('trip_duration')} days")
                    st.write(f"🏨 Accommodation: {report['details'].get('accommodation')}")
                    st.write(f"🎯 Activities: {', '.join(report['details'].get('activities', []))}")
        
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
        missing = [
            r['location'] for r in st.session_state.selected_reports
            if r['location'] not in st.session_state.locations_coords
        ]
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
                    coords = st.session_state.locations_coords[report['location']]
                    worker_type = type_map.get(report['type'], report['type'].lower())
                    trip_details = report.get('details', None) if report['type'] == "Trip Report" else None
                    pdf_path = generate_report(
                        report['location'], worker_type, coords, output_dir, trip_details
                    )
                    pdf_paths.append(pdf_path)
                except Exception as e:
                    errors.append(f"{report['type']} @ {report['location']}: {e}")

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
                    st.session_state.trip_details = {}
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
    st.write("Location: Sydney | Vehicle: Car | Duration: 3 days | Activities: Hiking, Sightseeing")
         
st.divider()
st.caption(f"© 2026 Sentinel Access | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
