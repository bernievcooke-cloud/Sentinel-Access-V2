import streamlit as st
from datetime import datetime
import time

st.set_page_config(page_title='Sentinel Access', layout='wide')

# Initialize session state
if 'num_reports' not in st.session_state:
    st.session_state.num_reports = 1
if 'reports' not in st.session_state:
    st.session_state.reports = []
if 'progress_status' not in st.session_state:
    st.session_state.progress_status = ""

col1, col2, col3 = st.columns([1, 1.5, 1])

# LEFT COLUMN - Instructions & Controls
with col1:
    st.write("### 📋 User Instructions")
    st.info("""
    **How to use Sentinel Access:**
    
    1. Select your location
    2. Choose report type(s)
    3. Click \"Add Report\" to generate multiple reports
    4. Price updates: $5.00 per report
    5. Click \"Generate & Pay\" when ready
    6. System will process and email results
    """
    )
    
    st.write("### 🔄 Controls")
    if st.button("🔄 Refresh Page"):
        st.rerun()

# MIDDLE COLUMN - Report Generation
with col2:
    st.write("### 📊 Generate Reports")
    
    # Location selection
    location = st.text_input("Enter Location")
    
    # Report type selection
    report_type = st.selectbox("Select Report Type", 
                               ["Surf Report", "Night Sky Report", "Weather Report"])
    
    st.write("### 📈 Your Reports")
    st.write(f"**Number of Reports: {st.session_state.num_reports}**")
    
    # Calculate price
    price_per_report = 5.00
    total_price = st.session_state.num_reports * price_per_report
    
    st.metric("Total Price", f"${total_price:.2f}")
    
    # Add Report button
    col_add, col_gen = st.columns(2)
    with col_add:
        if st.button("➕ Add Report"):
            st.session_state.num_reports += 1
            if location:
                st.session_state.reports.append({
                    'location': location,
                    'type': report_type
                })
            st.rerun()
    
    with col_gen:
        if st.button("✅ Generate & Pay"):
            st.session_state.progress_status = "processing"
    
    # System Progress Box
    if st.session_state.progress_status == "processing":
        st.write("### ⚙️ System Progress")
        progress_bar = st.progress(0)
        
        steps = [
            ("Step 1/4: Validating location...", 25),
            ("Step 2/4: Generating reports...", 50),
            ("Step 3/4: Processing payment...", 75),
            ("Step 4/4: Sending email...", 100),
        ]
        
        for step_text, progress_val in steps:
            st.info(step_text)
            progress_bar.progress(progress_val)
            time.sleep(0.5)
        
        st.success("✅ All reports generated and email sent!")
        st.session_state.progress_status = ""

# RIGHT COLUMN - Example Reports
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