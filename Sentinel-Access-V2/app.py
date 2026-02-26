"""
Sentinel Access - Streamlit Dashboard
Complete application with Report Generation & Email
"""

import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

load_dotenv()

# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="🛰️ Sentinel Access",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ============================================================
# CONFIGURATION
# ============================================================

BASE_OUTPUT_PATH = os.getenv("BASE_OUTPUT_PATH", "./storage/reports")

# Import Location Manager & Report Wrapper
try:
    from core.location_manager import LocationManager
    from core.report_wrapper import generate_report as generate_report_pdf
    location_manager = LocationManager(BASE_OUTPUT_PATH)
    has_report_gen = True
except ImportError as e:
    st.error(f"⚠️ Import error: {e}")
    location_manager = None
    has_report_gen = False

# ============================================================
# CONSTANTS
# ============================================================

REPORT_TYPES = {
    "Surf Report": {"price": "$29.99", "icon": "🌊"},
    "Night Sky Report": {"price": "$29.99", "icon": "🌌"}
}

# ============================================================
# SESSION STATE
# ============================================================

if 'username' not in st.session_state:
    st.session_state.username = ""

if 'user_email' not in st.session_state:
    st.session_state.user_email = ""

if 'locations_cache' not in st.session_state:
    if location_manager:
        st.session_state.locations_cache = location_manager.get_all_locations()
    else:
        st.session_state.locations_cache = {}

if 'selected_location' not in st.session_state:
    st.session_state.selected_location = None

if 'selected_report_type' not in st.session_state:
    st.session_state.selected_report_type = "Surf Report"

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def refresh_locations():
    """Refresh locations from manager"""
    if location_manager:
        try:
            st.session_state.locations_cache = location_manager.get_all_locations()
            return True
        except Exception as e:
            st.error(f"Error refreshing: {e}")
            return False
    return False

def validate_email(email):
    """Validate email"""
    return "@" in email and "." in email.split("@")[1]

def generate_report(location_name, report_type):
    """Generate PDF report using the report wrapper"""
    try:
        if not has_report_gen:
            raise Exception("Report generation not available")
        
        # Get coordinates for location
        coords_data = location_manager.get_coordinates(location_name)
        if not coords_data:
            raise Exception(f"No coordinates found for {location_name}")
        
        # Convert to tuple (lat, lon)
        if isinstance(coords_data, dict):
            coords_tuple = (coords_data['latitude'], coords_data['longitude'])
        else:
            coords_tuple = tuple(coords_data)
        
        # Determine report type for worker
        if "Surf" in report_type:
            report_type_key = "Surf"
        else:
            report_type_key = "Night"
        
        # Call report wrapper
        pdf_path = generate_report_pdf(
            location=location_name,
            report_type=report_type_key,
            coords=coords_tuple,
            output_dir=BASE_OUTPUT_PATH
        )
        
        return pdf_path
        
    except Exception as e:
        st.error(f"❌ Report generation failed: {e}")
        return None

def send_email_with_attachment(recipient_email, subject, body, pdf_path):
    """Send email with PDF attachment"""
    try:
        email_from = os.getenv("EMAIL_FROM")
        email_password = os.getenv("EMAIL_PASSWORD")
        smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        
        if not email_from or not email_password:
            raise Exception("Email credentials not configured in .env")
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = email_from
        msg['To'] = recipient_email
        msg['Subject'] = subject
        
        # Attach body
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach PDF if it exists
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as attachment:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(pdf_path)}')
                msg.attach(part)
        else:
            st.warning(f"⚠️ PDF file not found at {pdf_path}")
            return False
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(email_from, email_password)
            server.send_message(msg)
        
        return True
        
    except Exception as e:
        st.error(f"❌ Email failed: {e}")
        return False

# ============================================================
# LAYOUT - 3 COLUMNS
# ============================================================

col_left, col_center, col_right = st.columns([1, 1.5, 1], gap="medium")

# ============================================================
# LEFT COLUMN
# ============================================================

with col_left:
    st.markdown("### ⚙️ CONTROLS")
    
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        if st.button("🔄 Refresh", use_container_width=True, key="refresh_loc_btn"):
            if refresh_locations():
                st.success("✅ Refreshed!")
                st.rerun()
    
    with btn_col2:
        if st.button("🔄 Page", use_container_width=True, key="refresh_page_btn"):
            st.rerun()
    
    st.divider()
    
    st.markdown("### 👤 YOUR DETAILS")
    
    st.session_state.username = st.text_input(
        "Username",
        value=st.session_state.username,
        placeholder="Enter your name"
    )
    
    st.session_state.user_email = st.text_input(
        "Email",
        value=st.session_state.user_email,
        placeholder="your.email@example.com"
    )
    
    st.divider()
    
    st.markdown("### 📖 USER INSTRUCTIONS")
    
    st.markdown("""
    **How to use:**
    
    1️⃣ Enter username & email
    
    2️⃣ Create location (optional)
    
    3️⃣ Select report type
    
    4️⃣ Choose location
    
    5️⃣ Click "Generate & Pay"
    
    6️⃣ Complete payment
    
    7️⃣ Report to email
    
    ---
    
    **🔒 PRIVACY**
    
    ✅ No personal data stored
    
    ✅ No payment data stored
    
    ✅ Reports for you only
    """)

# ============================================================
# CENTER COLUMN
# ============================================================

with col_center:
    st.markdown("### 📍 CREATE LOCATION")
    
    with st.form("add_location_form", clear_on_submit=True):
        loc_name = st.text_input("Location Name", placeholder="e.g., Bells Beach")
        
        if st.form_submit_button("✅ Save Location", use_container_width=True):
            if not loc_name:
                st.error("❌ Enter location name")
            elif location_manager:
                try:
                    norm_name = loc_name.lower().strip()
                    # Use default coordinates
                    success = location_manager.add_location(norm_name, -38.0, 144.0)
                    if success:
                        st.session_state.locations_cache = location_manager.get_all_locations()
                        st.success(f"✅ '{norm_name}' saved!")
                        st.rerun()
                    else:
                        st.error("❌ Failed to save")
                except Exception as e:
                    st.error(f"❌ {e}")
    
    st.divider()
    
    st.markdown("### 📊 ORDER REPORT")
    
    # Get locations list
    location_list = sorted(list(st.session_state.locations_cache.keys())) if st.session_state.locations_cache else []
    
    # Report Type
    st.session_state.selected_report_type = st.selectbox(
        "Report Type",
        list(REPORT_TYPES.keys()),
        key="report_type_select"
    )
    
    # Location
    if location_list:
        st.session_state.selected_location = st.selectbox(
            "Location",
            location_list,
            key="location_select"
        )
    else:
        st.error("⚠️ No locations available - create one first!")
        st.session_state.selected_location = None
    
    st.divider()
    
    # Price
    report_info = REPORT_TYPES[st.session_state.selected_report_type]
    st.metric("💰 Price", report_info['price'])
    
    st.divider()
    
    # Generate button
    if st.button("💳 GENERATE & PAY", use_container_width=True):
        # Validation
        if not st.session_state.username:
            st.error("❌ Username required")
        elif not st.session_state.user_email:
            st.error("❌ Email required")
        elif not validate_email(st.session_state.user_email):
            st.error("❌ Valid email required")
        elif not st.session_state.selected_location:
            st.error("❌ Location required")
        else:
            # Process
            with st.spinner("🔄 Generating report..."):
                st.info("🔄 Generating PDF report...")
                time.sleep(1)
                
                # Generate PDF
                pdf_path = generate_report(
                    st.session_state.selected_location,
                    st.session_state.selected_report_type
                )
                
                if pdf_path:
                    st.success("✅ Report generated!")
                    st.divider()
                    st.info("💳 Processing payment...")
                    time.sleep(1)
                    st.success("✅ Payment successful!")
                    
                    # Send email
                    st.info("📧 Sending email with PDF...")
                    
                    email_subject = f"Your {st.session_state.selected_report_type} - Sentinel Access"
                    email_body = f"""
Hello {st.session_state.username},

Your report has been generated and is ready!

**Report Details:**
- Report Type: {st.session_state.selected_report_type}
- Location: {st.session_state.selected_location}
- Amount Paid: {report_info['price']}
- Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Your report PDF is attached to this email.

Thank you for using Sentinel Access!

Best regards,
Sentinel Access Team
                    """
                    
                    if send_email_with_attachment(
                        st.session_state.user_email,
                        email_subject,
                        email_body,
                        pdf_path
                    ):
                        st.success(f"📧 Email sent to {st.session_state.user_email}!")
                        st.divider()
                        
                        # Show order summary
                        st.success("✅ ORDER COMPLETE!")
                        st.markdown(f"""
                        **Order Details:**
                        - 📋 {st.session_state.selected_report_type}
                        - 📍 {st.session_state.selected_location}
                        - 👤 {st.session_state.username}
                        - 📧 {st.session_state.user_email}
                        - 💰 {report_info['price']}
                        - 📁 PDF: `{os.path.basename(pdf_path)}`
                        """)
                    else:
                        st.error("❌ Failed to send email")
                else:
                    st.error("❌ Failed to generate report")

# ============================================================
# RIGHT COLUMN - EXAMPLE REPORTS
# ============================================================

with col_right:
    st.markdown("### 📋 EXAMPLE REPORTS")
    
    st.divider()
    
    st.markdown("#### 🌊 SURF REPORT")
    
    with st.container(border=True):
        st.markdown("""
        **Sample Surf Report**
        
        📍 Location: Bells Beach
        
        📊 Current Waves: 2.1m
        
        ⭐ Condition: EXCELLENT
        
        🏆 Best Day: Tomorrow
        
        [Download Example PDF]
        """)
    
    st.divider()
    
    st.markdown("#### 🌌 SKY REPORT")
    
    with st.container(border=True):
        st.markdown("""
        **Sample Night Sky Report**
        
        📍 Location: Point Leo
        
        🌙 Moon Phase: Waxing Gibbous
        
        ⭐ Sky Clarity: 92%
        
        ✨ Best Night: Tonight
        
        [Download Example PDF]
        """)

# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(f"© 2026 Sentinel Access | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")