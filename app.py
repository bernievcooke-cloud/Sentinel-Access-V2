#!/usr/bin/env python3
from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Oz Trip Planner",
    layout="wide",
)

# ============================================================
# IMPORTS
# ============================================================
IMPORT_ERRORS: list[str] = []


def register_import_error(name: str, e: Exception) -> None:
    msg = f"{name} -> {type(e).__name__}: {e}"
    IMPORT_ERRORS.append(msg)
    print(f"IMPORT ERROR: {msg}")


try:
    from core.location_manager import LocationManager
except Exception as e:
    LocationManager = None  # type: ignore
    register_import_error("core.location_manager", e)

try:
    from core.surf_worker import generate_report as surf_generate_report
except Exception as e:
    surf_generate_report = None  # type: ignore
    register_import_error("core.surf_worker.generate_report", e)

try:
    import core.weather_worker as weather_worker
except Exception as e:
    weather_worker = None  # type: ignore
    register_import_error("core.weather_worker", e)

try:
    import core.sky_worker as sky_worker
except Exception as e:
    sky_worker = None  # type: ignore
    register_import_error("core.sky_worker", e)

try:
    import core.trip_worker as trip_worker
except Exception as e:
    trip_worker = None  # type: ignore
    register_import_error("core.trip_worker", e)

try:
    import core.email_sender as email_sender_mod
except Exception as e:
    email_sender_mod = None  # type: ignore
    register_import_error("core.email_sender", e)


# ============================================================
# STYLE
# ============================================================
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
        padding-bottom: 1rem;
        max-width: 1200px;
    }
    .stButton > button {
        width: 100%;
        border-radius: 10px;
        font-weight: 600;
        padding-top: 0.6rem;
        padding-bottom: 0.6rem;
    }
    .small-note {
        color: #666;
        font-size: 0.88rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# HELPERS
# ============================================================
APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def parse_float(value: str, fallback: Optional[float] = None) -> Optional[float]:
    txt = safe_str(value).strip()
    if not txt:
        return fallback
    try:
        return float(txt)
    except Exception:
        return fallback


def call_worker_flex(fn, *, location_name: str, lat: float, lon: float):
    """
    Calls worker generate_report functions flexibly depending on signature.
    """
    sig = inspect.signature(fn)
    params = sig.parameters

    kwargs = {}

    if "location_name" in params:
        kwargs["location_name"] = location_name
    elif "location" in params:
        kwargs["location"] = location_name
    elif "spot_name" in params:
        kwargs["spot_name"] = location_name

    if "lat" in params:
        kwargs["lat"] = lat
    elif "latitude" in params:
        kwargs["latitude"] = lat

    if "lon" in params:
        kwargs["lon"] = lon
    elif "lng" in params:
        kwargs["lng"] = lon
    elif "longitude" in params:
        kwargs["longitude"] = lon

    return fn(**kwargs)


def try_send_email(
    recipient: str,
    subject: str,
    body: str,
    attachment_path: str | None = None,
) -> tuple[bool, str]:
    if email_sender_mod is None:
        return False, "Email module not available."

    try:
        if hasattr(email_sender_mod, "send_email"):
            fn = email_sender_mod.send_email
            sig = inspect.signature(fn)
            kwargs = {}

            if "to_email" in sig.parameters:
                kwargs["to_email"] = recipient
            elif "recipient" in sig.parameters:
                kwargs["recipient"] = recipient
            elif "to" in sig.parameters:
                kwargs["to"] = recipient

            if "subject" in sig.parameters:
                kwargs["subject"] = subject
            if "body" in sig.parameters:
                kwargs["body"] = body
            if attachment_path:
                if "attachment_path" in sig.parameters:
                    kwargs["attachment_path"] = attachment_path
                elif "pdf_path" in sig.parameters:
                    kwargs["pdf_path"] = attachment_path
                elif "file_path" in sig.parameters:
                    kwargs["file_path"] = attachment_path

            fn(**kwargs)
            return True, "Email sent."
        return False, "Email function not found."
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def locate_saved_file(path_or_result: Any) -> Optional[Path]:
    if isinstance(path_or_result, str) and path_or_result.strip():
        p = Path(path_or_result)
        if p.exists():
            return p
    return None


def run_report(
    label: str,
    worker_fn,
    location_name: str,
    lat: float,
    lon: float,
) -> tuple[bool, str, Optional[Path]]:
    if worker_fn is None:
        return False, f"{label} worker not available.", None

    try:
        result = call_worker_flex(
            worker_fn,
            location_name=location_name,
            lat=lat,
            lon=lon,
        )
        out_path = locate_saved_file(result)
        if out_path is not None:
            return True, f"{label} report created successfully.", out_path
        return True, f"{label} ran successfully.", None
    except requests.HTTPError as e:
        return False, f"HTTP error: {e}", None
    except requests.RequestException as e:
        return False, f"Network error: {e}", None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


def get_location_defaults() -> tuple[str, float, float]:
    return "Bells Beach", -38.371, 144.281


def load_location_from_manager(location_name: str) -> tuple[Optional[float], Optional[float], str]:
    if LocationManager is None:
        return None, None, "Location manager not available."

    try:
        lm = LocationManager()
    except Exception as e:
        return None, None, f"Location manager failed to load: {e}"

    candidate_methods = [
        "get_location",
        "find_location",
        "lookup_location",
        "get",
    ]

    for method_name in candidate_methods:
        if hasattr(lm, method_name):
            try:
                result = getattr(lm, method_name)(location_name)
                if isinstance(result, dict):
                    lat = (
                        result.get("latitude")
                        or result.get("lat")
                        or result.get("LAT")
                    )
                    lon = (
                        result.get("longitude")
                        or result.get("lon")
                        or result.get("lng")
                        or result.get("LON")
                    )
                    if lat is not None and lon is not None:
                        return float(lat), float(lon), "Loaded from location manager."
            except Exception:
                pass

    return None, None, "Location not found in location manager."


def save_location_to_manager(location_name: str, lat: float, lon: float) -> str:
    if LocationManager is None:
        return "Location manager not available."

    try:
        lm = LocationManager()
    except Exception as e:
        return f"Location manager failed to load: {e}"

    candidate_methods = [
        "add_or_update_location",
        "save_location",
        "set_location",
        "add_location",
    ]

    for method_name in candidate_methods:
        if hasattr(lm, method_name):
            try:
                method = getattr(lm, method_name)
                sig = inspect.signature(method)
                kwargs = {}

                if "name" in sig.parameters:
                    kwargs["name"] = location_name
                elif "location_name" in sig.parameters:
                    kwargs["location_name"] = location_name
                elif "display_name" in sig.parameters:
                    kwargs["display_name"] = location_name

                if "latitude" in sig.parameters:
                    kwargs["latitude"] = lat
                elif "lat" in sig.parameters:
                    kwargs["lat"] = lat

                if "longitude" in sig.parameters:
                    kwargs["longitude"] = lon
                elif "lon" in sig.parameters:
                    kwargs["lon"] = lon
                elif "lng" in sig.parameters:
                    kwargs["lng"] = lon

                method(**kwargs)
                return "Location saved."
            except Exception:
                pass

    return "Could not find a compatible save method on LocationManager."


def show_result_box(title: str, ok: bool, message: str, output_path: Optional[Path]) -> None:
    if ok:
        st.success(f"{title}: {message}")
    else:
        st.error(f"{title}: {message}")

    if output_path and output_path.exists():
        st.caption(str(output_path))
        try:
            with open(output_path, "rb") as f:
                st.download_button(
                    label=f"Download {title}",
                    data=f.read(),
                    file_name=output_path.name,
                    mime="application/pdf",
                    key=f"dl_{title}_{output_path.name}",
                )
        except Exception as e:
            st.warning(f"Could not open output file for download: {e}")


# ============================================================
# SESSION STATE
# ============================================================
default_name, default_lat, default_lon = get_location_defaults()

if "location_name" not in st.session_state:
    st.session_state.location_name = default_name
if "lat" not in st.session_state:
    st.session_state.lat = default_lat
if "lon" not in st.session_state:
    st.session_state.lon = default_lon
if "recipient_email" not in st.session_state:
    st.session_state.recipient_email = ""
if "last_outputs" not in st.session_state:
    st.session_state.last_outputs = {}


# ============================================================
# HEADER
# ============================================================
st.title("Oz Trip Planner")
st.markdown("<div class='small-note'>Surf, weather, sky and trip report launcher</div>", unsafe_allow_html=True)

if IMPORT_ERRORS:
    with st.expander("Import diagnostics", expanded=False):
        for item in IMPORT_ERRORS:
            st.write(f"- {item}")

# ============================================================
# LOCATION PANEL
# ============================================================
with st.container():
    col1, col2, col3, col4 = st.columns([2.0, 1.0, 1.0, 1.0])

    with col1:
        location_name = st.text_input(
            "Location name",
            value=st.session_state.location_name,
            key="location_name_input",
        )

    with col2:
        lat_text = st.text_input(
            "Latitude",
            value=str(st.session_state.lat),
            key="lat_input",
        )

    with col3:
        lon_text = st.text_input(
            "Longitude",
            value=str(st.session_state.lon),
            key="lon_input",
        )

    lat = parse_float(lat_text, st.session_state.lat)
    lon = parse_float(lon_text, st.session_state.lon)

    with col4:
        st.write("")
        st.write("")
        if st.button("Load saved location", key="load_saved_location_btn"):
            loaded_lat, loaded_lon, msg = load_location_from_manager(location_name)
            if loaded_lat is not None and loaded_lon is not None:
                st.session_state.location_name = location_name
                st.session_state.lat = loaded_lat
                st.session_state.lon = loaded_lon
                st.success(f"{msg} {location_name}: {loaded_lat}, {loaded_lon}")
                st.rerun()
            else:
                st.warning(msg)

    csave1, csave2, csave3 = st.columns([1, 1, 2])
    with csave1:
        if st.button("Save location", key="save_location_btn"):
            if lat is None or lon is None:
                st.error("Latitude and longitude must be valid numbers.")
            else:
                msg = save_location_to_manager(location_name, lat, lon)
                st.info(msg)

    with csave2:
        if st.button("Use Bells Beach", key="bells_btn"):
            st.session_state.location_name = "Bells Beach"
            st.session_state.lat = -38.371
            st.session_state.lon = 144.281
            st.rerun()

    with csave3:
        st.caption("Tip: enter a location manually, or load/save it with LocationManager.")

# keep session updated
if lat is not None:
    st.session_state.lat = lat
if lon is not None:
    st.session_state.lon = lon
st.session_state.location_name = location_name

if lat is None or lon is None:
    st.error("Latitude and longitude must be valid numbers before running reports.")
    st.stop()

# ============================================================
# REPORT BUTTONS
# ============================================================
st.markdown("### Generate reports")

b1, b2, b3, b4 = st.columns(4)

with b1:
    run_surf = st.button("Generate Surf Report", key="run_surf_btn")
with b2:
    run_weather = st.button("Generate Weather Report", key="run_weather_btn")
with b3:
    run_sky = st.button("Generate Sky Report", key="run_sky_btn")
with b4:
    run_trip = st.button("Generate Trip Report", key="run_trip_btn")

ball1, ball2 = st.columns([2, 1])
with ball1:
    run_all = st.button("Generate All Reports", key="run_all_btn")
with ball2:
    clear_results = st.button("Clear Results", key="clear_results_btn")

if clear_results:
    st.session_state.last_outputs = {}
    st.rerun()

# ============================================================
# EXECUTION
# ============================================================
results_area = st.container()

def do_run(title: str, worker_fn):
    with results_area:
        with st.spinner(f"Running {title}..."):
            started = time.time()
            ok, message, out_path = run_report(
                label=title,
                worker_fn=worker_fn,
                location_name=location_name,
                lat=lat,
                lon=lon,
            )
            elapsed = time.time() - started
            show_result_box(title, ok, f"{message} ({elapsed:.1f}s)", out_path)
            if out_path:
                st.session_state.last_outputs[title] = str(out_path)


if run_surf:
    do_run("Surf", surf_generate_report)

if run_weather:
    weather_fn = getattr(weather_worker, "generate_report", None) if weather_worker else None
    do_run("Weather", weather_fn)

if run_sky:
    sky_fn = getattr(sky_worker, "generate_report", None) if sky_worker else None
    do_run("Sky", sky_fn)

if run_trip:
    trip_fn = getattr(trip_worker, "generate_report", None) if trip_worker else None
    do_run("Trip", trip_fn)

if run_all:
    weather_fn = getattr(weather_worker, "generate_report", None) if weather_worker else None
    sky_fn = getattr(sky_worker, "generate_report", None) if sky_worker else None
    trip_fn = getattr(trip_worker, "generate_report", None) if trip_worker else None

    do_run("Surf", surf_generate_report)
    do_run("Weather", weather_fn)
    do_run("Sky", sky_fn)
    do_run("Trip", trip_fn)

# ============================================================
# LAST OUTPUTS
# ============================================================
if st.session_state.last_outputs:
    st.markdown("### Last generated files")
    for label, p in st.session_state.last_outputs.items():
        path_obj = Path(p)
        if path_obj.exists():
            c1, c2 = st.columns([3, 1])
            with c1:
                st.write(f"**{label}** — {path_obj.name}")
                st.caption(str(path_obj))
            with c2:
                try:
                    with open(path_obj, "rb") as f:
                        st.download_button(
                            f"Download {label}",
                            data=f.read(),
                            file_name=path_obj.name,
                            mime="application/pdf",
                            key=f"repeat_dl_{label}_{path_obj.name}",
                        )
                except Exception as e:
                    st.warning(f"{label}: could not reopen file: {e}")

# ============================================================
# EMAIL SECTION
# ============================================================
st.markdown("### Email a generated file")

email_col1, email_col2, email_col3 = st.columns([2, 2, 1])

with email_col1:
    recipient_email = st.text_input(
        "Recipient email",
        value=st.session_state.recipient_email,
        key="recipient_email_input",
    )
    st.session_state.recipient_email = recipient_email

with email_col2:
    available_files = [""] + sorted(st.session_state.last_outputs.keys())
    selected_label = st.selectbox("Choose report", options=available_files, key="email_report_choice")

with email_col3:
    st.write("")
    st.write("")
    send_email_btn = st.button("Send Email", key="send_email_btn")

if send_email_btn:
    if not recipient_email.strip():
        st.error("Please enter a recipient email address.")
    elif not selected_label:
        st.error("Please choose a generated report first.")
    else:
        selected_path = st.session_state.last_outputs.get(selected_label)
        attachment = Path(selected_path) if selected_path else None
        ok, msg = try_send_email(
            recipient=recipient_email.strip(),
            subject=f"{selected_label} report - {location_name}",
            body=f"Attached is the {selected_label.lower()} report for {location_name}.",
            attachment_path=str(attachment) if attachment else None,
        )
        if ok:
            st.success(msg)
        else:
            st.error(msg)

# ============================================================
# FOOTER / DEBUG
# ============================================================
with st.expander("Debug info", expanded=False):
    debug_rows = [
        {"item": "Location", "value": location_name},
        {"item": "Latitude", "value": lat},
        {"item": "Longitude", "value": lon},
        {"item": "Surf worker", "value": surf_generate_report is not None},
        {"item": "Weather worker", "value": weather_worker is not None},
        {"item": "Sky worker", "value": sky_worker is not None},
        {"item": "Trip worker", "value": trip_worker is not None},
        {"item": "Email sender", "value": email_sender_mod is not None},
    ]
    st.dataframe(pd.DataFrame(debug_rows), use_container_width=True)
