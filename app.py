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
# PAGE CONFIG FIRST
# ============================================================
st.set_page_config(page_title="Sentinel Access", layout="wide")

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

st.title("Sentinel Access")

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

                surf_payload = {
                    "location_key": main_location,
                    "display_name": loc_payload.get("display_name", main_location),
                    "latitude": lat,
                    "longitude": lon,
                    "state": loc_payload.get("state"),
                }

                pdf_path = call_worker_generate_report(
                    surf_generate_report,
                    main_location,
                    surf_payload,
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
