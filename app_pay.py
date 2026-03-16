#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st

# ============================================================
# PAGE CONFIG MUST BE FIRST STREAMLIT COMMAND
# ============================================================
st.set_page_config(page_title="Oz Trip Planner", layout="wide")
...
col_title, col_link = st.columns([0.72, 0.28])
with col_title:
    st.title("Oz Trip Planner")
with col_link:
    st.markdown(
        """
        <div style="text-align:right; padding-top: 1.1rem;">
          <a href="https://www.oztripplanner.net" target="_blank"
             style="
                display:inline-block;
                text-decoration:none;
                padding:0.6rem 0.9rem;
                border-radius:10px;
                border:1px solid #1f8f3a;
                color:#1f8f3a;
                font-weight:700;
             ">
             Return to webpage
          </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ============================================================
# OPTIONAL IMPORTS
# ============================================================
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None  # type: ignore

STRIPE_IMPORT_ERROR = None
try:
    import stripe
    print(f"STRIPE IMPORT OK: version={getattr(stripe, '__version__', 'unknown')}")
except Exception as e:
    stripe = None  # type: ignore
    STRIPE_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print(f"STRIPE IMPORT FAILED: {STRIPE_IMPORT_ERROR}")

# ============================================================
# ENV / STRIPE CONFIG
# ============================================================
if load_dotenv is not None:
    try:
        load_dotenv()
    except Exception:
        pass

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "").strip()
CURRENCY = os.getenv("CURRENCY", "aud").strip().lower() or "aud"

PRICE_PER_REPORT_CENTS = int(os.getenv("PRICE_PER_REPORT_CENTS", "250"))
BUNDLE_PRICE_CENTS = int(os.getenv("BUNDLE_PRICE_CENTS", "800"))

# ============================================================
# IMPORTS WITH VISIBLE ERROR CAPTURE
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
      .block-container {
        padding-top: 0.8rem;
        padding-bottom: 1rem;
        max-width: 1500px;
      }

      h1 { margin: 0.1rem 0 0.5rem 0 !important; }

      .sa-step-box {
        border: 1px solid #d9d9d9;
        border-radius: 12px;
        padding: 0.8rem 0.9rem;
        margin-bottom: 0.7rem;
        background: #fafafa;
      }

      .sa-step-current {
        border: 2px solid #1f8f3a;
        background: #f3fbf5;
      }

      .sa-step-done {
        border: 1px solid #b7dfc2;
        background: #f5fcf7;
      }

      .sa-pay-box {
        border: 2px solid #f0b429;
        background: #fff8e6;
        border-radius: 14px;
        padding: 1rem;
        margin: 0.6rem 0 0.7rem 0;
      }

      .sa-next-box {
        border-left: 5px solid #1f8f3a;
        background: #f6fbf7;
        padding: 0.8rem 0.9rem;
        border-radius: 8px;
        margin-bottom: 0.8rem;
      }

      .sa-user-box {
        border: 2px solid #cfe8d6;
        background: #f7fcf8;
        border-radius: 12px;
        padding: 0.85rem;
        margin-bottom: 0.9rem;
      }

      .sa-email-note {
        border-left: 5px solid #f59e0b;
        background: #fff8e6;
        padding: 0.7rem 0.8rem;
        border-radius: 8px;
        margin-top: 0.5rem;
      }

      button[data-testid="stBaseButton-primary"] {
        background-color: #1f8f3a !important;
        border-color: #1f8f3a !important;
        color: white !important;
        font-weight: 700 !important;
      }

      button[data-testid="stBaseButton-primary"]:hover {
        background-color: #17702d !important;
        border-color: #17702d !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Surf, Weather, Photography, Trip Planner")

if IMPORT_ERRORS:
    st.error("One or more modules failed to import.")
    for err in IMPORT_ERRORS:
        st.caption(err)

# ============================================================
# SESSION STATE DEFAULTS
# ============================================================
defaults = {
    "progress_log": [],
    "confirmed_ok": False,
    "confirmed_payload": None,
    "outputs": {},
    "new_location_candidates": [],
    "chosen_geo_label": None,
    "location_names": [],
    "is_running": False,
    "final_banner": None,
    "payment_url": None,
    "payment_session_id": None,
    "payment_verified": False,
    "post_payment_done": False,
    "fulfillment_started": False,
    "pending_paid_session_id": None,
    "last_fulfilled_session_id": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# LOGGING / UI HELPERS
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
    # Clear all Streamlit session state, including user inputs, logs, banners, payment state, outputs
    for k in list(st.session_state.keys()):
        del st.session_state[k]

    # Clear URL query params so paid/cancelled/session_id do not rebuild the page state
    try:
        if hasattr(st, "query_params"):
            st.query_params.clear()
        else:
            st.experimental_set_query_params()
    except Exception:
        pass

    st.rerun()


def current_step_text() -> str:
    if st.session_state.get("post_payment_done"):
        return "Finished — reports generated and email step completed."
    if st.session_state.get("pending_paid_session_id"):
        return "Payment confirmed — Sentinel is generating reports and sending the email."
    if st.session_state.get("is_running"):
        return "Processing — please stay on this page while Sentinel finishes the next step."
    if st.session_state.get("payment_url"):
        return "Next step: click Pay now to open Stripe and complete payment."
    if st.session_state.get("confirmed_ok"):
        return "Next step: click Create payment link."
    return "Next step: enter details, choose reports, then click Confirm details."


def render_pay_button(url: str) -> None:
    st.markdown(
        """
        <div class="sa-pay-box">
          <div style="font-weight:800; font-size:1.05rem; margin-bottom:0.45rem;">
            Payment link ready
          </div>
          <div style="margin-bottom:0.8rem;">
            Click the button below to securely pay in Stripe, then return here automatically.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.link_button("💳 PAY NOW IN STRIPE", url, use_container_width=True)

# ============================================================
# GENERAL HELPERS
# ============================================================
def looks_like_email(x: str) -> bool:
    x = (x or "").strip()
    return ("@" in x) and ("." in x.split("@")[-1])


def cents_to_str(cents: int) -> str:
    return f"${cents / 100:,.2f}"


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
                "label": f"{item.get('name', '?')} — {admin1} — AU",
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

    if not looks_like_email(to_email):
        return False, "A valid user email is required."

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
# STRIPE HELPERS
# ============================================================
def stripe_ready() -> tuple[bool, str]:
    if stripe is None:
        return False, f"Stripe package failed to import: {STRIPE_IMPORT_ERROR or 'unknown error'}"
    if not STRIPE_SECRET_KEY:
        return False, "Missing STRIPE_SECRET_KEY."
    if not APP_BASE_URL:
        return False, "Missing APP_BASE_URL."
    if not APP_BASE_URL.startswith(("http://", "https://")):
        return False, "APP_BASE_URL must start with http:// or https://"
    return True, "OK"


def serialize_trip_payload(trip_payload: Any) -> str:
    try:
        return json.dumps(trip_payload or {})
    except Exception:
        return "{}"


def deserialize_trip_payload(raw: Any) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        obj = json.loads(str(raw))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def calculate_amount_cents(reports: list[str]) -> tuple[int, str]:
    if len(reports) == 4:
        return BUNDLE_PRICE_CENTS, "Bundle (4 reports)"
    return len(reports) * PRICE_PER_REPORT_CENTS, f"{len(reports)} report(s)"


def create_checkout_session(
    user_email: str,
    user_name: str,
    reports: list[str],
    location: str,
    amount_cents: int,
    label: str,
    trip_payload: dict[str, Any] | None = None,
) -> tuple[str, str]:
    ok, why = stripe_ready()
    if not ok:
        raise RuntimeError(why)

    assert stripe is not None
    stripe.api_key = STRIPE_SECRET_KEY

    success_url = f"{APP_BASE_URL}/?paid=1&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{APP_BASE_URL}/?cancelled=1"

    if len(reports) == 4:
        line_items = [
            {
                "price_data": {
                    "currency": CURRENCY,
                    "product_data": {"name": "Sentinel Access — Bundle (4 reports)"},
                    "unit_amount": BUNDLE_PRICE_CENTS,
                },
                "quantity": 1,
            }
        ]
    else:
        line_items = []
        for rt in reports:
            line_items.append(
                {
                    "price_data": {
                        "currency": CURRENCY,
                        "product_data": {"name": f"Sentinel Access — {rt} report"},
                        "unit_amount": PRICE_PER_REPORT_CENTS,
                    },
                    "quantity": 1,
                }
            )

    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        customer_email=user_email or None,
        line_items=line_items,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "user_name": user_name or "",
            "user_email": user_email or "",
            "reports": ",".join(reports or []),
            "location": location or "",
            "pricing_label": label or "",
            "expected_amount_cents": str(amount_cents),
            "trip_payload_json": serialize_trip_payload(trip_payload),
        },
    )
    return str(session.id), str(session.url)


def verify_session_paid(session_id: str) -> tuple[bool, str]:
    ok, why = stripe_ready()
    if not ok:
        return False, why

    assert stripe is not None
    stripe.api_key = STRIPE_SECRET_KEY

    try:
        sess = stripe.checkout.Session.retrieve(session_id)
        status = getattr(sess, "payment_status", None)
        amount_total = getattr(sess, "amount_total", None)
        if status == "paid":
            amount_str = cents_to_str(int(amount_total)) if amount_total is not None else "paid"
            return True, f"Payment confirmed: {amount_str}"
        return False, f"Payment not confirmed yet (status={status})"
    except Exception as e:
        return False, f"Stripe verify error: {e}"


def retrieve_session_metadata(session_id: str) -> tuple[dict[str, str], str]:
    ok, why = stripe_ready()
    if not ok:
        return {}, why

    assert stripe is not None
    stripe.api_key = STRIPE_SECRET_KEY

    try:
        sess = stripe.checkout.Session.retrieve(session_id)
        md = getattr(sess, "metadata", None) or {}
        return {str(k): str(v) for k, v in dict(md).items()}, "OK"
    except Exception as e:
        return {}, f"Stripe metadata retrieve error: {e}"

# ============================================================
# LOCATION MANAGER
# ============================================================
if LocationManager is None:
    st.error("LocationManager import failed. Expected: core/location_manager.py")
    st.stop()

if "lm" not in st.session_state:
    st.session_state.lm = LocationManager()
lm = st.session_state.lm

if not hasattr(lm, "locations") or not hasattr(lm, "get"):
    st.error("LocationManager missing expected methods: locations() and get().")
    st.stop()


def _refresh_locations() -> None:
    try:
        lm.reload()
    except Exception:
        st.session_state.lm = LocationManager()
    st.session_state.location_names = list(st.session_state.lm.locations())


if not st.session_state.location_names:
    st.session_state.location_names = list(lm.locations())

if not st.session_state.location_names:
    st.error("0 locations loaded. Check config/locations.json.")
    st.stop()

# ============================================================
# ACTIONS
# ============================================================
def confirm_action() -> None:
    st.session_state.confirmed_ok = False
    st.session_state.confirmed_payload = None
    st.session_state.final_banner = None
    st.session_state.payment_url = None
    st.session_state.payment_session_id = None
    st.session_state.payment_verified = False
    st.session_state.post_payment_done = False
    st.session_state.fulfillment_started = False
    st.session_state.pending_paid_session_id = None

    user_name = st.session_state.get("user_name", "")
    user_email = st.session_state.get("user_email", "")

    if not user_name.strip():
        st.session_state.final_banner = {
            "type": "error",
            "title": "Name required",
            "detail": "Please enter the user's name before confirming.",
        }
        log("ERROR: Name missing.")
        return

    if not looks_like_email(user_email):
        st.session_state.final_banner = {
            "type": "error",
            "title": "Valid email required",
            "detail": "Please type the email carefully, then click Confirm details.",
        }
        log("ERROR: Valid email missing.")
        return

    report_types = st.session_state.get("report_types") or []
    main_location = st.session_state.get("main_location")

    trip_payload = None
    if "Trip" in report_types:
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
    st.session_state.final_banner = {
        "type": "success",
        "title": "✅ Details confirmed",
        "detail": "Your selections are locked in. Next step: create the payment link.",
    }


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
        log("ERROR: Please confirm details first.")
        st.session_state.final_banner = {
            "type": "error",
            "title": "Confirmation needed",
            "detail": "Please click Confirm details before creating the payment link.",
        }
        return

    st.session_state.is_running = True
    st.session_state.payment_url = None
    st.session_state.payment_session_id = None
    st.session_state.payment_verified = False
    st.session_state.post_payment_done = False
    st.session_state.fulfillment_started = False
    st.session_state.pending_paid_session_id = None
    st.session_state.final_banner = {
        "type": "info",
        "title": "Preparing payment…",
        "detail": "Creating your secure Stripe checkout link.",
    }

    payload = st.session_state.get("confirmed_payload") or {}
    user = payload.get("user") or {}
    report_types: list[str] = payload.get("report_types") or []
    main_location = payload.get("main_location")
    trip_cfg = payload.get("trip")

    user_name = user.get("name") or ""
    user_email = user.get("email") or ""

    if not report_types:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "No reports selected",
            "detail": "Please select at least one report before continuing.",
        }
        return

    if not looks_like_email(user_email):
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Valid email required",
            "detail": "Please enter a valid email before continuing to payment.",
        }
        return

    amount_cents, pricing_label = calculate_amount_cents(report_types)

    try:
        session_id, session_url = create_checkout_session(
            user_email=user_email,
            user_name=user_name,
            reports=report_types,
            location=main_location or "",
            amount_cents=amount_cents,
            label=pricing_label,
            trip_payload=trip_cfg,
        )

        st.session_state.payment_session_id = session_id
        st.session_state.payment_url = session_url
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "success",
            "title": "✅ Payment link ready",
            "detail": f"Next step: click Pay now below. Total: {cents_to_str(amount_cents)}",
        }
        log(f"Stripe session created: {session_id}")
        log(f"Stripe URL: {session_url}")

    except Exception as e:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Stripe error",
            "detail": str(e),
        }
        log(f"Stripe session error: {e}")


def build_payload_from_stripe_metadata(session_id: str) -> tuple[dict[str, Any] | None, str]:
    metadata, msg = retrieve_session_metadata(session_id)
    if not metadata:
        return None, msg

    reports = [x.strip() for x in (metadata.get("reports") or "").split(",") if x.strip()]
    location = metadata.get("location") or ""
    user_name = metadata.get("user_name") or ""
    user_email = metadata.get("user_email") or ""
    trip_payload = deserialize_trip_payload(metadata.get("trip_payload_json"))

    if not reports or not location:
        return None, "Stripe metadata missing reports or location."

    summary_parts = [
        f"User: {user_name or '(no name)'} | {user_email or '(no email)'}",
        f"Reports: {', '.join(reports)}",
        f"Location: {location}",
    ]
    if trip_payload:
        summary_parts.append(
            f"Trip: {trip_payload.get('start')} → {trip_payload.get('stop1')} → {trip_payload.get('stop2')}"
        )

    payload = {
        "user": {"name": user_name, "email": user_email},
        "report_types": reports,
        "main_location": location,
        "trip": trip_payload,
        "summary": " | ".join(summary_parts),
    }
    return payload, "OK"


def fulfill_after_payment(session_id: str) -> None:
    if st.session_state.get("last_fulfilled_session_id") == session_id:
        return

    if st.session_state.get("fulfillment_started"):
        return

    st.session_state.fulfillment_started = True

    payload = st.session_state.get("confirmed_payload") or {}
    report_types = payload.get("report_types") or []
    main_location = payload.get("main_location")

    if not report_types or not main_location:
        rebuilt_payload, rebuilt_msg = build_payload_from_stripe_metadata(session_id)
        if rebuilt_payload is None:
            st.session_state.is_running = False
            st.session_state.final_banner = {
                "type": "error",
                "title": "Payment confirmed, but fulfillment could not start",
                "detail": f"Stripe payment was successful, but Sentinel could not rebuild the order details. {rebuilt_msg}",
            }
            log(f"FULFILLMENT ERROR: {rebuilt_msg}")
            st.session_state.pending_paid_session_id = None
            st.session_state.fulfillment_started = False
            return

        payload = rebuilt_payload
        st.session_state.confirmed_payload = rebuilt_payload
        log("Rebuilt fulfillment payload from Stripe metadata.")

    user = payload.get("user") or {}
    report_types = payload.get("report_types") or []
    main_location = payload.get("main_location")
    trip_cfg = payload.get("trip")

    if not report_types or not main_location:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Payment confirmed, but order details are missing",
            "detail": "Please contact support or run the order again.",
        }
        log("FULFILLMENT ERROR: Missing reports or location after payment.")
        st.session_state.pending_paid_session_id = None
        st.session_state.fulfillment_started = False
        return

    st.session_state.is_running = True
    st.session_state.progress_log = []
    st.session_state.outputs = {}
    st.session_state.final_banner = {
        "type": "info",
        "title": "✅ Payment confirmed",
        "detail": "Generating reports and preparing your email now.",
    }

    log("Payment confirmed ✅")
    log(payload.get("summary", "Starting fulfillment…"))

    output_dir = str(Path.cwd() / "outputs")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    loc_payload = lm.get(main_location)
    if loc_payload is None:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Location error",
            "detail": "Main location was not found in LocationManager.",
        }
        log("FULFILLMENT ERROR: location not found in LocationManager.")
        st.session_state.pending_paid_session_id = None
        st.session_state.fulfillment_started = False
        return

    lat, lon, dbg = extract_lat_lon(loc_payload)
    if lat is None or lon is None:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Location missing coordinates",
            "detail": f"Selected location has no lat/lon. {dbg}",
        }
        log(f"FULFILLMENT ERROR: bad location payload. {dbg}")
        st.session_state.pending_paid_session_id = None
        st.session_state.fulfillment_started = False
        return

    surf_profile = {}
    if isinstance(loc_payload, dict) and isinstance(loc_payload.get("surf_profile"), dict):
        surf_profile = loc_payload["surf_profile"]

    attachments: list[str] = []
    ran_any = False
    errors: list[str] = []

    order = ["Surf", "Sky", "Weather", "Trip"]
    selected_in_order = [x for x in order if x in report_types]

    log("RUN START ✅")

    for rt in selected_in_order:
        log(f"--- Running {rt.upper()} ---")
        try:
            if rt == "Surf":
                if surf_generate_report is None:
                    raise RuntimeError("core.surf_worker.generate_report import failed. See import errors above.")
                pdf_path = call_worker_generate_report(
                    surf_generate_report, main_location, [lat, lon, surf_profile], output_dir, logger=log
                )
                st.session_state.outputs["Surf"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Surf")
                ran_any = True
                log(f"SURF {'complete' if pdf_path else 'failed'}.")

            elif rt == "Sky":
                if sky_worker is None:
                    raise RuntimeError("core.sky_worker import failed. See import errors above.")
                pdf_path = call_worker_generate_report(
                    sky_worker, main_location, [lat, lon], output_dir, logger=log
                )
                st.session_state.outputs["Sky"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Sky")
                ran_any = True
                log(f"SKY {'complete' if pdf_path else 'failed'}.")

            elif rt == "Weather":
                if weather_worker is None:
                    raise RuntimeError("core.weather_worker import failed. See import errors above.")
                pdf_path = call_worker_generate_report(
                    weather_worker, main_location, [lat, lon], output_dir, logger=log
                )
                st.session_state.outputs["Weather"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Weather")
                ran_any = True
                log(f"WEATHER {'complete' if pdf_path else 'failed'}.")

            elif rt == "Trip":
                if trip_worker is None:
                    raise RuntimeError("core.trip_worker import failed. See import errors above.")
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
                    trip_worker, trip_name, trip_data, output_dir, logger=log
                )
                st.session_state.outputs["Trip"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Trip")
                ran_any = True
                log(f"TRIP {'complete' if pdf_path else 'failed'}.")

        except Exception as e:
            st.session_state.outputs[rt] = {"error": str(e)}
            errors.append(f"{rt}: {e}")
            log(f"{rt.upper()} ERROR: {e}")
            log(f"[{rt}] ATTACH: skipped due to worker error.")

    if not ran_any:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Payment confirmed, but no reports were produced",
            "detail": "See System progress for the exact worker error.",
        }
        log("FULFILLMENT ERROR: Nothing ran.")
        st.session_state.pending_paid_session_id = None
        st.session_state.fulfillment_started = False
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
    st.session_state.post_payment_done = True
    st.session_state.payment_url = None
    st.session_state.pending_paid_session_id = None
    st.session_state.last_fulfilled_session_id = session_id
    st.session_state.fulfillment_started = False

    if ok:
        detail = f"Email sent to {user.get('email') or '(no email)'} with {len(attachments)} PDF(s) attached."
        if errors:
            detail += " Some reports had errors — see System progress."
        st.session_state.final_banner = {
            "type": "success",
            "title": "✅ All complete — email sent",
            "detail": detail,
        }
    else:
        detail = f"Payment was confirmed, but email sending failed: {msg}"
        if errors:
            detail += " Some reports also had errors — see System progress."
        st.session_state.final_banner = {
            "type": "error",
            "title": "Payment confirmed, but email failed",
            "detail": detail,
        }

    log("All done ✅")
    st.session_state.confirmed_ok = False
    st.session_state.confirmed_payload = None

# ============================================================
# HANDLE STRIPE RETURN
# ============================================================
if hasattr(st, "query_params"):
    query = st.query_params

    def _qp_get(name: str) -> Optional[str]:
        try:
            val = query.get(name)
            if isinstance(val, list):
                return str(val[0]) if val else None
            return str(val) if val is not None else None
        except Exception:
            return None
else:
    query = st.experimental_get_query_params()

    def _qp_get(name: str) -> Optional[str]:
        try:
            val = query.get(name, [None])[0]
            return str(val) if val is not None else None
        except Exception:
            return None

cancelled_flag = _qp_get("cancelled")
paid_flag = _qp_get("paid")
session_id_from_query = _qp_get("session_id")

log(f"RETURN CHECK: paid={paid_flag}, session_id={session_id_from_query}")

if cancelled_flag == "1":
    st.session_state.final_banner = {
        "type": "error",
        "title": "Payment cancelled",
        "detail": "You cancelled the Stripe checkout. You can still click Pay now again if your payment link is available.",
    }

if paid_flag == "1" and session_id_from_query:
    paid_ok, paid_msg = verify_session_paid(str(session_id_from_query))
    if paid_ok:
        st.session_state.payment_verified = True
        st.session_state.payment_session_id = str(session_id_from_query)
        st.session_state.pending_paid_session_id = str(session_id_from_query)
        st.session_state.final_banner = {
            "type": "info",
            "title": "✅ Payment confirmed",
            "detail": f"{paid_msg} Sentinel is now generating your reports.",
        }
        log(f"PAID VERIFIED: {session_id_from_query}")
    else:
        st.session_state.final_banner = {
            "type": "error",
            "title": "Payment not confirmed",
            "detail": paid_msg,
        }
        log(f"PAID VERIFY FAILED: {paid_msg}")

# ============================================================
# RUN PENDING FULFILLMENT
# ============================================================
pending_session_id = st.session_state.get("pending_paid_session_id")
if (
    pending_session_id
    and st.session_state.get("last_fulfilled_session_id") != pending_session_id
    and not st.session_state.get("is_running")
):
    log(f"STARTING FULFILLMENT: {pending_session_id}")
    fulfill_after_payment(str(pending_session_id))

# ============================================================
# HELPERS FOR UI
# ============================================================
def _worker_status_line(name: str, obj: Any) -> str:
    return f"{name}: {'OK' if obj is not None else 'Import failed'}"

# ============================================================
# 3 PANELS
# ============================================================
left, middle, right = st.columns([0.28, 0.48, 0.24], gap="large")

with left:
    st.subheader("How it works")

    confirmed_ok = st.session_state.get("confirmed_ok", False)
    payment_url = st.session_state.get("payment_url")
    post_done = st.session_state.get("post_payment_done", False)
    pending_paid = st.session_state.get("pending_paid_session_id")

    cls1 = "sa-step-box sa-step-done" if confirmed_ok or payment_url or post_done or pending_paid else "sa-step-box sa-step-current"
    cls2 = "sa-step-box sa-step-done" if payment_url or post_done or pending_paid else "sa-step-box sa-step-current" if confirmed_ok else "sa-step-box"
    cls3 = "sa-step-box sa-step-done" if post_done else "sa-step-box sa-step-current" if payment_url or pending_paid else "sa-step-box"
    cls4 = "sa-step-box sa-step-done" if post_done else "sa-step-box sa-step-current" if pending_paid else "sa-step-box"

    st.markdown(
        f"""
        <div class="{cls1}">
          <b>Step 1 — Choose reports and location</b><br>
          Pick reports and choose the location.
        </div>
        <div class="{cls2}">
          <b>Step 2 — Confirm details</b><br>
          Enter name and email, then click <b>Confirm details</b>.
        </div>
        <div class="{cls3}">
          <b>Step 3 — Pay in Stripe</b><br>
          Click <b>Pay now</b>, complete payment, then return here automatically.
        </div>
        <div class="{cls4}">
          <b>Step 4 — Reports emailed</b><br>
          Sentinel generates the PDFs and emails them after payment is confirmed.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="sa-next-box">
          <b>What happens next</b><br>
          {current_step_text()}
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()
    st.subheader("System checks")

    ok_stripe, stripe_msg = stripe_ready()
    if ok_stripe:
        st.success("Stripe: OK")
    else:
        st.error(f"Stripe: {stripe_msg}")

    st.caption(_worker_status_line("Surf worker", surf_generate_report))
    st.caption(_worker_status_line("Sky worker", sky_worker))
    st.caption(_worker_status_line("Weather worker", weather_worker))
    st.caption(_worker_status_line("Trip worker", trip_worker))
    st.caption(_worker_status_line("Email sender", email_sender_mod))

    st.button("Reset / Refresh page", use_container_width=True, on_click=reset_app_state, disabled=st.session_state.is_running)

with middle:
    st.subheader("Order setup")

    banner = st.session_state.get("final_banner")
    payment_url = st.session_state.get("payment_url")

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

    if payment_url:
        render_pay_button(payment_url)
    elif st.session_state.is_running or st.session_state.get("pending_paid_session_id"):
        st.info("Sentinel is working on the next step…")

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

    with st.expander("➕ Add a new location", expanded=False):
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
            st.button("Save new location", type="primary", use_container_width=True, on_click=add_location_action, disabled=st.session_state.is_running)

    if "Trip" in (st.session_state.get("report_types") or []):
        st.divider()
        st.markdown("**Trip setup**")
        st.selectbox("Start location", st.session_state.location_names, key="trip_start", disabled=st.session_state.is_running)
        st.selectbox("Next location", st.session_state.location_names, key="trip_stop1", disabled=st.session_state.is_running)
        st.selectbox("Next location (2)", st.session_state.location_names, key="trip_stop2", disabled=st.session_state.is_running)
        st.selectbox("Fuel type", ["Petrol", "Diesel"], key="fuel_type", disabled=st.session_state.is_running)
        st.number_input("Fuel consumption (L/100km)", min_value=1.0, value=9.5, step=0.1, key="fuel_l_per_100km", disabled=st.session_state.is_running)
        default_price = 2.10 if (st.session_state.get("fuel_type") or "Petrol") == "Petrol" else 2.20
        st.number_input("Fuel price ($/L)", min_value=0.0, value=float(default_price), step=0.01, key="fuel_price", disabled=st.session_state.is_running)

    st.divider()
    c1, c2 = st.columns(2, gap="small")
    with c1:
        st.button("✅ Confirm details", type="primary", use_container_width=True, on_click=confirm_action, disabled=st.session_state.is_running)
    with c2:
        st.button("💳 Create payment link", type="primary", use_container_width=True, on_click=generate_pay_action, disabled=st.session_state.is_running)

    render_progress_box(height=320)

with right:
    st.markdown(
        """
        <div class="sa-user-box">
          <div style="font-weight:800; font-size:1.05rem; margin-bottom:0.4rem;">
            User details
          </div>
          <div style="font-size:0.95rem; margin-bottom:0.4rem;">
            Enter the name and email carefully before clicking <b>Confirm details</b>.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.text_input("Name", key="user_name", disabled=st.session_state.is_running)
    st.text_input("Email", key="user_email", disabled=st.session_state.is_running)

    if not looks_like_email(st.session_state.get("user_email", "")):
        st.markdown(
            """
            <div class="sa-email-note">
              <b>Email check:</b> Please type a valid email address, then click <b>Confirm details</b> to lock it in before payment.
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.success("Email looks valid. Next step: click Confirm details.")

    st.divider()
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
