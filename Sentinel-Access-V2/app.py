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

# ============================================================
# PAGE CONFIG - MUST BE FIRST!
# ============================================================

st.set_page_config(
    page_title="🛰️ Sentinel Access",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

load_dotenv()

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
    "Night Sky Report": {"price": "$29.99", "icon": "🌌"},
    "Weather Report": {"price": "$29.99", "icon": "🌤️"}
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

if 'reports_queue' not in st.session_state:
    st.session_state.reports_queue = []

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
        elif "Weather" in report_type:
            report_type_key = "Weather"
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
        email_from = os.getenv("SENDER_EMAIL")
        email_password = os.getenv("SENDER_PASSWORD")
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
            "Select Location",
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
    
    # Show queued reports
    if st.session_state.reports_queue:
        st.markdown("**📋 Reports in queue:**")
        for i, r in enumerate(st.session_state.reports_queue, 1):
            st.markdown(f"{i}. {r['icon']} {r['type']} @ {r['location']}")
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
            # Build list of reports to process (queue + current)
            current_report = {
                "type": st.session_state.selected_report_type,
                "location": st.session_state.selected_location,
                "icon": report_info['icon']
            }
            all_reports = st.session_state.reports_queue + [current_report]
            
            unit_price = float(report_info['price'].replace('$', ''))
            total_price = unit_price * len(all_reports)
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            all_pdf_paths = []
            success = True
            
            for idx, rep in enumerate(all_reports):
                pct_start = int(idx / len(all_reports) * 100)
                pct_end = int((idx + 1) / len(all_reports) * 100)
                
                status_text.info(f"⏳ [{idx+1}/{len(all_reports)}] Generating {rep['icon']} {rep['type']} for {rep['location']}...")
                progress_bar.progress(pct_start)
                time.sleep(0.5)
                
                pdf_path = generate_report(rep['location'], rep['type'])
                
                if pdf_path:
                    all_pdf_paths.append(pdf_path)
                    status_text.success(f"✅ [{idx+1}/{len(all_reports)}] {rep['type']} generated!")
                    progress_bar.progress(pct_end)
                else:
                    status_text.error(f"❌ [{idx+1}/{len(all_reports)}] Failed to generate {rep['type']}")
                    success = False
                    break
            
            if success and all_pdf_paths:
                progress_bar.progress(100)
                status_text.info("💳 Processing payment...")
                time.sleep(1)
                st.success("✅ Payment successful!")
                
                # Send email with first PDF (primary report)
                st.info("📧 Sending email with report(s)...")
                
                report_lines = "\n".join(
                    f"- {r['icon']} {r['type']} @ {r['location']}" for r in all_reports
                )
                email_subject = "Your Sentinel Access Report(s)"
                email_body = f"""
Hello {st.session_state.username},

Your report(s) have been generated and are ready!

Reports ordered:
{report_lines}

Total Amount Paid: ${total_price:.2f} ({len(all_reports)} x {report_info['price']})
Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Your report PDF is attached to this email.

Thank you for using Sentinel Access!

Best regards,
Sentinel Access Team
                """
                
                if send_email_with_attachment(
                    st.session_state.user_email,
                    email_subject,
                    email_body,
                    all_pdf_paths[0]
                ):
                    st.success(f"📧 Email sent to {st.session_state.user_email}!")
                    st.divider()
                    
                    # Show order summary
                    st.success("✅ ORDER COMPLETE!")
                    for r, p in zip(all_reports, all_pdf_paths):
                        st.markdown(f"""
                        **{r['icon']} {r['type']} - {r['location']}**
                        - 👤 {st.session_state.username}
                        - 📧 {st.session_state.user_email}
                        - 💰 {report_info['price']} per report
                        - 📁 PDF: `{os.path.basename(p)}`
                        """)
                    if len(all_reports) > 1:
                        st.markdown(f"**💰 Total: ${total_price:.2f}** ({len(all_reports)} x {report_info['price']})")
                    
                    # Clear queue after successful order
                    st.session_state.reports_queue = []
                else:
                    st.error("❌ Failed to send email")
            elif not success:
                st.error("❌ Failed to generate one or more reports")
    
    # Add Another Report button
    if st.button("➕ Add Another Report", use_container_width=True):
        if not st.session_state.selected_location:
            st.error("❌ Select a location first")
        else:
            st.session_state.reports_queue.append({
                "type": st.session_state.selected_report_type,
                "location": st.session_state.selected_location,
                "icon": report_info['icon']
            })
            st.success(f"✅ Added {report_info['icon']} {st.session_state.selected_report_type} @ {st.session_state.selected_location} to queue")
            st.rerun()

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
    
    st.divider()
    
    st.markdown("#### 🌤️ WEATHER REPORT")
    
    with st.container(border=True):
        st.markdown("""
        **Sample Weather Report**
        
        📍 Location: Cape Schanck
        
        🌡️ Max Temp: 24°C
        
        💨 Wind: 25 km/h NW
        
        ⚠️ Alert: NORMAL
        
        [Download Example PDF]
        """)

# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(f"© 2026 Sentinel Access | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")