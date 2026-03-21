#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
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
# CONSTANTS
# ============================================================
APP_DIR = Path(__file__).resolve().parent
CONFIG_DIR = APP_DIR / "config"
CONFIG_DIR.mkdir(exist_ok=True)
LOCATIONS_JSON_PATH = CONFIG_DIR / "locations.json"

AU_STATES = ["NSW", "VIC", "QLD", "SA", "WA", "TAS", "NT", "ACT"]
REPORT_OPTIONS = ["Surf", "Weather", "Sky", "Trip"]

DEFAULT_LOCATION_NAME = "Bells Beach"
DEFAULT_LAT = -38.371
DEFAULT_LON = 144.281

# ============================================================
# STYLE
# ============================================================
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.8rem;
        padding-bottom: 0.8rem;
        max-width: 1450px;
    }
    .stButton > button {
        width: 100%;
        border-radius: 10px;
        font-weight: 600;
        padding-top: 0.55rem;
        padding-bottom: 0.55rem;
    }
    .panel-box {
        border: 1px solid #e5e7eb;
        border-radius: 12px;
        padding: 14px 14px 12px 14px;
        background: #ffffff;
        margin-bottom: 0.8rem;
    }
    .panel-title {
        font-size: 1.05rem;
        font-weight: 700;
        margin-bottom: 0.45rem;
    }
    .small-note {
        color: #666;
        font-size: 0.9rem;
        margin-bottom: 0.75rem;
    }
    .success-banner {
        background: #e8f7e9;
        border: 1px solid #9ed7a3;
        color: #156b2a;
        padding: 0.7rem 0.9rem;
        border-radius: 10px;
        font-weight: 600;
        margin-bottom: 0.8rem;
    }
    .placeholder-card {
        border: 1px dashed #c9ced6;
        border-radius: 10px;
        padding: 0.8rem;
        min-height: 105px;
        margin-bottom: 0.55rem;
        background: #fafafa;
    }
    .placeholder-title {
        font-weight: 700;
        margin-bottom: 0.35rem;
    }
    .confirmed-box {
        border: 1px solid #d7dde5;
        border-radius: 10px;
        padding: 0.7rem 0.8rem;
        background: #fbfcfe;
        margin-top: 0.45rem;
        margin-bottom: 0.55rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# SESSION STATE
# ============================================================
def init_state() -> None:
    defaults = {
        "user_name": "",
        "user_email": "",
        "report_type": "Surf",
        "selected_location": DEFAULT_LOCATION_NAME,
        "trip_start": DEFAULT_LOCATION_NAME,
        "trip_dest_1": "",
        "trip_dest_2": "",
        "trip_dest_3": "",
        "progress_lines": ["System ready."],
        "email_status": "",
        "last_outputs": {},
        "geo_query": "",
        "geo_state": "VIC",
        "geo_results": [],
        "geo_selected_index": 0,
        "confirmed_reports": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()

# ============================================================
# HELPERS
# ============================================================
def safe_str(v: Any) -> str:
    return "" if v is None else str(v)


def parse_float(value: Any) -> Optional[float]:
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except Exception:
        return None


def log_progress(msg: str) -> None:
    lines = list(st.session_state.get("progress_lines", []))
    lines.append(msg)
    st.session_state["progress_lines"] = lines
    print(msg)


def reset_progress(msg: str = "System ready.") -> None:
    st.session_state["progress_lines"] = [msg]


def progress_text() -> str:
    return "\n".join(st.session_state.get("progress_lines", []))


def clear_transient_state() -> None:
    st.session_state["email_status"] = ""
    st.session_state["geo_results"] = []
    st.session_state["geo_selected_index"] = 0
    st.session_state["confirmed_reports"] = []
    st.session_state["last_outputs"] = {}
    reset_progress("Page refreshed.")


def make_safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in safe_str(name).replace(" ", "_"))


# ============================================================
# LOCATION MANAGEMENT
# ============================================================
def ensure_locations_json_exists() -> None:
    if LOCATIONS_JSON_PATH.exists():
        return

    seed = {
        DEFAULT_LOCATION_NAME: {
            "display_name": DEFAULT_LOCATION_NAME,
            "state": "VIC",
            "latitude": DEFAULT_LAT,
            "longitude": DEFAULT_LON,
        }
    }
    LOCATIONS_JSON_PATH.write_text(json.dumps(seed, indent=2), encoding="utf-8")


def load_locations_from_json() -> dict[str, dict]:
    ensure_locations_json_exists()
    try:
        raw = json.loads(LOCATIONS_JSON_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return raw
    except Exception:
        pass
    return {}


def save_locations_to_json(payload: dict[str, dict]) -> bool:
    try:
        LOCATIONS_JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def load_locations() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if LocationManager is not None:
        try:
            lm = LocationManager()
            for attr in ["_locations", "locations"]:
                if hasattr(lm, attr):
                    obj = getattr(lm, attr)
                    if isinstance(obj, dict):
                        for key, value in obj.items():
                            if isinstance(value, dict):
                                rows.append(
                                    {
                                        "display_name": str(value.get("display_name") or value.get("name") or key),
                                        "latitude": parse_float(value.get("latitude", value.get("lat"))),
                                        "longitude": parse_float(value.get("longitude", value.get("lon", value.get("lng")))),
                                        "state": safe_str(value.get("state", "")),
                                    }
                                )
        except Exception:
            pass

    raw_json = load_locations_from_json()
    for key, value in raw_json.items():
        if isinstance(value, dict):
            rows.append(
                {
                    "display_name": str(value.get("display_name") or value.get("name") or key),
                    "latitude": parse_float(value.get("latitude", value.get("lat"))),
                    "longitude": parse_float(value.get("longitude", value.get("lon", value.get("lng")))),
                    "state": safe_str(value.get("state", "")),
                }
            )

    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()

    for row in rows:
        name = safe_str(row.get("display_name")).strip()
        lat = parse_float(row.get("latitude"))
        lon = parse_float(row.get("longitude"))
        state = safe_str(row.get("state")).strip()

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
                "state": state,
            }
        )

    if not cleaned:
        cleaned = [
            {
                "display_name": DEFAULT_LOCATION_NAME,
                "latitude": DEFAULT_LAT,
                "longitude": DEFAULT_LON,
                "state": "VIC",
            }
        ]

    cleaned.sort(key=lambda x: x["display_name"].casefold())
    return cleaned


def resolve_location(name: str, locations: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float]]:
    for row in locations:
        if row["display_name"] == name:
            return row["latitude"], row["longitude"]
    return None, None


def save_location_entry(display_name: str, state: str, lat: float, lon: float) -> tuple[bool, str]:
    payload = load_locations_from_json()
    payload[display_name] = {
        "display_name": display_name,
        "state": state,
        "latitude": float(lat),
        "longitude": float(lon),
    }
    ok_json = save_locations_to_json(payload)

    lm_msg = ""
    if LocationManager is not None:
        try:
            lm = LocationManager()
            saved = False
            for method_name in ["add_or_update_location", "save_location", "set_location", "add_location"]:
                if hasattr(lm, method_name):
                    method = getattr(lm, method_name)
                    sig = inspect.signature(method)
                    kwargs = {}

                    if "name" in sig.parameters:
                        kwargs["name"] = display_name
                    elif "location_name" in sig.parameters:
                        kwargs["location_name"] = display_name
                    elif "display_name" in sig.parameters:
                        kwargs["display_name"] = display_name

                    if "state" in sig.parameters:
                        kwargs["state"] = state

                    if "latitude" in sig.parameters:
                        kwargs["latitude"] = float(lat)
                    elif "lat" in sig.parameters:
                        kwargs["lat"] = float(lat)

                    if "longitude" in sig.parameters:
                        kwargs["longitude"] = float(lon)
                    elif "lon" in sig.parameters:
                        kwargs["lon"] = float(lon)
                    elif "lng" in sig.parameters:
                        kwargs["lng"] = float(lon)

                    method(**kwargs)
                    saved = True
                    break

            if saved:
                lm_msg = " Saved to LocationManager too."
        except Exception as e:
            lm_msg = f" LocationManager save skipped: {e}"

    if ok_json:
        return True, f"Location saved successfully.{lm_msg}"
    return False, "Could not save location to locations.json."


# ============================================================
# GEOCODING
# ============================================================
def search_australian_locations(query: str, state_filter: str) -> tuple[list[dict[str, Any]], str]:
    query = safe_str(query).strip()
    if not query:
        return [], "Please enter a location search term."

    try:
        url = (
            "https://geocoding-api.open-meteo.com/v1/search"
            f"?name={requests.utils.quote(query)}"
            "&count=10"
            "&language=en"
            "&format=json"
        )
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("results", []) or []

        filtered: list[dict[str, Any]] = []
        for row in results:
            country_code = safe_str(row.get("country_code")).upper()
            admin1 = safe_str(row.get("admin1")).upper()
            name = safe_str(row.get("name"))
            lat = parse_float(row.get("latitude"))
            lon = parse_float(row.get("longitude"))

            if country_code != "AU":
                continue
            if state_filter and admin1 != state_filter.upper():
                continue
            if not name or lat is None or lon is None:
                continue

            filtered.append(
                {
                    "display_name": name,
                    "state": admin1,
                    "latitude": lat,
                    "longitude": lon,
                    "admin2": safe_str(row.get("admin2")),
                }
            )

        if not filtered:
            return [], "No matching Australian locations found for that state."

        return filtered, f"Found {len(filtered)} matching location(s)."

    except Exception as e:
        return [], f"Location search failed: {e}"


# ============================================================
# WORKER / EMAIL HELPERS
# ============================================================
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
        if not hasattr(email_sender_mod, "send_email"):
            return False, "Email function not found."

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
            elif "attachments" in sig.parameters:
                kwargs["attachments"] = [attachment_path]

        if "username" in sig.parameters:
            kwargs["username"] = st.session_state.user_name or "there"

        fn(**kwargs)
        return True, "Email sent."

    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


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


def run_standard_report(label: str, location_name: str, lat: float, lon: float) -> tuple[bool, str, Optional[Path]]:
    worker_fn = get_worker_by_label(label)
    if worker_fn is None:
        return False, f"{label} worker not available.", None

    try:
        result = call_worker_flex(worker_fn, location_name=location_name, lat=lat, lon=lon)
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


def run_trip_report(start_location: str, destinations: list[str]) -> tuple[bool, str, Optional[Path]]:
    if trip_worker is None:
        return False, "Trip worker not available.", None

    route = [start_location] + [d for d in destinations if safe_str(d).strip()]
    if len(route) < 2:
        return False, "Trip requires at least a start location and 1 destination.", None

    trip_route_fn = getattr(trip_worker, "generate_trip_report_from_route", None)
    try:
        if callable(trip_route_fn):
            result = trip_route_fn(route=route)
            out_path = locate_saved_file(result)
            if out_path is not None:
                return True, "Trip report created successfully.", out_path
            return True, "Trip ran successfully.", None

        fallback_fn = getattr(trip_worker, "generate_report", None)
        if fallback_fn is None:
            return False, "Trip worker has no usable report function.", None

        start_lat, start_lon = resolve_location(start_location, load_locations())
        if start_lat is None or start_lon is None:
            return False, "Could not resolve trip start location.", None

        result = call_worker_flex(
            fallback_fn,
            location_name=start_location,
            lat=start_lat,
            lon=start_lon,
        )
        out_path = locate_saved_file(result)
        if out_path is not None:
            return True, "Trip placeholder report created.", out_path
        return True, "Trip ran successfully.", None

    except Exception as e:
        return False, f"{type(e).__name__}: {e}", None


def auto_email_report(
    user_name: str,
    user_email: str,
    report_label: str,
    location_name: str,
    file_path: Optional[Path],
) -> tuple[bool, str]:
    if not user_email.strip():
        return False, "No user email entered."

    if file_path is None or not file_path.exists():
        return False, "No output file available to email."

    subject = f"{report_label} report - {location_name}"
    body = (
        f"Hello {user_name.strip() or 'there'},\n\n"
        f"Attached is your {report_label.lower()} report for {location_name}.\n\n"
        f"Regards,\nSurf, Weather, Sky, Trip Planner"
    )
    return try_send_email(
        recipient=user_email.strip(),
        subject=subject,
        body=body,
        attachment_path=str(file_path),
    )


# ============================================================
# CONFIRMATION HELPERS
# ============================================================
def add_confirmed_report(report_type: str, location_name: str) -> tuple[bool, str]:
    confirmed = list(st.session_state.get("confirmed_reports", []))
    item = f"{report_type} | {location_name}"
    if item in confirmed:
        return False, "That report/location combination is already confirmed."
    confirmed.append(item)
    st.session_state.confirmed_reports = confirmed
    return True, f"Confirmed: {item}"


def set_confirmed_trip(start_location: str, dest1: str, dest2: str, dest3: str) -> tuple[bool, str]:
    route_parts = [start_location] + [d for d in [dest1, dest2, dest3] if safe_str(d).strip()]
    if len(route_parts) < 2:
        return False, "Trip confirmation needs a start location and at least 1 destination."

    item = "Trip | " + " -> ".join(route_parts)
    confirmed = list(st.session_state.get("confirmed_reports", []))
    if item in confirmed:
        return False, "That trip route is already confirmed."

    confirmed.append(item)
    st.session_state.confirmed_reports = confirmed
    return True, f"Confirmed: {item}"


def clear_confirmed_reports() -> None:
    st.session_state.confirmed_reports = []


# ============================================================
# LOAD LOCATIONS
# ============================================================
locations_data = load_locations()
location_names = [row["display_name"] for row in locations_data]

if st.session_state.selected_location not in location_names:
    st.session_state.selected_location = DEFAULT_LOCATION_NAME if DEFAULT_LOCATION_NAME in location_names else location_names[0]

if st.session_state.trip_start not in location_names:
    st.session_state.trip_start = st.session_state.selected_location

# ============================================================
# HEADER
# ============================================================
st.title("Surf, Weather, Sky, Trip Planner")
st.markdown(
    "<div class='small-note'>Sentinel-style layout with progress logging, confirmed multi-report selection, and auto-email sending.</div>",
    unsafe_allow_html=True,
)

if IMPORT_ERRORS:
    with st.expander("Import diagnostics", expanded=False):
        for item in IMPORT_ERRORS:
            st.write(f"- {item}")

# ============================================================
# 3-COLUMN LAYOUT
# ============================================================
left_col, middle_col, right_col = st.columns([1.05, 1.4, 1.0], gap="large")

# ------------------------------------------------------------
# LEFT PANEL
# ------------------------------------------------------------
with left_col:
    st.markdown("<div class='panel-box'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-title'>User instructions</div>", unsafe_allow_html=True)
    st.markdown(
        """
        1. Enter your name and email.  
        2. Choose a report type and location.  
        3. Use **Confirm Selection** to add more reports.  
        4. For Trip, choose up to 3 destinations and confirm the route.  
        5. Use Add New Location to search and save more places.  
        6. Click **Generate Report/s**.  
        7. Reports are generated and emailed to your email address.
        """
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-box'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-title'>User details</div>", unsafe_allow_html=True)

    st.session_state.user_name = st.text_input(
        "User name",
        value=st.session_state.user_name,
        key="user_name_input",
        placeholder="Enter your name",
    )

    st.session_state.user_email = st.text_input(
        "User email",
        value=st.session_state.user_email,
        key="user_email_input",
        placeholder="Enter your email",
    )

    if st.button("Refresh Page", key="refresh_page_btn"):
        clear_transient_state()
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------
# MIDDLE PANEL
# ------------------------------------------------------------
with middle_col:
    st.markdown("<div class='panel-box'>", unsafe_allow_html=True)
    st.markdown("<div class='panel-title'>Report controls</div>", unsafe_allow_html=True)

    st.session_state.report_type = st.selectbox(
        "Select report type",
        options=REPORT_OPTIONS,
        index=REPORT_OPTIONS.index(st.session_state.report_type)
        if st.session_state.report_type in REPORT_OPTIONS
        else 0,
        key="report_type_input",
    )

    st.session_state.selected_location = st.selectbox(
        "Select location",
        options=location_names,
        index=location_names.index(st.session_state.selected_location)
        if st.session_state.selected_location in location_names
        else 0,
        key="selected_location_input",
    )

    if st.session_state.report_type == "Trip":
        trip_location_options = [""] + location_names

        st.session_state.trip_start = st.selectbox(
            "Location",
            options=location_names,
            index=location_names.index(st.session_state.trip_start)
            if st.session_state.trip_start in location_names
            else 0,
            key="trip_start_input",
        )

        st.session_state.trip_dest_1 = st.selectbox(
            "1st destination",
            options=trip_location_options,
            index=trip_location_options.index(st.session_state.trip_dest_1)
            if st.session_state.trip_dest_1 in trip_location_options
            else 0,
            key="trip_dest_1_input",
        )

        st.session_state.trip_dest_2 = st.selectbox(
            "2nd destination",
            options=trip_location_options,
            index=trip_location_options.index(st.session_state.trip_dest_2)
            if st.session_state.trip_dest_2 in trip_location_options
            else 0,
            key="trip_dest_2_input",
        )

        st.session_state.trip_dest_3 = st.selectbox(
            "3rd destination",
            options=trip_location_options,
            index=trip_location_options.index(st.session_state.trip_dest_3)
            if st.session_state.trip_dest_3 in trip_location_options
            else 0,
            key="trip_dest_3_input",
        )

    st.markdown("#### Confirm selection")
    confirm_c1, confirm_c2 = st.columns([1, 1])

    with confirm_c1:
        if st.button("Confirm Selection", key="confirm_selection_btn"):
            if st.session_state.report_type == "Trip":
                ok, msg = set_confirmed_trip(
                    start_location=st.session_state.trip_start,
                    dest1=st.session_state.trip_dest_1,
                    dest2=st.session_state.trip_dest_2,
                    dest3=st.session_state.trip_dest_3,
                )
            else:
                ok, msg = add_confirmed_report(
                    report_type=st.session_state.report_type,
                    location_name=st.session_state.selected_location,
                )
            log_progress(msg)

    with confirm_c2:
        if st.button("Clear Confirmed", key="clear_confirmed_btn"):
            clear_confirmed_reports()
            log_progress("Cleared all confirmed report selections.")

    confirmed_reports = st.session_state.get("confirmed_reports", [])
    if confirmed_reports:
        st.markdown("<div class='confirmed-box'>", unsafe_allow_html=True)
        st.write("**Confirmed reports to generate:**")
        for item in confirmed_reports:
            st.write(f"- {item}")
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='confirmed-box'>No confirmed reports yet.</div>", unsafe_allow_html=True)

    st.markdown("#### Add new location")
    st.session_state.geo_query = st.text_input(
        "Search new location",
        value=st.session_state.geo_query,
        key="geo_query_input",
        placeholder="Example: Noosa Heads",
    )

    st.session_state.geo_state = st.selectbox(
        "Confirm state",
        options=AU_STATES,
        index=AU_STATES.index(st.session_state.geo_state)
        if st.session_state.geo_state in AU_STATES
        else 0,
        key="geo_state_input",
    )

    add_c1, add_c2 = st.columns([1, 1])

    with add_c1:
        if st.button("Auto Find Location", key="auto_find_location_btn"):
            reset_progress("Searching for location...")
            results, msg = search_australian_locations(st.session_state.geo_query, st.session_state.geo_state)
            st.session_state.geo_results = results
            st.session_state.geo_selected_index = 0
            log_progress(msg)

    with add_c2:
        if st.button("Confirm & Add Location", key="confirm_add_location_btn"):
            results = st.session_state.get("geo_results", [])
            idx = int(st.session_state.get("geo_selected_index", 0))

            if not results:
                log_progress("No searched location available to confirm. Use Auto Find Location first.")
            elif idx < 0 or idx >= len(results):
                log_progress("Selected location result is out of range.")
            else:
                chosen = results[idx]
                ok, msg = save_location_entry(
                    display_name=chosen["display_name"],
                    state=chosen["state"],
                    lat=float(chosen["latitude"]),
                    lon=float(chosen["longitude"]),
                )
                log_progress(msg)
                if ok:
                    st.session_state.selected_location = chosen["display_name"]
                    st.session_state.trip_start = chosen["display_name"]
                    st.session_state.geo_query = ""
                    st.session_state.geo_results = []
                    st.session_state.geo_selected_index = 0
                    st.rerun()

    geo_results = st.session_state.get("geo_results", [])
    if geo_results:
        geo_labels = [
            f"{r['display_name']} ({r['state']})  lat {r['latitude']:.5f}, lon {r['longitude']:.5f}"
            for r in geo_results
        ]
        st.session_state.geo_selected_index = st.selectbox(
            "Search results",
            options=list(range(len(geo_labels))),
            format_func=lambda i: geo_labels[i],
            index=min(int(st.session_state.get("geo_selected_index", 0)), len(geo_labels) - 1),
            key="geo_selected_index_input",
        )

    st.markdown("#### System progress")
    st.text_area(
        "System progress",
        value=progress_text(),
        height=240,
        key="progress_display_box",
        disabled=True,
        label_visibility="collapsed",
    )

    st.markdown("</div>", unsafe_allow_html=True)

# ------------------------------------------------------------
# RIGHT PANEL
# ------------------------------------------------------------
with right_col:
    if st.button("Generate Report/s", key="generate_reports_btn"):
        reset_progress("Starting report generation...")
        st.session_state.email_status = ""

        if not st.session_state.user_email.strip():
            log_progress("User email is required before generating and sending reports.")
        else:
            confirmed = list(st.session_state.get("confirmed_reports", []))

            if not confirmed:
                log_progress("No confirmed reports selected. Please use Confirm Selection first.")
            else:
                email_messages: list[str] = []

                for item in confirmed:
                    if item.startswith("Trip | "):
                        route_text = item.replace("Trip | ", "", 1)
                        route_parts = [p.strip() for p in route_text.split("->")]
                        start_location = route_parts[0]
                        destinations = route_parts[1:]

                        log_progress(f"Running Trip for route: {route_text}")
                        ok, msg, output_path = run_trip_report(
                            start_location=start_location,
                            destinations=destinations,
                        )
                        log_progress(msg)

                        if ok and output_path:
                            st.session_state.last_outputs["Trip"] = str(output_path)
                            e_ok, e_msg = auto_email_report(
                                user_name=st.session_state.user_name,
                                user_email=st.session_state.user_email,
                                report_label="Trip",
                                location_name=start_location,
                                file_path=output_path,
                            )
                            log_progress(e_msg)
                            email_messages.append("Trip sent" if e_ok else "Trip email failed")

                    else:
                        try:
                            report_label, location_name = [x.strip() for x in item.split("|", 1)]
                        except Exception:
                            log_progress(f"Skipping malformed confirmed item: {item}")
                            continue

                        lat, lon = resolve_location(location_name, load_locations())
                        if lat is None or lon is None:
                            log_progress(f"Location '{location_name}' does not have valid coordinates.")
                            continue

                        log_progress(f"Running {report_label} for {location_name}...")
                        ok, msg, output_path = run_standard_report(report_label, location_name, lat, lon)
                        log_progress(msg)

                        if ok and output_path:
                            st.session_state.last_outputs[report_label] = str(output_path)
                            e_ok, e_msg = auto_email_report(
                                user_name=st.session_state.user_name,
                                user_email=st.session_state.user_email,
                                report_label=report_label,
                                location_name=location_name,
                                file_path=output_path,
                            )
                            log_progress(e_msg)
                            email_messages.append(f"{report_label} sent" if e_ok else f"{report_label} email failed")

                st.session_state.email_status = (
                    f"Email status: {', '.join(email_messages)} to {st.session_state.user_email}"
                    if email_messages
                    else "No reports were emailed."
                )

    email_status = st.session_state.get("email_status", "")
    if email_status:
        st.markdown(
            f"<div class='success-banner'>{email_status}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div class='success-banner'>Email confirmation will appear here after a report is sent.</div>",
            unsafe_allow_html=True,
        )

    for label in ["Surf", "Weather", "Sky", "Trip"]:
        p = st.session_state.last_outputs.get(label)
        st.markdown("<div class='placeholder-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='placeholder-title'>{label} placeholder</div>", unsafe_allow_html=True)
        if p and Path(p).exists():
            path_obj = Path(p)
            st.write(f"Latest generated: {path_obj.name}")
            st.caption(str(path_obj))
        else:
            st.write(f"No {label.lower()} report generated yet.")
        st.markdown("</div>", unsafe_allow_html=True)
