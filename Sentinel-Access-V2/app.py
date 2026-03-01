import streamlit as st
from datetime import datetime

st.set_page_config(page_title='Sentinel Access', layout='wide')

# Initialize session state
if 'locations_list' not in st.session_state:
    st.session_state.locations_list = ['Bells Beach', 'Point Leo', 'Melbourne', 'Sydney']
if 'selected_reports' not in st.session_state:
    st.session_state.selected_reports = []
if 'progress_status' not in st.session_state:
    st.session_state.progress_status = ""

def add_location(name, lat, lon):
    st.session_state.locations_list.append(name)
    st.session_state.locations_list = sorted(list(set(st.session_state.locations_list)))

col1, col2, col3 = st.columns([1, 1.5, 1])

# LEFT COLUMN
with col1:
    st.write("### 📋 User Instructions")
    st.info("""
    **How to use Sentinel Access:**
    
    1. Select a report type
    2. Choose a location (or create new)
    3. Click "Add Report" to add to order
    4. Add multiple reports as needed
    5. Click "Generate & Pay"
    6. System processes & emails results
    """)
    
    st.write("### 🔄 Controls")
    if st.button("🔄 Refresh Page"):
        st.rerun()

# MIDDLE COLUMN
with col2:
    st.write("### 📊 Generate Reports")
    
    # Step 1: Select Report Type
    st.write("**Step 1: Select Report Type**")
    report_type = st.selectbox("Report Type", 
                               ["Surf Report", "Night Sky Report", "Weather Report"],
                               key="report_type")
    
    # Step 2: Select Location
    st.write("**Step 2: Select Location**")
    selected_location = st.selectbox("Choose Location", 
                                    st.session_state.locations_list,
                                    key="location")
    
    # Step 3: Create New Location if needed
    with st.expander("➕ Create New Location"):
        new_loc_name = st.text_input("Location Name (e.g., 'Bondi Beach')", key="new_loc_name")
        new_loc_lat = st.number_input("Latitude", value=-33.0, format="%.4f", key="new_loc_lat")
        new_loc_lon = st.number_input("Longitude", value=151.0, format="%.4f", key="new_loc_lon")
        
        if st.button("✅ Add New Location"):
            if new_loc_name:
                add_location(new_loc_name, new_loc_lat, new_loc_lon)
                st.success(f"✅ Added: {new_loc_name} ({new_loc_lat}, {new_loc_lon})")
                st.rerun()
            else:
                st.error("Please enter a location name")
    
    # Step 4: Add Report Button
    st.write("**Step 3: Add Report**")
    if st.button("➕ Add Report"):
        st.session_state.selected_reports.append({
            'type': report_type,
            'location': selected_location
        })
        st.success(f"✅ Added: {report_type} - {selected_location}")
        st.rerun()
    
    # Display Selected Reports
    st.write("### 📋 Your Reports")
    if st.session_state.selected_reports:
        for idx, report in enumerate(st.session_state.selected_reports, 1):
            st.write(f"**Report {idx}:** {report['type']} | 📍 {report['location']}")
        
        price_per_report = 5.00
        total_price = len(st.session_state.selected_reports) * price_per_report
        
        st.metric("Total Price", f"${total_price:.2f}")
        
        if st.button("✅ Generate & Pay"):
            st.session_state.progress_status = "processing"
    else:
        st.info("No reports added yet. Add a report to get started!")
    
    # System Progress Box
    if st.session_state.progress_status == "processing":
        st.write("### ⚙️ System Progress")
        progress_bar = st.progress(0)
        
        steps = [
            ("Step 1/4: Validating locations...", 25),
            ("Step 2/4: Generating reports...", 50),
            ("Step 3/4: Processing payment...", 75),
            ("Step 4/4: Sending email...", 100),
        ]
        
        for step_text, progress_val in steps:
            st.info(step_text)
            progress_bar.progress(progress_val)
            import time
            time.sleep(0.3)
        
        st.success("✅ All reports generated and email sent!")
        st.session_state.progress_status = ""
        st.session_state.selected_reports = []

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
st.caption(f"© 2026 Sentinel Access | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")