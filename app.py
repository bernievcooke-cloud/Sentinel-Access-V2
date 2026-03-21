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
    page_title="Surf, Weather, Sky, Trip Planner",
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
        padding-top: 1.0rem;
        padding-bottom: 1.0rem;
        max-width: 1180px;
    }
    .stButton > button {
        width: 100%;
        border-radius: 10px;
        font-weight: 600;
        padding-top: 0.55rem;
        padding-bottom: 0.55rem;
    }
    .small-note {
        color: #666;
        font-size: 0.92rem;
        margin-top: -0.35rem;
        margin-bottom: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# HELPERS
# ============================================================
APP_DIR = Path(__file__).resolve().parent


def safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def parse_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def call_worker_flex(fn, *, location_name: str, lat: float, lon: float):
    sig = inspect.signature(fn)
    params = sig.parameters
    kwargs = {}

    if "location_name" in params:
        kwargs["location_name"] = location_name
    elif "location" in params:
        kwargs["location"] = location_name
    elif "spot_name" in params:
        kwargs["spot_name"] = location_name
    elif "target" in params:
        kwargs["target"] = location_name

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


def locate_saved_file(path_or_result: Any) -> Optional[Path]:
    if isinstance(path_or_result, str) and path_or_result.strip():
        p = Path(path_or_result)
        if p.exists():
            return p
    return None


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


def load_locations() -> list[dict[str, Any]]:
    """
    Returns list of dicts with:
      display_name, latitude, longitude
    """
    fallback = [
        {
            "display_name": "Bells Beach",
            "latitude": -38.371,
            "longitude": 144.281,
        }
    ]

    if LocationManager is None:
        return fallback

    try:
        lm = LocationManager()
    except Exception:
        return fallback

    raw_candidates: list[dict[str, Any]] = []

    # Try common attributes first
    for attr in ["_locations", "locations"]:
        if hasattr(lm, attr):
            try:
                obj = getattr(lm, attr)
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if isinstance(value, dict):
                            display_name = (
                                value.get("display_name")
                                or value.get("name")
                                or str(key)
                            )
                            lat = (
                                value.get("latitude")
                                if value.get("latitude") is not None
                                else value.get("lat")
                            )
                            lon = (
                                value.get("longitude")
                                if value.get("longitude") is not None
                                else value.get("lon")
                                if value.get("lon") is not None
                                else value.get("lng")
                            )
                            raw_candidates.append(
                                {
                                    "display_name": str(display_name),
                                    "latitude": parse_float(lat),
                                    "longitude": parse_float(lon),
                                }
                            )
            except Exception:
                pass

    # Try common methods if nothing found
    if not raw_candidates:
        for method_name in ["list_locations", "all_locations", "get_all_locations"]:
            if hasattr(lm, method_name):
                try:
                    result = getattr(lm, method_name)()
                    if isinstance(result, dict):
                        for key, value in result.items():
                            if isinstance(value, dict):
                                display_name = (
                                    value.get("display_name")
                                    or value.get("name")
                                    or str(key)
                                )
                                lat = (
                                    value.get("latitude")
                                    if value.get("latitude") is not None
                                    else value.get("lat")
                                )
                                lon = (
                                    value.get("longitude")
                                    if value.get("longitude") is not None
                                    else value.get("lon")
                                    if value.get("lon") is not None
                                    else value.get("lng")
                                )
                                raw_candidates.append(
                                    {
                                        "display_name": str(display_name),
                                        "latitude": parse_float(lat),
                                        "longitude": parse_float(lon),
                                    }
                                )
                    elif isinstance(result, list):
                        for value in result:
                            if isinstance(value, dict):
                                display_name = (
                                    value.get("display_name")
                                    or value.get("name")
                                    or "Unknown"
                                )
                                lat = (
                                    value.get("latitude")
                                    if value.get("latitude") is not None
                                    else value.get("lat")
                                )
                                lon = (
                                    value.get("longitude")
                                    if value.get("longitude") is not None
                                    else value.get("lon")
                                    if value.get("lon") is not None
                                    else value.get("lng")
                                )
                                raw_candidates.append(
                                    {
                                        "display_name": str(display_name),
                                        "latitude": parse_float(lat),
                                        "longitude": parse_float(lon),
                                    }
                                )
                except Exception:
                    pass

    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in raw_candidates:
        name = safe_str(row.get("display_name")).strip()
        lat = parse_float(row.get("latitude"))
        lon = parse_float(row.get("longitude"))
        if not name or lat is None or lon is None:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(
            {
                "display_name": name,
                "latitude": lat,
                "longitude": lon,
            }
        )

    if not cleaned:
        return fallback

    cleaned.sort(key=lambda x: x["display_name"].casefold())
    return cleaned


def resolve_location(location_name: str, locations: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float]]:
    for row in locations:
        if row["display_name"] == location_name:
            return row["latitude"], row["longitude"]
    return None, None


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


# ============================================================
# SESSION STATE
# ============================================================
locations_data = load_locations()
location_names = [row["display_name"] for row in locations_data]
default_location = "Bells Beach" if "Bells Beach" in location_names else location_names[0]

if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "user_email" not in st.session_state:
    st.session_state.user_email = ""
if "selected_location" not in st.session_state:
    st.session_state.selected_location = default_location
if "selected_report_type" not in st.session_state:
    st.session_state.selected_report_type = "Surf"
if "last_outputs" not in st.session_state:
    st.session_state.last_outputs = {}


# ============================================================
# HEADER
# ============================================================
st.title("Surf, Weather, Sky, Trip Planner")
st.markdown(
    "<div class='small-note'>Generate location-based reports with the original Sentinel-style layout.</div>",
    unsafe_allow_html=True,
)

if IMPORT_ERRORS:
    with st.expander("Import diagnostics", expanded=False):
        for item in IMPORT_ERRORS:
            st.write(f"- {item}")

# ============================================================
# TOP FORM
# ============================================================
st.markdown("### Report details")

c1, c2, c3, c4 = st.columns([1.4, 1.5, 1.4, 1.1])

with c1:
    user_name = st.text_input(
        "User name",
        value=st.session_state.user_name,
        key="user_name_input",
        placeholder="Enter your name",
    )

with c2:
    user_email = st.text_input(
        "Email",
        value=st.session_state.user_email,
        key="user_email_input",
        placeholder="Enter your email",
    )

with c3:
    selected_location = st.selectbox(
        "Location",
        options=location_names,
        index=location_names.index(st.session_state.selected_location)
        if st.session_state.selected_location in location_names
        else 0,
        key="selected_location_input",
    )

with c4:
    report_type = st.selectbox(
        "Report type",
        options=["Surf", "Weather", "Sky", "Trip"],
        index=["Surf", "Weather", "Sky", "Trip"].index(st.session_state.selected_report_type)
        if st.session_state.selected_report_type in ["Surf", "Weather", "Sky", "Trip"]
        else 0,
        key="selected_report_type_input",
    )

st.session_state.user_name = user_name
st.session_state.user_email = user_email
st.session_state.selected_location = selected_location
st.session_state.selected_report_type = report_type

lat, lon = resolve_location(selected_location, locations_data)

if lat is None or lon is None:
    st.error("Selected location does not have valid latitude/longitude.")
    st.stop()

# ============================================================
# ACTION BUTTONS
# ============================================================
st.markdown("### Generate reports")

b1, b2, b3 = st.columns([1.2, 1.2, 3.0])

with b1:
    run_selected = st.button("Generate Selected Report", key="run_selected_btn")

with b2:
    run_all = st.button("Generate All Reports", key="run_all_btn")

with b3:
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
                location_name=selected_location,
                lat=lat,
                lon=lon,
            )
            elapsed = time.time() - started
            show_result_box(title, ok, f"{message} ({elapsed:.1f}s)", out_path)
            if out_path:
                st.session_state.last_outputs[title] = str(out_path)


def get_worker_by_label(label: str):
    if label == "Surf":
        return surf_generate_report
    if label == "Weather":
        return getattr(weather_worker, "generate_report", None) if weather_worker else None
    if label == "Sky":
        return getattr(sky_worker, "generate_report", None) if sky_worker else None
    if label == "Trip":
        return getattr(trip_worker, "generate_report", None) if trip_worker else None
    return None


if run_selected:
    do_run(report_type, get_worker_by_label(report_type))

if run_all:
    do_run("Surf", get_worker_by_label("Surf"))
    do_run("Weather", get_worker_by_label("Weather"))
    do_run("Sky", get_worker_by_label("Sky"))
    do_run("Trip", get_worker_by_label("Trip"))

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
    email_to_use = st.text_input(
        "Recipient email",
        value=st.session_state.user_email,
        key="recipient_email_input",
        placeholder="Enter recipient email",
    )

with email_col2:
    available_files = [""] + sorted(st.session_state.last_outputs.keys())
    selected_label = st.selectbox(
        "Choose report",
        options=available_files,
        key="email_report_choice",
    )

with email_col3:
    st.write("")
    st.write("")
    send_email_btn = st.button("Send Email", key="send_email_btn")

if send_email_btn:
    if not email_to_use.strip():
        st.error("Please enter a recipient email address.")
    elif not selected_label:
        st.error("Please choose a generated report first.")
    else:
        selected_path = st.session_state.last_outputs.get(selected_label)
        attachment = Path(selected_path) if selected_path else None
        ok, msg = try_send_email(
            recipient=email_to_use.strip(),
            subject=f"{selected_label} report - {selected_location}",
            body=(
                f"Hello {user_name or 'there'},\n\n"
                f"Attached is the {selected_label.lower()} report for {selected_location}.\n"
            ),
            attachment_path=str(attachment) if attachment else None,
        )
        if ok:
            st.success(msg)
        else:
            st.error(msg)

# ============================================================
# DEBUG
# ============================================================
with st.expander("Debug info", expanded=False):
    debug_rows = [
        {"item": "User name", "value": user_name},
        {"item": "User email", "value": user_email},
        {"item": "Location", "value": selected_location},
        {"item": "Latitude", "value": lat},
        {"item": "Longitude", "value": lon},
        {"item": "Selected report type", "value": report_type},
        {"item": "Surf worker", "value": surf_generate_report is not None},
        {"item": "Weather worker", "value": weather_worker is not None},
        {"item": "Sky worker", "value": sky_worker is not None},
        {"item": "Trip worker", "value": trip_worker is not None},
        {"item": "Email sender", "value": email_sender_mod is not None},
        {"item": "Location count", "value": len(location_names)},
    ]
    st.dataframe(pd.DataFrame(debug_rows), use_container_width=True)
