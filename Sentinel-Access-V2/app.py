import streamlit as st
from datetime import datetime
import time

st.set_page_config(page_title='Sentinel Access', layout='wide')

if 'locations' not in st.session_state:
    st.session_state.locations = []
if 'username' not in st.session_state:
    st.session_state.username = ""
if 'email' not in st.session_state:
    st.session_state.email = ""

col1, col2, col3 = st.columns([1, 1.5, 1])

with col1:
    st.write("### Controls")
    if st.button("Refresh"):
        st.rerun()
    st.write("### Your Details")
    st.session_state.username = st.text_input("Username", st.session_state.username)
    st.session_state.email = st.text_input("Email", st.session_state.email)

with col2:
    st.write("### Create Location")
    loc_input = st.text_input("Location Name")
    if st.button("Save Location"):
        if loc_input:
            st.session_state.locations.append(loc_input)
            st.success(f"Saved: {loc_input}")
    
    st.write("### Order Report")
    st.selectbox("Report Type", ["Surf Report", "Night Sky Report", "Weather Report"])
    
    if st.session_state.locations:
        st.selectbox("Select Location", st.session_state.locations)
    else:
        st.error("No locations - create one first!")
    
    st.metric("Price", "$29.99")
    
    if st.button("GENERATE & PAY"):
        pb = st.progress(0)
        st.info("Step 1/4: Generating...")
        pb.progress(25)
        time.sleep(1)
        st.success("Step 1 done")
        
        st.info("Step 2/4: Payment...")
        pb.progress(50)
        time.sleep(1)
        st.success("Step 2 done")
        
        st.info("Step 3/4: Email...")
        pb.progress(75)
        time.sleep(1)
        st.success("Step 3 done")
        
        st.info("Step 4/4: Finalizing...")
        pb.progress(100)
        time.sleep(1)
        st.success("Complete!")
        
        if st.button("Add Another Report"):
            st.rerun()

with col3:
    st.write("### Example Reports")
    st.write("**Surf Report**")
    st.write("Location: Bells Beach | Waves: 2.1m | Condition: EXCELLENT")
    st.write("**Night Sky Report**")
    st.write("Location: Point Leo | Moon: Waxing | Clarity: 92%")
    st.write("**Weather Report**")
    st.write("Location: Melbourne | Temp: 22C | Wind: 15 km/h")

st.divider()
st.caption(f"© 2026 Sentinel Access | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")