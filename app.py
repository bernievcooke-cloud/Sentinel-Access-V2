#!/usr/bin/env python3
from __future__ import annotations

import math
import os
import platform
from datetime import datetime
from io import BytesIO
from zoneinfo import ZoneInfo

import#!/usr/bin/env python3
from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st

# ============================================================
# PAGE CONFIG FIRST
# ============================================================
st.set_page_config(page_title="Report x Type & Location", layout="wide")

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
    import core.sky_worker as sky_worker
except Exception as e:
    sky_worker = None  # type: ignore
    register_import_error("core.sky_worker", e)

try:
    import core.weather_worker as weather_worker
except Exception as e:
    weather_worker = None  # type: ignore
    register_import_error("core.weather_worker", e)

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
      .block-container { padding-top: 1rem; padding-bottom: 1rem; max-width: 1500px; }
      h1 { margin: 0.2rem 0 0.7rem 0 !important; }

      button[data-testid="stBaseButton-primary"] {
        background-color: #1f8f3a !important;
        border-color: #1f8f3a !important;
        color: white !important;
        font-weight: 600 !important;
      }
      button[data-testid="stBaseButton-primary"]:hover {
        background-color: #17702d !important;
        border-color: #17702d !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Surf, Weather, Sky, Trip Planner")

# Show import errors clearly at top of page
if IMPORT_ERRORS:
    st.error("One or more modules failed to import.")
    for err in IMPORT_ERRORS:
        st.caption(err)


# ============================================================
# SESSION STATE DEFAULTS
# ============================================================
if "progress_log" not in st.session_state:
    st.session_state.progress_log = []
if "confirmed_ok" not in st.session_state:
    st.session_state.confirmed_ok = False
if "confirmed_payload" not in st.session_state:
    st.session_state.confirmed_payload = None
if "outputs" not in st.session_state:
    st.session_state.outputs = {}
if "new_location_candidates" not in st.session_state:
    st.session_state.new_location_candidates = []
if "chosen_geo_label" not in st.session_state:
    st.session_state.chosen_geo_label = None
if "location_names" not in st.session_state:
    st.session_state.location_names = []

if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "final_banner" not in st.session_state:
    st.session_state.final_banner = None


# ============================================================
# PROGRESS LOG
# ============================================================
def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    st.session_state.progress_log.append(f"{ts} — {msg}")


def render_progress_box(height: int = 320) -> None:
    st.text_area(
        "System progress",
        value="\n".join(st.session_state.progress_log) if st.session_state.progress_log else "",
        height=height,
        disabled=True,
    )


def reset_app_state() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# ============================================================
# HELPERS
# ============================================================
def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def extract_lat_lon(payload: Any) -> tuple[Optional[float], Optional[float], str]:
    if payload is None:
        return None, None, "payload=None"

    if isinstance(payload, (list, tuple)) and len(payload) >= 2:
        return _to_float(payload[0]), _to_float(payload[1]), "payload=list/tuple"

    if not isinstance(payload, dict):
        return None, None, f"payload_type={type(payload).__name__}"

    candidates_lat = ["latitude", "lat", "LAT", "Latitude", "y", "Y"]
    candidates_lon = ["longitude", "lon", "lng", "LON", "LNG", "Longitude", "x", "X"]

    lat = None
    lon = None

    for k in candidates_lat:
        if k in payload:
            lat = _to_float(payload.get(k))
            if lat is not None:
                break

    for k in candidates_lon:
        if k in payload:
            lon = _to_float(payload.get(k))
            if lon is not None:
                break

    return lat, lon, f"payload_keys={sorted(list(payload.keys()))}"


def state_to_admin1(state_code: str) -> str:
    mapping = {
        "VIC": "Victoria",
        "NSW": "New South Wales",
        "QLD": "Queensland",
        "SA": "South Australia",
        "WA": "Western Australia",
        "TAS": "Tasmania",
        "NT": "Northern Territory",
        "ACT": "Australian Capital Territory",
    }
    return mapping.get(state_code, state_code)


def geocode_au(name: str, state_code: str, timeout: int = 12) -> list[dict[str, Any]]:
    name = (name or "").strip()
    if not name:
        return []

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": name, "count": 10, "language": "en", "format": "json"}
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    j = r.json() or {}
    results = j.get("results") or []

    target_admin1 = state_to_admin1(state_code)

    out: list[dict[str, Any]] = []
    for item in results:
        if item.get("country_code") != "AU":
            continue
        admin1 = item.get("admin1") or ""
        score = 2 if target_admin1.lower() in admin1.lower() else 1
        out.append(
            {
                "label": f"{item.get('name','?')} — {admin1} — AU",
                "lat": item.get("latitude"),
                "lon": item.get("longitude"),
                "admin1": admin1,
                "score": score,
            }
        )

    out.sort(key=lambda x: x.get("score", 0), reverse=True)
    return out


def maybe_add_attachment(attachments: list[str], maybe_path: Any, label: str = "") -> None:
    prefix = f"[{label}] " if label else ""
    if not maybe_path:
        log(f"{prefix}ATTACH: skipped (worker returned None/empty).")
        return

    p = Path(str(maybe_path))

    if p.suffix.lower() != ".pdf":
        log(f"{prefix}ATTACH: skipped (not a PDF): {p}")
        return

    if str(p) in attachments:
        log(f"{prefix}ATTACH: skipped (duplicate): {p.name}")
        return

    try:
        if not p.exists():
            log(f"{prefix}ATTACH: skipped (file missing): {p}")
            return

        size = p.stat().st_size
        if size <= 1000:
            log(f"{prefix}ATTACH: skipped (file too small: {size} bytes): {p.name}")
            return

        attachments.append(str(p))
        log(f"{prefix}ATTACH: ✅ added {p.name} ({size} bytes)")
    except Exception as e:
        log(f"{prefix}ATTACH: skipped (error checking file): {e}")


def call_worker_generate_report(module_or_fn: Any, *args, logger=None, **kwargs) -> Any:
    if module_or_fn is None:
        raise RuntimeError("Worker is None (import failed).")

    fn = module_or_fn
    if not callable(module_or_fn):
        fn = getattr(module_or_fn, "generate_report", None)

    if not callable(fn):
        name = getattr(module_or_fn, "__name__", "worker")
        raise RuntimeError(f"{name}.generate_report not found.")

    if logger is not None:
        try:
            sig = inspect.signature(fn)
            if "logger" in sig.parameters:
                kwargs["logger"] = logger
        except Exception:
            pass

    return fn(*args, **kwargs)


def send_email_via_sender(
    to_email: str,
    username: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None,
) -> tuple[bool, str]:
    attachments = attachments or []

    if email_sender_mod is None:
        return False, "core.email_sender failed to import."

    fn = getattr(email_sender_mod, "send_email", None)
    if not callable(fn):
        return False, "core.email_sender.send_email not found."

    try:
        fn(to_email, subject, body, attachments=attachments, username=username or "there")
        return True, "Email sent."
    except Exception as e:
        return False, str(e)


# ============================================================
# LOCATION MANAGER
# ============================================================
if LocationManager is None:
    st.error("LocationManager import failed. Expected: core/location_manager.py")
    st.stop()

if "lm" not in st.session_state:
    st.session_state.lm = LocationManager()
lm = st.session_state.lm

required_methods = ["locations", "get", "add_or_update"]
missing = [m for m in required_methods if not hasattr(lm, m)]
if missing:
    st.error(f"LocationManager missing expected methods: {', '.join(missing)}")
    st.stop()


def _refresh_locations() -> None:
    try:
        lm.reload()
    except Exception:
        st.session_state.lm = LocationManager()
    st.session_state.location_names = list(st.session_state.lm.locations())


if not st.session_state.location_names:
    st.session_state.location_names = list(lm.locations())

location_names = st.session_state.location_names
if not location_names:
    st.error("0 locations loaded. Check config/locations.json.")
    st.stop()


# ============================================================
# ACTIONS (callbacks)
# ============================================================
def confirm_action() -> None:
    st.session_state.confirmed_ok = False
    st.session_state.confirmed_payload = None
    st.session_state.final_banner = None

    user_name = st.session_state.get("user_name", "")
    user_email = st.session_state.get("user_email", "")
    report_types = st.session_state.get("report_types") or []
    main_location = st.session_state.get("main_location")

    if not str(user_name).strip():
        log("ERROR: Please enter your name.")
        return

    if not str(user_email).strip():
        log("ERROR: Please enter your email.")
        return

    if "@" not in user_email or "." not in user_email:
        log("ERROR: Please enter a valid email address.")
        return

    if not report_types:
        log("ERROR: Please select at least one report.")
        return

    if not main_location:
        log("ERROR: Please select a location.")
        return

    trip_payload = None
    if "Trip" in report_types:
        trip_stops = [
            st.session_state.get("trip_start"),
            st.session_state.get("trip_stop1"),
            st.session_state.get("trip_stop2"),
        ]
        if not all(trip_stops):
            log("ERROR: Please complete all Trip locations.")
            return

        trip_payload = {
            "start": st.session_state.get("trip_start"),
            "stop1": st.session_state.get("trip_stop1"),
            "stop2": st.session_state.get("trip_stop2"),
            "fuel_type": st.session_state.get("fuel_type"),
            "fuel_l_per_100km": float(st.session_state.get("fuel_l_per_100km", 9.5)),
            "fuel_price": float(st.session_state.get("fuel_price", 2.10)),
        }

    summary_parts = [
        f"User: {user_name or '(no name)'} | {user_email or '(no email)'}",
        f"Reports: {', '.join(report_types) if report_types else '(none)'}",
        f"Location: {main_location}",
    ]
    if trip_payload:
        summary_parts.append(f"Trip: {trip_payload['start']} → {trip_payload['stop1']} → {trip_payload['stop2']}")

    st.session_state.confirmed_payload = {
        "user": {"name": user_name, "email": user_email},
        "report_types": report_types,
        "main_location": main_location,
        "trip": trip_payload,
        "summary": " | ".join(summary_parts),
    }
    st.session_state.confirmed_ok = True

    log("Confirmed selections.")
    log(st.session_state.confirmed_payload["summary"])


def add_location_action() -> None:
    name = (st.session_state.get("new_loc_name") or "").strip()
    state = st.session_state.get("new_state") or "VIC"
    chosen_label = st.session_state.get("chosen_geo_label")
    candidates = st.session_state.get("new_location_candidates", []) or []

    if not name:
        log("ERROR: Enter a new location name first.")
        return
    if not candidates:
        log("ERROR: Click 'Find matches' first.")
        return
    if not chosen_label:
        log("ERROR: Select a match from the dropdown before saving.")
        return

    chosen = None
    for c in candidates:
        if c.get("label") == chosen_label:
            chosen = c
            break

    if not chosen:
        log("ERROR: Selected match not found. Click 'Find matches' again.")
        return

    try:
        lat = float(chosen["lat"])
        lon = float(chosen["lon"])
    except Exception:
        log("ERROR: Match did not contain valid lat/lon.")
        return

    try:
        saved_name = lm.add_or_update(name, lat, lon, state=state)
        _refresh_locations()
        log(f"✅ Location saved: {saved_name} ({state}) [{lat:.5f}, {lon:.5f}]")
        st.session_state.main_location = saved_name
        st.session_state.new_loc_name = ""
        st.session_state.new_location_candidates = []
        st.session_state.chosen_geo_label = None
        st.rerun()
    except Exception as e:
        log(f"ERROR saving new location: {e}")


def generate_pay_action() -> None:
    if not st.session_state.get("confirmed_ok"):
        log("ERROR: Please Confirm selections first.")
        return

    st.session_state.is_running = True
    st.session_state.final_banner = {
        "type": "info",
        "title": "Running…",
        "detail": "Generating reports and preparing email.",
    }

    st.session_state.progress_log = []
    st.session_state.outputs = {}

    payload = st.session_state.get("confirmed_payload") or {}
    user = payload.get("user") or {}
    report_types: list[str] = payload.get("report_types") or []
    main_location = payload.get("main_location")
    trip_cfg = payload.get("trip")

    if not report_types:
        log("ERROR: No report types selected.")
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Nothing to run",
            "detail": "No report types were selected.",
        }
        return

    log(payload.get("summary", "Starting run…"))

    output_dir = str(Path.cwd() / "outputs")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    loc_payload = lm.get(main_location)
    if loc_payload is None:
        log("ERROR: main location not found in LocationManager.")
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Location error",
            "detail": "Main location was not found in LocationManager.",
        }
        return

    lat, lon, dbg = extract_lat_lon(loc_payload)
    if lat is None or lon is None:
        log("ERROR: Selected location missing latitude/longitude in locations.json.")
        log(f"DEBUG: {dbg}")
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Location missing coordinates",
            "detail": f"Selected location has no lat/lon. {dbg}",
        }
        return

    surf_profile = {}
    if isinstance(loc_payload, dict) and isinstance(loc_payload.get("surf_profile"), dict):
        surf_profile = loc_payload["surf_profile"]

    attachments: list[str] = []
    ran_any = False
    errors: list[str] = []

    order = ["Surf", "Sky", "Weather", "Trip"]
    selected_in_order = [x for x in order if x in report_types]

    log("RUN START ✅ (screen may dim while Streamlit runs — that is normal)")

    for rt in selected_in_order:
        log(f"--- Running {rt.upper()} ---")
        try:
            if rt == "Surf":
                if surf_generate_report is None:
                    raise RuntimeError("core.surf_worker.generate_report import failed. See import error shown above.")
                pdf_path = call_worker_generate_report(
                    surf_generate_report,
                    main_location,
                    [lat, lon, surf_profile],
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Surf"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Surf")
                if pdf_path:
                    ran_any = True
                log(f"SURF {'complete' if pdf_path else 'failed'}.")

            elif rt == "Sky":
                if sky_worker is None:
                    raise RuntimeError("core.sky_worker import failed. See import error shown above.")
                pdf_path = call_worker_generate_report(
                    sky_worker,
                    main_location,
                    [lat, lon],
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Sky"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Sky")
                if pdf_path:
                    ran_any = True
                log(f"SKY {'complete' if pdf_path else 'failed'}.")

            elif rt == "Weather":
                if weather_worker is None:
                    raise RuntimeError("core.weather_worker import failed. See import error shown above.")
                pdf_path = call_worker_generate_report(
                    weather_worker,
                    main_location,
                    [lat, lon],
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Weather"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Weather")
                if pdf_path:
                    ran_any = True
                log(f"WEATHER {'complete' if pdf_path else 'failed'}.")

            elif rt == "Trip":
                if trip_worker is None:
                    raise RuntimeError("core.trip_worker import failed. See import error shown above.")
                if not trip_cfg:
                    raise RuntimeError("Trip config missing. Confirm again with Trip selected.")
                route = [trip_cfg["start"], trip_cfg["stop1"], trip_cfg["stop2"]]
                trip_data = {
                    "route": route,
                    "fuel_type": trip_cfg.get("fuel_type", "Petrol"),
                    "fuel_l_per_100km": float(trip_cfg.get("fuel_l_per_100km", 9.5)),
                    "fuel_price": float(trip_cfg.get("fuel_price", 2.10)),
                }
                trip_name = f"{route[0]}_{route[-1]}"
                pdf_path = call_worker_generate_report(
                    trip_worker,
                    trip_name,
                    trip_data,
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Trip"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Trip")
                if pdf_path:
                    ran_any = True
                log(f"TRIP {'complete' if pdf_path else 'failed'}.")

        except Exception as e:
            st.session_state.outputs[rt] = {"error": str(e)}
            errors.append(f"{rt}: {e}")
            log(f"{rt.upper()} ERROR: {e}")
            log(f"[{rt}] ATTACH: skipped due to worker error.")

    if not ran_any:
        log("ERROR: Nothing ran.")
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Nothing ran",
            "detail": "No reports executed successfully.",
        }
        return

    if not attachments:
        log("ERROR: No valid PDF attachments were created, so email was not sent.")
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "❌ No PDFs created",
            "detail": "No valid report PDFs were generated, so the email was not sent.",
        }
        return

    log("Sending email…")
    log(f"ATTACHMENTS: {len(attachments)} PDF(s) will be sent.")
    if attachments:
        for a in attachments:
            log(f" - {Path(a).name}")

    subject = f"Sentinel Access — {', '.join(selected_in_order)} — {main_location}"
    body_lines = [
        f"Hello {user.get('name') or ''}",
        "",
        "Attached are your Sentinel Access report(s):",
        f"- Reports: {', '.join(selected_in_order)}",
        f"- Location: {main_location}",
    ]
    if "Trip" in selected_in_order and trip_cfg:
        body_lines.append(f"- Trip: {trip_cfg.get('start')} → {trip_cfg.get('stop1')} → {trip_cfg.get('stop2')}")
    body_lines += ["", "Sentinel Access"]
    body = "\n".join(body_lines)

    ok, msg = send_email_via_sender(
        to_email=user.get("email") or "",
        username=user.get("name") or "",
        subject=subject,
        body=body,
        attachments=attachments,
    )
    log(f"{'EMAIL OK' if ok else 'EMAIL ERROR'}: {msg}")

    st.session_state.is_running = False
    if ok:
        detail = f"Email sent to {user.get('email') or '(no email)'} with {len(attachments)} PDF(s) attached."
        if errors:
            detail += " (Some reports had errors—see System progress.)"
        st.session_state.final_banner = {
            "type": "success",
            "title": "✅ ALL COMPLETE — Email sent",
            "detail": detail,
        }
        try:
            st.toast("✅ All complete — email sent", icon="✅")
        except Exception:
            pass
    else:
        detail = f"Email failed: {msg}"
        if errors:
            detail += " (Some reports also had errors—see System progress.)"
        st.session_state.final_banner = {
            "type": "error",
            "title": "❌ Completed, but email failed",
            "detail": detail,
        }
        try:
            st.toast("❌ Completed, but email failed", icon="❌")
        except Exception:
            pass

    log("All done ✅")
    st.session_state.confirmed_ok = False
    st.session_state.confirmed_payload = None


# ============================================================
# 3 PANELS
# ============================================================
left, middle, right = st.columns([0.30, 0.44, 0.26], gap="large")

# LEFT
with left:
    with st.container():
        st.subheader("Instructions")
        st.markdown(
            """
            1) Enter Name + Email  
            2) Select report(s) + location(s)  
            3) Add a new location (standalone) if needed  
            4) Confirm selections  
            5) Generate & Send (emails all selected report PDFs)  
            """
        )
        st.divider()
        st.subheader("User details")
        st.text_input("Name", key="user_name", disabled=st.session_state.is_running)
        st.text_input("Email", key="user_email", disabled=st.session_state.is_running)
        st.button(
            "Reset / Refresh page",
            use_container_width=True,
            on_click=reset_app_state,
            disabled=st.session_state.is_running,
        )

# MIDDLE
with middle:
    with st.container():
        st.subheader("Report setup")

        banner = st.session_state.get("final_banner")
        if banner:
            btype = banner.get("type", "info")
            title = banner.get("title", "")
            detail = banner.get("detail", "")
            if btype == "success":
                st.success(f"{title}\n\n{detail}")
            elif btype == "error":
                st.error(f"{title}\n\n{detail}")
            else:
                st.info(f"{title}\n\n{detail}")
        else:
            if st.session_state.is_running:
                st.info("Running… generating reports and emailing PDFs. (The screen dimming is normal while Streamlit runs.)")

        st.multiselect(
            "Report type(s)",
            ["Surf", "Sky", "Weather", "Trip"],
            default=["Weather"],
            key="report_types",
            disabled=st.session_state.is_running,
        )
        st.selectbox(
            "Location",
            st.session_state.location_names,
            key="main_location",
            disabled=st.session_state.is_running,
        )

        with st.expander("➕ Add a new location (standalone)", expanded=False):
            st.text_input("New location name", key="new_loc_name", disabled=st.session_state.is_running)
            st.selectbox(
                "State",
                ["VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT"],
                key="new_state",
                disabled=st.session_state.is_running,
            )

            cols = st.columns([1, 1], gap="small")
            with cols[0]:
                if st.button("Find matches", use_container_width=True, disabled=st.session_state.is_running):
                    st.session_state.new_location_candidates = []
                    name = (st.session_state.get("new_loc_name") or "").strip()
                    state = st.session_state.get("new_state") or "VIC"
                    if not name:
                        log("ERROR: Enter a new location name first.")
                    else:
                        try:
                            matches = geocode_au(name, state)
                            st.session_state.new_location_candidates = matches
                            if matches:
                                log(f"Found {len(matches)} match(es) for '{name}' ({state}). Select the best match.")
                            else:
                                log(f"No AU matches found for '{name}'. Try a different name.")
                        except Exception as e:
                            log(f"Geocoding error: {e}")

            candidates = st.session_state.get("new_location_candidates") or []
            if candidates:
                labels = [c["label"] for c in candidates]
                st.selectbox("Select best match", labels, key="chosen_geo_label", disabled=st.session_state.is_running)

            with cols[1]:
                st.button(
                    "✅ Save new location",
                    type="primary",
                    use_container_width=True,
                    on_click=add_location_action,
                    disabled=st.session_state.is_running,
                )

        if "Trip" in (st.session_state.get("report_types") or []):
            st.divider()
            st.markdown("**Trip setup**")
            st.selectbox("Start location", st.session_state.location_names, key="trip_start", disabled=st.session_state.is_running)
            st.selectbox("Next location", st.session_state.location_names, key="trip_stop1", disabled=st.session_state.is_running)
            st.selectbox("Next location (2)", st.session_state.location_names, key="trip_stop2", disabled=st.session_state.is_running)

            st.selectbox("Fuel type", ["Petrol", "Diesel"], key="fuel_type", disabled=st.session_state.is_running)
            st.number_input(
                "Fuel consumption (L/100km)",
                min_value=1.0,
                value=9.5,
                step=0.1,
                key="fuel_l_per_100km",
                disabled=st.session_state.is_running,
            )
            default_price = 2.10 if (st.session_state.get("fuel_type") or "Petrol") == "Petrol" else 2.20
            st.number_input(
                "Fuel price ($/L)",
                min_value=0.0,
                value=float(default_price),
                step=0.01,
                key="fuel_price",
                disabled=st.session_state.is_running,
            )

        st.divider()
        st.button(
            "✅ Confirm selections",
            type="primary",
            use_container_width=True,
            on_click=confirm_action,
            disabled=st.session_state.is_running,
        )
        render_progress_box(height=320)
        st.button(
            "📨 Generate & Send",
            type="primary",
            use_container_width=True,
            on_click=generate_pay_action,
            disabled=st.session_state.is_running,
        )

# RIGHT
with right:
    with st.container():
        st.subheader("Examples")
        tab_surf, tab_sky, tab_weather, tab_trip = st.tabs(["Surf", "Sky", "Weather", "Trip"])

        with tab_surf:
            if st.toggle("View Surf example", key="ex_surf"):
                st.markdown("**Surf example**")
                st.caption("Today panel + next best day + 7-day trend with surf windows.")

        with tab_sky:
            if st.toggle("View Sky example", key="ex_sky"):
                st.markdown("**Sky example**")
                st.caption("Depends on your sky_worker output structure.")

        with tab_weather:
            if st.toggle("View Weather example", key="ex_weather"):
                st.markdown("**Weather example**")
                st.caption("Depends on your weather_worker output structure.")

        with tab_trip:
            if st.toggle("View Trip example", key="ex_trip"):
                st.markdown("**Trip example**")
                demo = pd.DataFrame(
                    [
                        {"Leg": "1. Start → Next", "Distance (km)": 120.0, "Fuel (L)": 11.40, "Fuel cost ($)": 23.94},
                        {"Leg": "2. Next → Next 2", "Distance (km)": 65.0, "Fuel (L)": 6.18, "Fuel cost ($)": 12.98},
                    ]
                )
                st.dataframe(demo, use_container_width=True, hide_index=True)

        outputs = st.session_state.get("outputs") or {}
        if outputs:
            st.divider()
            st.caption("Latest outputs")
            for k, v in outputs.items():
                with st.expander(k, expanded=False):
                    st.write(v)
 matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ============================================================
# 1. USER CONFIG — EDIT THESE FOR ANY AUSTRALIAN SURF SITE
# ============================================================
LOCATION_NAME = "Bells Beach"
LAT = -38.371
LON = 144.281
REPORT_TZ = ZoneInfo("Australia/Melbourne")

# Beach / break tuning
# Direction the beach faces toward the ocean, in degrees:
# N=0, E=90, S=180, W=270
BEACH_ORIENTATION_DEG = 210

# Preferred swell direction window (degrees)
PREFERRED_SWELL_DIR_MIN = 170
PREFERRED_SWELL_DIR_MAX = 235

# Preferred swell size window (metres)
PREFERRED_SWELL_MIN_M = 0.8
PREFERRED_SWELL_MAX_M = 2.8

# Preferred tide window (optional). Leave as None to disable tide scoring.
PREFERRED_TIDE_MIN_M = None
PREFERRED_TIDE_MAX_M = None

# Optional synthetic tide fallback.
USE_ESTIMATED_TIDE_IF_MISSING = False

FORECAST_DAYS = 7
REQUEST_TIMEOUT = 20

SAFE_NAME = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in LOCATION_NAME.replace(" ", "_"))
FILENAME = f"{SAFE_NAME}_Surf_Forecast.pdf"

LOCAL_DIR = (
    r"C:\RuralAI\OUTPUT\SURF"
    if platform.system() == "Windows"
    else os.path.join(os.path.expanduser("~"), "Documents", "Surf Reports")
)
os.makedirs(LOCAL_DIR, exist_ok=True)


# ============================================================
# 2. SMALL HELPERS
# ============================================================
def now_local() -> datetime:
    return datetime.now(REPORT_TZ)


def parse_local_times(series: pd.Series) -> pd.Series:
    # Open-Meteo returns local wall-clock strings when timezone is specified.
    # We explicitly localize them to Australia/Melbourne so cloud/server timezone
    # can never affect the "now" line or date slicing.
    dt = pd.to_datetime(series)
    if getattr(dt.dt, "tz", None) is None:
        return dt.dt.tz_localize(REPORT_TZ)
    return dt.dt.tz_convert(REPORT_TZ)


def deg_to_text(deg: float | int | None) -> str:
    if deg is None or pd.isna(deg):
        return ""
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
    ]
    return dirs[int((float(deg) + 11.25) // 22.5) % 16]


def angular_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def in_direction_window(value: float, low: float, high: float) -> bool:
    value = value % 360
    low = low % 360
    high = high % 360
    if low <= high:
        return low <= value <= high
    return value >= low or value <= high


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def circular_mean_deg(values: list[float]) -> float | None:
    clean = [float(v) for v in values if v is not None and not pd.isna(v)]
    if not clean:
        return None
    radians = np.deg2rad(clean)
    sin_sum = np.sin(radians).mean()
    cos_sum = np.cos(radians).mean()
    angle = math.degrees(math.atan2(sin_sum, cos_sum)) % 360
    return angle


def safe_float_text(value, fmt: str = ".1f", suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{value:{fmt}}{suffix}"


def score_out_of_10(score_100: float | int | None) -> str:
    if score_100 is None or pd.isna(score_100):
        return "n/a"
    value = float(score_100) / 10.0
    return f"{round(value):.0f}/10"


# ============================================================
# 3. FETCHERS
# ============================================================
def fetch_json(url: str) -> dict:
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_open_meteo_marine(lat: float, lon: float) -> pd.DataFrame:
    url = (
        "https://marine-api.open-meteo.com/v1/marine"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=swell_wave_height,swell_wave_direction,wave_period"
        f"&forecast_days={FORECAST_DAYS}"
        "&timezone=Australia/Melbourne"
    )
    data = fetch_json(url)
    hourly = data.get("hourly", {})
    df = pd.DataFrame(hourly)
    if df.empty or "time" not in df.columns:
        raise ValueError("Marine API returned no hourly data.")
    df["time"] = parse_local_times(df["time"])
    return df


def fetch_open_meteo_weather(lat: float, lon: float) -> pd.DataFrame:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&hourly=wind_speed_10m,wind_direction_10m"
        f"&forecast_days={FORECAST_DAYS}"
        f"&timezone=Australia/Melbourne"
    )
    data = fetch_json(url)
    hourly = data.get("hourly", {})
    df = pd.DataFrame(hourly)
    if df.empty or "time" not in df.columns:
        raise ValueError("Forecast API returned no hourly data.")
    df["time"] = parse_local_times(df["time"])
    return df.rename(columns={
        "wind_speed_10m": "wind_speed_10m_main",
        "wind_direction_10m": "wind_direction_10m_main",
    })


def fetch_bom_access_g_weather(lat: float, lon: float) -> pd.DataFrame | None:
    try:
        url = (
            "https://api.open-meteo.com/v1/bom"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=wind_speed_10m,wind_direction_10m"
            f"&forecast_days={FORECAST_DAYS}"
            f"&timezone=Australia/Melbourne"
        )
        data = fetch_json(url)
        hourly = data.get("hourly", {})
        df = pd.DataFrame(hourly)
        if df.empty or "time" not in df.columns:
            return None
        df["time"] = parse_local_times(df["time"])
        return df.rename(columns={
            "wind_speed_10m": "wind_speed_10m_bom",
            "wind_direction_10m": "wind_direction_10m_bom",
        })
    except Exception:
        return None


def add_optional_tide(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    tide_source = "No tide source configured"
    if USE_ESTIMATED_TIDE_IF_MISSING:
        hours = np.arange(len(df))
        df["tide_height"] = 1.35 + 0.85 * np.sin(hours * (2 * np.pi / 12.4))
        tide_source = "Estimated tide model (low confidence)"
    else:
        df["tide_height"] = np.nan
    return df, tide_source


# ============================================================
# 4. DATA PREP / CONSENSUS
# ============================================================
def build_dataset(lat: float, lon: float) -> tuple[pd.DataFrame, dict]:
    marine = fetch_open_meteo_marine(lat, lon)
    wx_main = fetch_open_meteo_weather(lat, lon)
    wx_bom = fetch_bom_access_g_weather(lat, lon)

    df = marine.merge(wx_main, on="time", how="inner")

    diagnostics = {
        "marine_source": "Open-Meteo Marine",
        "wind_source_main": "Open-Meteo Forecast",
        "wind_source_secondary": "Open-Meteo BOM ACCESS-G" if wx_bom is not None else "Unavailable",
        "tide_source": "",
        "timezone": "Australia/Melbourne",
    }

    if wx_bom is not None:
        df = df.merge(wx_bom, on="time", how="left")
    else:
        df["wind_speed_10m_bom"] = np.nan
        df["wind_direction_10m_bom"] = np.nan

    df["wind_speed_10m"] = df[["wind_speed_10m_main", "wind_speed_10m_bom"]].mean(axis=1, skipna=True)

    wind_dirs = []
    for _, row in df.iterrows():
        wind_dirs.append(circular_mean_deg([
            row.get("wind_direction_10m_main"),
            row.get("wind_direction_10m_bom"),
        ]))
    df["wind_direction_10m"] = wind_dirs

    def wind_agreement(row: pd.Series) -> float:
        a = row.get("wind_direction_10m_main")
        b = row.get("wind_direction_10m_bom")
        if pd.isna(a) or pd.isna(b):
            return 0.65
        diff = angular_diff(float(a), float(b))
        if diff <= 20:
            return 1.0
        if diff <= 45:
            return 0.8
        if diff <= 70:
            return 0.55
        return 0.3

    df["wind_agreement"] = df.apply(wind_agreement, axis=1)

    df, tide_source = add_optional_tide(df)
    diagnostics["tide_source"] = tide_source

    return df, diagnostics


# ============================================================
# 5. GENERIC SURF SCORING FOR A SINGLE POINT
# ============================================================
def score_row(row: pd.Series) -> pd.Series:
    reasons: list[str] = []

    swell_h = row.get("swell_wave_height", np.nan)
    swell_dir = row.get("swell_wave_direction", np.nan)
    wave_period = row.get("wave_period", np.nan)
    wind_kmh = row.get("wind_speed_10m", np.nan)
    wind_dir = row.get("wind_direction_10m", np.nan)
    tide_h = row.get("tide_height", np.nan)

    score = 0.0

    # Swell size score (0..30)
    swell_score = 0.0
    if not pd.isna(swell_h):
        if PREFERRED_SWELL_MIN_M <= swell_h <= PREFERRED_SWELL_MAX_M:
            swell_score = 30.0
            reasons.append(f"swell size in range ({swell_h:.1f}m)")
        elif swell_h < PREFERRED_SWELL_MIN_M:
            gap = PREFERRED_SWELL_MIN_M - swell_h
            swell_score = max(0.0, 30.0 - gap * 20.0)
            reasons.append(f"swell a bit small ({swell_h:.1f}m)")
        else:
            gap = swell_h - PREFERRED_SWELL_MAX_M
            swell_score = max(0.0, 30.0 - gap * 10.0)
            reasons.append(f"swell a bit oversized ({swell_h:.1f}m)")
    score += swell_score

    # Swell direction score (0..20)
    swell_dir_score = 0.0
    if not pd.isna(swell_dir):
        if in_direction_window(float(swell_dir), PREFERRED_SWELL_DIR_MIN, PREFERRED_SWELL_DIR_MAX):
            swell_dir_score = 20.0
            reasons.append(f"swell suits break ({deg_to_text(swell_dir)})")
        else:
            diffs = [
                angular_diff(float(swell_dir), PREFERRED_SWELL_DIR_MIN),
                angular_diff(float(swell_dir), PREFERRED_SWELL_DIR_MAX),
            ]
            swell_dir_score = max(0.0, 20.0 - min(diffs) * 0.35)
            reasons.append(f"swell less ideal ({deg_to_text(swell_dir)})")
    score += swell_dir_score

    # Wave period score (0..10)
    period_score = 0.0
    if not pd.isna(wave_period):
        if wave_period >= 14:
            period_score = 10.0
            reasons.append(f"long period ({wave_period:.0f}s)")
        elif wave_period >= 10:
            period_score = 7.5
            reasons.append(f"decent period ({wave_period:.0f}s)")
        elif wave_period >= 8:
            period_score = 5.0
        else:
            period_score = 2.0
    score += period_score

    # Wind score (0..30)
    offshore_from_deg = (BEACH_ORIENTATION_DEG + 180) % 360
    wind_score = 0.0
    if not pd.isna(wind_kmh) and not pd.isna(wind_dir):
        alignment = angular_diff(float(wind_dir), offshore_from_deg)

        if alignment <= 30:
            dir_component = 20.0
            reasons.append(f"offshore wind ({deg_to_text(wind_dir)})")
        elif alignment <= 60:
            dir_component = 14.0
            reasons.append(f"cross-offshore wind ({deg_to_text(wind_dir)})")
        elif alignment <= 100:
            dir_component = 7.0
            reasons.append(f"cross-shore wind ({deg_to_text(wind_dir)})")
        else:
            dir_component = 0.0
            reasons.append(f"onshore wind ({deg_to_text(wind_dir)})")

        if wind_kmh <= 12:
            speed_component = 10.0
            reasons.append(f"light wind ({wind_kmh:.0f} km/h)")
        elif wind_kmh <= 20:
            speed_component = 7.0
        elif wind_kmh <= 28:
            speed_component = 4.0
        else:
            speed_component = 1.0
            reasons.append(f"windy ({wind_kmh:.0f} km/h)")

        wind_score = dir_component + speed_component

    score += wind_score

    # Tide score (0..10)
    tide_score = 0.0
    if (
        PREFERRED_TIDE_MIN_M is not None
        and PREFERRED_TIDE_MAX_M is not None
        and not pd.isna(tide_h)
    ):
        if PREFERRED_TIDE_MIN_M <= tide_h <= PREFERRED_TIDE_MAX_M:
            tide_score = 10.0
            reasons.append(f"tide in range ({tide_h:.1f}m)")
        else:
            if tide_h < PREFERRED_TIDE_MIN_M:
                tide_score = max(0.0, 10.0 - (PREFERRED_TIDE_MIN_M - tide_h) * 6.0)
            else:
                tide_score = max(0.0, 10.0 - (tide_h - PREFERRED_TIDE_MAX_M) * 4.0)
            reasons.append(f"tide less ideal ({tide_h:.1f}m)")
    score += tide_score

    # Morning bias (0..5)
    hour = row["time"].hour
    morning_bonus = 5.0 if 5 <= hour <= 9 else (2.0 if 10 <= hour <= 12 else 0.0)
    if morning_bonus > 0:
        reasons.append("better time-of-day bias")
    score += morning_bonus

    confidence = 0.85
    if pd.isna(swell_h) or pd.isna(swell_dir) or pd.isna(wind_kmh) or pd.isna(wind_dir):
        confidence -= 0.25
    confidence *= float(row.get("wind_agreement", 0.65))
    if USE_ESTIMATED_TIDE_IF_MISSING and not pd.isna(tide_h):
        confidence -= 0.10
    confidence = clamp(confidence, 0.15, 0.98)

    if score >= 75:
        rating = "Good"
    elif score >= 55:
        rating = "Fair"
    elif score >= 38:
        rating = "Marginal"
    else:
        rating = "Poor"

    return pd.Series({
        "surf_score": round(score, 1),
        "surf_rating": rating,
        "confidence": round(confidence, 2),
        "summary_reasons": ", ".join(reasons[:5]),
    })


def find_best_windows(df: pd.DataFrame) -> pd.DataFrame:
    scored = df.copy()
    scored[["surf_score", "surf_rating", "confidence", "summary_reasons"]] = scored.apply(score_row, axis=1)
    return scored


# ============================================================
# 6. DAY SELECTION
# ============================================================
def get_today_df(df: pd.DataFrame) -> pd.DataFrame:
    now = now_local()
    today_df = df[df["time"].dt.date == now.date()].copy()
    if today_df.empty:
        today_df = df.head(24).copy()
    return today_df


def get_next_best_day_df(df: pd.DataFrame) -> pd.DataFrame:
    today = now_local().date()
    daily_best = (
        df.groupby(df["time"].dt.date)
        .apply(lambda g: g["surf_score"].max())
        .reset_index(name="day_best_score")
        .rename(columns={"time": "date"})
    )
    future_days = daily_best[daily_best["time"] != today].copy() if "time" in daily_best.columns else daily_best[daily_best["date"] != today].copy()
    if future_days.empty:
        dates = sorted(df["time"].dt.date.unique())
        fallback_date = dates[1] if len(dates) > 1 else dates[0]
        return df[df["time"].dt.date == fallback_date].copy()

    date_col = "date" if "date" in future_days.columns else "time"
    next_best_date = future_days.sort_values("day_best_score", ascending=False).iloc[0][date_col]
    return df[df["time"].dt.date == next_best_date].copy()


# ============================================================
# 7. CHART HELPERS
# ============================================================
def annotate_direction_points(ax, day_df: pd.DataFrame, y_max: float, include_current_line: bool = False) -> None:
    if day_df.empty:
        return

    label_rows = day_df.iloc[::4].copy()
    if len(label_rows) == 0:
        label_rows = day_df.copy()

    for _, row in label_rows.iterrows():
        swell_txt = deg_to_text(row.get("swell_wave_direction"))
        wind_txt = deg_to_text(row.get("wind_direction_10m"))
        label = f"S:{swell_txt}  W:{wind_txt}"
        y = row["swell_wave_height"] + max(0.08, y_max * 0.03)
        ax.text(
            row["time"],
            y,
            label,
            ha="center",
            va="bottom",
            fontsize=6.5,
            color="black",
            bbox=dict(facecolor="white", alpha=0.65, edgecolor="none", pad=0.15),
            zorder=9,
        )

    if include_current_line:
        now = now_local()
        ax.axvline(now, color="red", lw=1.7, label="Current Time")


def base_day_chart(day_df: pd.DataFrame, title: str, include_current_line: bool) -> BytesIO:
    fig, ax1 = plt.subplots(figsize=(10.8, 2.5))
    ax2 = ax1.twinx()

    ax1.plot(day_df["time"], day_df["swell_wave_height"], lw=2.2, color="#1f77b4", label="Swell (m)")
    ax2.plot(day_df["time"], day_df["wind_speed_10m"], lw=1.2, ls="--", color="#2ca02c", alpha=0.75, label="Wind (km/h)")

    y_max = max(1.0, float(day_df["swell_wave_height"].max()) * 1.35 if not day_df["swell_wave_height"].isna().all() else 1.0)
    ax1.set_ylim(0, y_max)

    top = day_df.nlargest(min(3, len(day_df)), "surf_score").sort_values("time")
    for _, row in top.iterrows():
        ax1.scatter(row["time"], row["swell_wave_height"], marker="o", s=34, zorder=10, color="darkblue")
        ax1.annotate(
            f"{row['time'].strftime('%H:%M')}  {row['surf_rating']} {row['surf_score']:.0f}",
            (row["time"], row["swell_wave_height"]),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=6.7,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.85),
        )

    annotate_direction_points(ax1, day_df, y_max, include_current_line=include_current_line)

    ax1.set_title(title, fontweight="bold", fontsize=10.5, pad=6)
    ax1.set_ylabel("Swell", fontsize=7)
    ax2.set_ylabel("Wind", fontsize=7)
    ax1.tick_params(axis="both", labelsize=7)
    ax2.tick_params(axis="y", labelsize=7)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=REPORT_TZ))

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", fontsize=6.7, framealpha=0.9)

    plt.tight_layout(pad=0.8)
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=145, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


def generate_daily_chart(df: pd.DataFrame, location_name: str) -> BytesIO:
    day_df = get_today_df(df)
    return base_day_chart(day_df, f"{location_name} — Today", include_current_line=True)


def generate_next_best_day_chart(df: pd.DataFrame, location_name: str) -> BytesIO:
    day_df = get_next_best_day_df(df)
    day_title = day_df["time"].iloc[0].strftime("%a %d %b")
    return base_day_chart(day_df, f"{location_name} — Next Best Day ({day_title})", include_current_line=False)


def generate_weekly_chart(df: pd.DataFrame, location_name: str) -> BytesIO:
    fig, ax1 = plt.subplots(figsize=(10.8, 2.7))
    ax2 = ax1.twinx()

    ax1.plot(df["time"], df["swell_wave_height"], lw=2.0, color="#1f77b4", label="Swell (m)")
    ax2.plot(df["time"], df["wind_speed_10m"], lw=1.1, ls="--", color="#2ca02c", alpha=0.7, label="Wind (km/h)")

    y_max = max(1.0, float(df["swell_wave_height"].max()) * 1.30 if not df["swell_wave_height"].isna().all() else 1.0)
    ax1.set_ylim(0, y_max)

    for day, group in df.groupby(df["time"].dt.date):
        best = group.loc[group["surf_score"].idxmax()]
        ax1.scatter(best["time"], best["swell_wave_height"], marker="x", s=42, zorder=8, color="darkred")
        ax1.annotate(
            f"{best['time'].strftime('%a %H:%M')}\n{best['surf_rating']} {best['surf_score']:.0f}\nS:{deg_to_text(best['swell_wave_direction'])} W:{deg_to_text(best['wind_direction_10m'])}",
            (best["time"], best["swell_wave_height"]),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=6.4,
            bbox=dict(boxstyle="round,pad=0.16", facecolor="white", alpha=0.82),
        )

    ax1.set_title(f"{location_name} — Weekly Outlook", fontweight="bold", fontsize=10.5, pad=6)
    ax1.set_ylabel("Swell", fontsize=7)
    ax2.set_ylabel("Wind", fontsize=7)
    ax1.tick_params(axis="both", labelsize=7)
    ax2.tick_params(axis="y", labelsize=7)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%a %d", tz=REPORT_TZ))

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", fontsize=6.7, framealpha=0.9)

    plt.tight_layout(pad=0.8)
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=145, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


# ============================================================
# 8. PDF
# ============================================================
def build_pdf(df: pd.DataFrame, diagnostics: dict) -> str:
    ppath = os.path.join(LOCAL_DIR, FILENAME)
    doc = SimpleDocTemplate(
        ppath,
        pagesize=A4,
        leftMargin=0.65 * cm,
        rightMargin=0.65 * cm,
        topMargin=0.45 * cm,
        bottomMargin=0.45 * cm,
    )

    styles = getSampleStyleSheet()
    compact = ParagraphStyle(
        "compact",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.4,
        leading=8.4,
        spaceAfter=0,
    )
    compact_bold = ParagraphStyle(
        "compact_bold",
        parent=compact,
        fontName="Helvetica-Bold",
    )

    now = now_local()
    today_df = get_today_df(df)
    next_best_df = get_next_best_day_df(df)

    best_today = today_df.loc[today_df["surf_score"].idxmax()]
    today_sorted = today_df.sort_values("surf_score", ascending=False).reset_index(drop=True)
    backup_today = today_sorted.iloc[1] if len(today_sorted) > 1 else best_today

    next_best = next_best_df.loc[next_best_df["surf_score"].idxmax()]

    why_para = Paragraph(best_today["summary_reasons"], compact)

    daily_rows = [
        [Paragraph("Location", compact_bold), Paragraph(LOCATION_NAME, compact)],
        [Paragraph("Best window today", compact_bold),
         Paragraph(f"{best_today['time'].strftime('%H:%M')} — {best_today['surf_rating']} ({best_today['surf_score']:.0f}/100)", compact)],
        [Paragraph("Backup window", compact_bold),
         Paragraph(f"{backup_today['time'].strftime('%H:%M')} — {backup_today['surf_rating']} ({backup_today['surf_score']:.0f}/100)", compact)],
        [Paragraph("Next best day", compact_bold),
         Paragraph(f"{next_best['time'].strftime('%a %d %b %H:%M')} — {next_best['surf_rating']} ({next_best['surf_score']:.0f}/100)", compact)],
        [Paragraph("Wind", compact_bold),
         Paragraph(f"{safe_float_text(best_today['wind_speed_10m'], '.0f', ' km/h')} {deg_to_text(best_today['wind_direction_10m'])}", compact)],
        [Paragraph("Swell", compact_bold),
         Paragraph(f"{safe_float_text(best_today['swell_wave_height'], '.1f', ' m')} {deg_to_text(best_today['swell_wave_direction'])}", compact)],
        [Paragraph("Wave period", compact_bold),
         Paragraph(f"{safe_float_text(best_today['wave_period'], '.0f', ' s')}", compact)],
        [Paragraph("Confidence", compact_bold),
         Paragraph(f"{int(best_today['confidence'] * 100)}%", compact)],
        [Paragraph("Why", compact_bold), why_para],
    ]

    t1 = Table(daily_rows, colWidths=[3.9 * cm, 14.7 * cm])
    t1.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.black),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("BACKGROUND", (1, 0), (1, -1), colors.whitesmoke),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.45, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.22, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))

    story = [
        Paragraph(f"<b>{LOCATION_NAME.upper()} SURF REPORT</b>", styles["Title"]),
        Paragraph(
            f"<font size=7.2>Generated {now.strftime('%Y-%m-%d %H:%M %Z')} | "
            f"Today chart keeps the live time marker. "
            f"Direction labels: S = swell direction, W = wind direction. "
            f"Timezone: {diagnostics.get('timezone', 'Australia/Melbourne')}</font>",
            styles["Normal"],
        ),
        Spacer(1, 0.10 * cm),
        t1,
        Spacer(1, 0.12 * cm),
        Image(generate_daily_chart(df, LOCATION_NAME), 18.6 * cm, 4.15 * cm),
        Spacer(1, 0.06 * cm),
        Image(generate_next_best_day_chart(df, LOCATION_NAME), 18.6 * cm, 4.15 * cm),
        Spacer(1, 0.06 * cm),
        Image(generate_weekly_chart(df, LOCATION_NAME), 18.6 * cm, 4.35 * cm),
        Spacer(1, 0.04 * cm),
        Paragraph(
            "<font size=6.8><b>Guide:</b> Good ≥ 75 | Fair 55–74 | Marginal 38–54 | Poor &lt; 38</font>",
            styles["Normal"],
        ),
    ]

    doc.build(story)
    return ppath


# ============================================================
# 9. MAIN
# ============================================================
def main() -> None:
    try:
        df, diagnostics = build_dataset(LAT, LON)
        df = find_best_windows(df)
        output_path = build_pdf(df, diagnostics)

        best = df.loc[df["surf_score"].idxmax()]
        print("SUCCESS")
        print(f"Location: {LOCATION_NAME}")
        print(f"Best forecast window: {best['time'].strftime('%Y-%m-%d %H:%M %Z')}")
        print(f"Rating: {best['surf_rating']} ({best['surf_score']:.0f}/100)")
        print(f"Confidence: {int(best['confidence'] * 100)}%")
        print(f"PDF saved to: {output_path}")

    except requests.HTTPError as e:
        print(f"HTTP ERROR: {e}")
    except requests.RequestException as e:
        print(f"NETWORK ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")


if __name__ == "__main__":
    main()
