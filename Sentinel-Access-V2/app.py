#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

try:
    import stripe
except Exception:
    stripe = None  # type: ignore


# ============================================================
# LOAD ENV
# ============================================================
ENV_FILE_PATH = Path(__file__).resolve().parent / "config" / ".env"
if ENV_FILE_PATH.exists():
    load_dotenv(dotenv_path=ENV_FILE_PATH)
else:
    load_dotenv()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8501").strip()

# Stripe config
CURRENCY = "aud"
PRICE_PER_REPORT_CENTS = 300
BUNDLE_PRICE_CENTS = 1000  # all four reports

# local persistence for checkout context
PROJECT_ROOT = Path(__file__).resolve().parent
PAY_STATE_DIR = PROJECT_ROOT / "outputs" / "pay_state"
PAY_STATE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# IMPORTS
# ============================================================
try:
    from core.location_manager import LocationManager
except Exception:
    LocationManager = None  # type: ignore

try:
    from core.surf_worker import generate_report as surf_generate_report
except Exception:
    surf_generate_report = None  # type: ignore

try:
    import core.sky_worker as sky_worker
except Exception:
    sky_worker = None  # type: ignore

try:
    import core.weather_worker as weather_worker
except Exception:
    weather_worker = None  # type: ignore

try:
    import core.trip_worker as trip_worker
except Exception:
    trip_worker = None  # type: ignore

try:
    import core.email_sender as email_sender_mod
except Exception:
    email_sender_mod = None  # type: ignore


# ============================================================
# PAGE + STYLE
# ============================================================
st.set_page_config(page_title="Sentinel Access (Payments)", layout="wide")

st.markdown(
    """
    <style>
      .block-container {
        padding-top: 0.18rem;
        padding-bottom: 0.30rem;
        max-width: 1380px;
      }

      h1, h2, h3 {
        margin-top: 0.03rem !important;
        margin-bottom: 0.16rem !important;
        line-height: 1.06 !important;
      }

      p, div, label {
        line-height: 1.12 !important;
      }

      div[data-testid="stTextInput"],
      div[data-testid="stSelectbox"],
      div[data-testid="stNumberInput"],
      div[data-testid="stTextArea"],
      div[data-testid="stCheckbox"] {
        margin-bottom: 0.07rem !important;
      }

      div[data-testid="stExpander"] {
        margin-top: 0.08rem !important;
        margin-bottom: 0.08rem !important;
      }

      div[data-testid="stButton"] {
        margin-top: 0.03rem !important;
        margin-bottom: 0.03rem !important;
      }

      button[data-testid="stBaseButton-primary"] {
        background-color: #1f8f3a !important;
        border-color: #1f8f3a !important;
        color: white !important;
        font-weight: 700 !important;
        min-height: 2.20rem !important;
      }

      button[data-testid="stBaseButton-primary"]:hover {
        background-color: #17702d !important;
        border-color: #17702d !important;
      }

      textarea {
        line-height: 1.18 !important;
      }

      div[data-testid="stTextArea"] textarea,
      div[data-testid="stTextArea"] textarea:disabled {
        color: #111827 !important;
        -webkit-text-fill-color: #111827 !important;
        opacity: 1 !important;
        background-color: #f8fafc !important;
        font-weight: 500 !important;
      }

      div[data-testid="stTextArea"] label p {
        color: #111827 !important;
        font-weight: 700 !important;
      }

      div[data-testid="stInfo"],
      div[data-testid="stSuccess"],
      div[data-testid="stError"],
      div[data-testid="stWarning"] {
        padding-top: 0.42rem !important;
        padding-bottom: 0.42rem !important;
        margin-bottom: 0.12rem !important;
      }

      .sa-header {
        font-size: 1.22rem;
        font-weight: 700;
        margin: 0.00rem 0 0.16rem 0;
        color: #111827;
      }

      .sa-step-card {
        background: #f8fafc;
        border: 1px solid #dbe4ee;
        border-radius: 10px;
        padding: 0.55rem 0.72rem;
        margin: 0.14rem 0 0.18rem 0;
      }

      .sa-step-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #0f172a;
        margin-bottom: 0.14rem;
      }

      .sa-step-line {
        font-size: 0.89rem;
        color: #334155;
        margin-bottom: 0.05rem;
      }

      .sa-anchor {
        display: block;
        position: relative;
        top: -12px;
        visibility: hidden;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="sa-header">Sentinel Access — Pay &amp; Run</div>', unsafe_allow_html=True)


# ============================================================
# SESSION STATE DEFAULTS
# ============================================================
defaults = {
    "progress_log": [],
    "outputs": {},
    "confirmed_ok": False,
    "confirmed_payload": None,
    "new_location_candidates": [],
    "chosen_geo_label": None,
    "location_names": [],
    "is_running": False,
    "final_banner": None,
    "paid_ok": False,
    "paid_summary": None,
    "checkout_session_id": None,
    "checkout_url": None,
    "expected_amount_cents": None,
    "auto_redirect_url": None,
    "report_types": [],
    "post_pay_focus": False,
    "report_surf": False,
    "report_sky": False,
    "report_weather": False,
    "report_trip": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ============================================================
# PROGRESS / HELPERS
# ============================================================
def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    st.session_state.progress_log.append(f"{ts} — {msg}")


def render_progress_box(height: int = 205) -> None:
    st.text_area(
        "System progress / live status",
        value="\n".join(st.session_state.progress_log) if st.session_state.progress_log else "",
        height=height,
        disabled=True,
    )


def render_banner() -> None:
    banner = st.session_state.get("final_banner")
    if not banner:
        return

    btype = banner.get("type", "info")
    title = banner.get("title", "")
    detail = banner.get("detail", "")

    if btype == "success":
        st.success(f"{title}\n\n{detail}")
    elif btype == "error":
        st.error(f"{title}\n\n{detail}")
    elif btype == "warning":
        st.warning(f"{title}\n\n{detail}")
    else:
        st.info(f"{title}\n\n{detail}")


def reset_app_state() -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


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


def maybe_add_attachment(attachments: list[str], maybe_path: Any, label: str = "") -> None:
    prefix = f"[{label}] " if label else ""
    if not maybe_path:
        log(f"{prefix}ATTACH: skipped (worker returned None/empty).")
        return

    # unwrap common worker result shapes
    if isinstance(maybe_path, dict):
        maybe_path = maybe_path.get("result")
    elif isinstance(maybe_path, (tuple, list)):
        picked = None
        for item in maybe_path:
            if isinstance(item, (str, os.PathLike)) and str(item).strip():
                picked = item
                break
            if isinstance(item, dict) and item.get("result"):
                picked = item.get("result")
                break
        maybe_path = picked

    if not maybe_path:
        log(f"{prefix}ATTACH: skipped (no usable path after normalising).")
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


def looks_like_email(email: str) -> bool:
    email = (email or "").strip()
    if not email:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def pricing_for_reports(selected: list[str]) -> tuple[int, str, list[str]]:
    order = ["Surf", "Sky", "Weather", "Trip"]
    sel = [x for x in order if x in (selected or [])]
    if len(sel) == 4:
        return BUNDLE_PRICE_CENTS, "Bundle (all 4)", sel
    return PRICE_PER_REPORT_CENTS * len(sel), f"{len(sel)} report(s) @ $3.00", sel


def cents_to_str(cents: int) -> str:
    return f"${cents / 100:.2f} AUD"


def stripe_ready() -> tuple[bool, str]:
    if stripe is None:
        return False, "Stripe library not installed. Run: pip install stripe python-dotenv"
    if not STRIPE_SECRET_KEY:
        return False, "Missing STRIPE_SECRET_KEY in config/.env"
    return True, "OK"


def _get_query_params() -> dict[str, list[str]]:
    try:
        qp = st.query_params  # type: ignore
        out: dict[str, list[str]] = {}
        for k in qp.keys():
            v = qp.get(k)
            if isinstance(v, list):
                out[k] = [str(x) for x in v]
            elif v is None:
                out[k] = []
            else:
                out[k] = [str(v)]
        return out
    except Exception:
        return st.experimental_get_query_params()  # type: ignore


def _clear_query_params() -> None:
    try:
        st.query_params.clear()  # type: ignore
    except Exception:
        st.experimental_set_query_params()  # type: ignore


def _safe_filename(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", text.strip())
    return cleaned[:120] or "state"


def _state_file_for_session(session_id: str) -> Path:
    return PAY_STATE_DIR / f"{_safe_filename(session_id)}.json"


def save_checkout_context(session_id: str, payload: dict[str, Any], amount_cents: int, label: str) -> None:
    p = _state_file_for_session(session_id)
    data = {
        "confirmed_ok": True,
        "confirmed_payload": payload,
        "expected_amount_cents": amount_cents,
        "pricing_label": label,
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_checkout_context(session_id: str) -> dict[str, Any] | None:
    p = _state_file_for_session(session_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_checkout_context(session_id: str) -> None:
    p = _state_file_for_session(session_id)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def create_checkout_session(user_email: str, user_name: str, reports: list[str], location: str, amount_cents: int, label: str) -> tuple[str, str]:
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
            "pricing_label": label,
            "expected_amount_cents": str(amount_cents),
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


def sync_report_types_from_checkboxes() -> list[str]:
    selected: list[str] = []
    if st.session_state.get("report_surf"):
        selected.append("Surf")
    if st.session_state.get("report_sky"):
        selected.append("Sky")
    if st.session_state.get("report_weather"):
        selected.append("Weather")
    if st.session_state.get("report_trip"):
        selected.append("Trip")
    st.session_state.report_types = selected
    return selected


def get_flow_state() -> dict[str, Any]:
    user_name = (st.session_state.get("user_name") or "").strip()
    user_email = (st.session_state.get("user_email") or "").strip()
    report_types = st.session_state.get("report_types") or []
    main_location = st.session_state.get("main_location")

    step1_done = bool(user_name) and looks_like_email(user_email)
    step2_done = bool(report_types) and bool(main_location)
    step3_done = bool(st.session_state.get("confirmed_ok"))
    step4_done = bool(st.session_state.get("paid_ok"))

    if not step1_done:
        current_step = 1
    elif not step2_done:
        current_step = 2
    elif not step3_done:
        current_step = 3
    elif not step4_done:
        current_step = 4
    else:
        current_step = 5

    return {
        "step1_done": step1_done,
        "step2_done": step2_done,
        "step3_done": step3_done,
        "step4_done": step4_done,
        "current_step": current_step,
    }


def render_step_status(flow: dict[str, Any], amount_cents: int, label: str) -> None:
    def yn(v: bool) -> str:
        return "Done" if v else "Waiting"

    st.markdown(
        f"""
        <div class="sa-step-card">
          <div class="sa-step-title">Step progress</div>
          <div class="sa-step-line">Step 1 — Name + email: {yn(flow["step1_done"])}</div>
          <div class="sa-step-line">Step 2 — Reports + location: {yn(flow["step2_done"])}</div>
          <div class="sa-step-line">Step 3 — Confirm selections: {yn(flow["step3_done"])}</div>
          <div class="sa-step-line">Step 4 — Payment: {yn(flow["step4_done"])}</div>
          <div class="sa-step-line">Step 5 — Generate &amp; Email: {"Ready" if flow["current_step"] == 5 else "Locked"}</div>
          <div class="sa-step-line">Price: {cents_to_str(amount_cents) if amount_cents > 0 else "Select report(s)"} {("— " + label) if amount_cents > 0 else ""}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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

location_names = st.session_state.location_names
if not location_names:
    st.error("0 locations loaded. Check config/locations.json.")
    st.stop()


# ============================================================
# HANDLE RETURN FROM STRIPE
# ============================================================
qp = _get_query_params()
paid_flag = (qp.get("paid") or [""])[0]
session_id = (qp.get("session_id") or [""])[0]
cancelled = (qp.get("cancelled") or [""])[0]

if cancelled == "1":
    st.session_state.paid_ok = False
    st.session_state.checkout_session_id = None
    st.session_state.checkout_url = None
    st.session_state.auto_redirect_url = None
    st.session_state.final_banner = {
        "type": "error",
        "title": "Payment cancelled",
        "detail": "No charge was made.",
    }
    _clear_query_params()

if paid_flag == "1" and session_id:
    ok, msg = verify_session_paid(session_id)
    if ok:
        ctx = load_checkout_context(session_id)
        if ctx and isinstance(ctx.get("confirmed_payload"), dict):
            st.session_state.confirmed_payload = ctx["confirmed_payload"]
            st.session_state.confirmed_ok = bool(ctx.get("confirmed_ok", True))
            st.session_state.expected_amount_cents = ctx.get("expected_amount_cents")
        st.session_state.paid_ok = True
        st.session_state.checkout_session_id = session_id
        st.session_state.checkout_url = None
        st.session_state.auto_redirect_url = None
        st.session_state.paid_summary = msg
        st.session_state.final_banner = {
            "type": "success",
            "title": "Step 4 complete",
            "detail": "Payment confirmed. Step 5 is now ready below.",
        }
        st.session_state.post_pay_focus = True
        _clear_query_params()
    else:
        st.session_state.paid_ok = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Payment not confirmed",
            "detail": msg,
        }


# ============================================================
# ACTIONS
# ============================================================
def confirm_action() -> None:
    st.session_state.confirmed_ok = False
    st.session_state.confirmed_payload = None
    st.session_state.final_banner = None

    user_name = (st.session_state.get("user_name") or "").strip()
    user_email = (st.session_state.get("user_email") or "").strip()
    report_types = st.session_state.get("report_types") or []
    main_location = st.session_state.get("main_location")

    if not looks_like_email(user_email) or not user_name:
        msg = "Enter name and a valid email before confirming."
        log(f"ERROR: {msg}")
        st.session_state.final_banner = {
            "type": "error",
            "title": "Step 1 incomplete",
            "detail": msg,
        }
        return

    if not report_types or not main_location:
        msg = "Choose at least one report and a location before confirming."
        log(f"ERROR: {msg}")
        st.session_state.final_banner = {
            "type": "error",
            "title": "Step 2 incomplete",
            "detail": msg,
        }
        return

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
        f"User: {user_name} | {user_email}",
        f"Reports: {', '.join(report_types)}",
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
    st.session_state.paid_ok = False
    st.session_state.paid_summary = None
    st.session_state.checkout_session_id = None
    st.session_state.checkout_url = None
    st.session_state.auto_redirect_url = None

    log("Confirmed selections.")
    log(st.session_state.confirmed_payload["summary"])
    st.session_state.final_banner = {
        "type": "success",
        "title": "Step 3 complete",
        "detail": "Selections confirmed. Step 4 Pay is now next.",
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
        log("ERROR: Select a match before saving.")
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


def pay_action() -> None:
    st.session_state.paid_ok = False
    st.session_state.checkout_session_id = None
    st.session_state.checkout_url = None
    st.session_state.auto_redirect_url = None
    st.session_state.final_banner = None

    payload = st.session_state.get("confirmed_payload") or {}
    user = payload.get("user") or {}
    reports: list[str] = payload.get("report_types") or []
    location = payload.get("main_location") or ""
    user_email = str(user.get("email") or "").strip()

    if not reports or not payload:
        st.session_state.final_banner = {
            "type": "error",
            "title": "Step 3 required",
            "detail": "Confirm selections before payment.",
        }
        return

    if not looks_like_email(user_email):
        st.session_state.final_banner = {
            "type": "error",
            "title": "Email required",
            "detail": "Please enter a valid email before payment.",
        }
        return

    ok, why = stripe_ready()
    if not ok:
        st.session_state.final_banner = {
            "type": "error",
            "title": "Stripe not ready",
            "detail": why,
        }
        return

    amount_cents, label, normalized = pricing_for_reports(reports)
    if amount_cents <= 0:
        st.session_state.final_banner = {
            "type": "error",
            "title": "Invalid selection",
            "detail": "Choose at least one report.",
        }
        return

    try:
        sess_id, sess_url = create_checkout_session(
            user_email=user_email,
            user_name=str(user.get("name") or ""),
            reports=normalized,
            location=str(location),
            amount_cents=amount_cents,
            label=label,
        )
        save_checkout_context(sess_id, payload, amount_cents, label)
        st.session_state.checkout_session_id = sess_id
        st.session_state.checkout_url = sess_url
        st.session_state.auto_redirect_url = None
        st.session_state.expected_amount_cents = amount_cents
        st.session_state.final_banner = {
            "type": "info",
            "title": "Step 4 ready",
            "detail": "Continue to Stripe using the button below.",
        }
        log(f"PAY: Checkout session created: {sess_id} for {cents_to_str(amount_cents)}")
        st.rerun()
    except Exception as e:
        st.session_state.final_banner = {
            "type": "error",
            "title": "Stripe error",
            "detail": str(e),
        }
        log(f"PAY ERROR: {e}")


def generate_and_email_action() -> None:
    if not st.session_state.get("confirmed_ok"):
        st.session_state.final_banner = {
            "type": "error",
            "title": "Step 3 required",
            "detail": "Please confirm selections first.",
        }
        return

    if not st.session_state.get("paid_ok"):
        st.session_state.final_banner = {
            "type": "error",
            "title": "Step 4 required",
            "detail": "Please complete payment before generating.",
        }
        return

    st.session_state.is_running = True
    st.session_state.final_banner = {
        "type": "info",
        "title": "Step 5 running",
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
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Nothing to run",
            "detail": "No reports executed successfully.",
        }
        return

    log(payload.get("summary", "Starting run…"))

    output_dir = str(Path.cwd() / "outputs")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    loc_payload = lm.get(main_location)
    if loc_payload is None:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Location error",
            "detail": "Main location not found in LocationManager.",
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
    errors: list[str] = []
    ran_any = False

    _, label, selected_in_order = pricing_for_reports(report_types)
    log("Run initialised successfully.")

    for rt in selected_in_order:
        log(f"--- Running {rt.upper()} ---")
        try:
            if rt == "Surf":
                if surf_generate_report is None:
                    raise RuntimeError("core.surf_worker.generate_report import failed.")
                pdf_path = call_worker_generate_report(
                    surf_generate_report,
                    main_location,
                    [lat, lon, surf_profile],
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Surf"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Surf")
                ran_any = True
                log(f"SURF {'complete' if pdf_path else 'failed'}.")

            elif rt == "Sky":
                pdf_path = call_worker_generate_report(
                    sky_worker,
                    main_location,
                    [lat, lon],
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Sky"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Sky")
                ran_any = True
                log(f"SKY {'complete' if pdf_path else 'failed'}.")

            elif rt == "Weather":
                pdf_path = call_worker_generate_report(
                    weather_worker,
                    main_location,
                    [lat, lon],
                    output_dir,
                    logger=log,
                )
                st.session_state.outputs["Weather"] = {"result": pdf_path}
                maybe_add_attachment(attachments, pdf_path, label="Weather")
                ran_any = True
                log(f"WEATHER {'complete' if pdf_path else 'failed'}.")

            elif rt == "Trip":
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
                ran_any = True
                log(f"TRIP {'complete' if pdf_path else 'failed'}.")

        except Exception as e:
            st.session_state.outputs[rt] = {"error": str(e)}
            errors.append(f"{rt}: {e}")
            log(f"{rt.upper()} ERROR: {e}")

    if not ran_any:
        st.session_state.is_running = False
        st.session_state.final_banner = {
            "type": "error",
            "title": "Nothing ran",
            "detail": "No reports executed successfully.",
        }
        return

    # final attachment clean-up before email sender
    attachments = [str(Path(a)) for a in attachments if a and str(a).strip()]

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
        "",
        f"Payment: {st.session_state.paid_summary or label}",
        "",
        "Sentinel Access",
    ]
    if "Trip" in selected_in_order and trip_cfg:
        body_lines.insert(5, f"- Trip: {trip_cfg.get('start')} → {trip_cfg.get('stop1')} → {trip_cfg.get('stop2')}")
    body = "\n".join(body_lines)

    ok, msg = send_email_via_sender(
        to_email=str(user.get("email") or ""),
        username=str(user.get("name") or ""),
        subject=subject,
        body=body,
        attachments=attachments,
    )
    log(f"{'EMAIL OK' if ok else 'EMAIL ERROR'}: {msg}")

    st.session_state.is_running = False

    if ok:
        detail = f"Email sent to {user.get('email') or '(no email)'} with {len(attachments)} PDF(s)."
        if errors:
            detail += " (Some reports had errors—see System progress.)"
        st.session_state.final_banner = {
            "type": "success",
            "title": "Step 5 complete",
            "detail": detail,
        }
        try:
            st.toast("✅ All complete — email sent", icon="✅")
        except Exception:
            pass

        time.sleep(2)

        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    else:
        st.session_state.final_banner = {
            "type": "error",
            "title": "Completed, but email failed",
            "detail": f"Email failed: {msg}",
        }
        try:
            st.toast("❌ Completed, but email failed", icon="❌")
        except Exception:
            pass

    log("All done ✅")
    st.session_state.confirmed_ok = False
    st.session_state.confirmed_payload = None


# ============================================================
# PRE-UI DERIVED STATE
# ============================================================
sync_report_types_from_checkboxes()
flow = get_flow_state()
amount_cents, label, _ = pricing_for_reports(st.session_state.get("report_types") or [])


# ============================================================
# UI LAYOUT
# ============================================================
left, middle, right = st.columns([0.27, 0.50, 0.23], gap="medium")

with left:
    with st.container(border=True):
        st.subheader("Step 1")
        st.caption("Enter your details first.")
        st.text_input("Name", key="user_name", disabled=st.session_state.is_running)
        st.text_input("Email", key="user_email", disabled=st.session_state.is_running)

        if flow["current_step"] == 1:
            st.info("Current step: enter name and valid email.")
        elif flow["step1_done"]:
            st.caption("Step 1 complete")

        st.button(
            "Reset / Refresh page",
            width="stretch",
            on_click=reset_app_state,
            disabled=st.session_state.is_running,
            key="reset_page_btn",
        )

with middle:
    with st.container(border=True):
        st.markdown('<span id="step-five-anchor" class="sa-anchor"></span>', unsafe_allow_html=True)

        if st.session_state.get("post_pay_focus"):
            components.html(
                """
                <html>
                  <body>
                    <script>
                      window.parent.location.hash = "step-five-anchor";
                      window.parent.scrollTo({top: 0, behavior: "smooth"});
                    </script>
                  </body>
                </html>
                """,
                height=0,
            )
            st.session_state.post_pay_focus = False

        render_banner()
        render_step_status(flow, amount_cents, label)

        st.subheader("Step 2")
        st.caption("Choose report(s) and location.")
        c1, c2 = st.columns(2, gap="small")
        with c1:
            st.checkbox("Surf", key="report_surf", disabled=st.session_state.is_running)
            st.checkbox("Sky", key="report_sky", disabled=st.session_state.is_running)
        with c2:
            st.checkbox("Weather", key="report_weather", disabled=st.session_state.is_running)
            st.checkbox("Trip", key="report_trip", disabled=st.session_state.is_running)

        sync_report_types_from_checkboxes()

        st.selectbox(
            "Location",
            st.session_state.location_names,
            key="main_location",
            disabled=st.session_state.is_running,
        )

        if "Trip" in (st.session_state.get("report_types") or []):
            st.markdown("**Trip setup**")
            st.selectbox("Start location", st.session_state.location_names, key="trip_start", disabled=st.session_state.is_running)
            st.selectbox("Next location", st.session_state.location_names, key="trip_stop1", disabled=st.session_state.is_running)
            st.selectbox("Next location (2)", st.session_state.location_names, key="trip_stop2", disabled=st.session_state.is_running)
            st.selectbox("Fuel type", ["Petrol", "Diesel"], key="fuel_type", disabled=st.session_state.is_running)
            st.number_input("Fuel consumption (L/100km)", min_value=1.0, value=9.5, step=0.1, key="fuel_l_per_100km", disabled=st.session_state.is_running)
            default_price = 2.10 if (st.session_state.get("fuel_type") or "Petrol") == "Petrol" else 2.20
            st.number_input("Fuel price ($/L)", min_value=0.0, value=float(default_price), step=0.01, key="fuel_price", disabled=st.session_state.is_running)

        if flow["current_step"] == 2:
            st.info("Current step: choose report(s) and location.")
        elif flow["step2_done"]:
            st.caption("Step 2 complete")

        st.subheader("Step 3")
        if flow["step3_done"]:
            st.button("Step 3 Complete — Confirmed", width="stretch", disabled=True, key="step3_done_btn")
        else:
            st.button(
                "Confirm selections",
                type="primary" if flow["current_step"] == 3 else "secondary",
                width="stretch",
                on_click=confirm_action,
                disabled=st.session_state.is_running or (flow["current_step"] < 3),
                key="confirm_btn",
            )

        st.subheader("Step 4")
        pay_ok, pay_why = stripe_ready()
        if not pay_ok:
            st.warning(pay_why)

        if flow["step4_done"]:
            st.button("Step 4 Complete — Paid", width="stretch", disabled=True, key="step4_done_btn")
        else:
            if st.session_state.get("checkout_url") and flow["current_step"] == 4:
                st.link_button(
                    "Continue to Stripe",
                    st.session_state["checkout_url"],
                    type="primary",
                    width="stretch",
                )
            else:
                st.button(
                    "Pay now",
                    type="primary" if flow["current_step"] == 4 else "secondary",
                    width="stretch",
                    on_click=pay_action,
                    disabled=st.session_state.is_running or (flow["current_step"] != 4) or (not pay_ok),
                    key="pay_now_btn",
                )

        st.subheader("Step 5")
        if st.session_state.get("paid_ok"):
            st.button(
                "Generate & Email",
                type="primary",
                width="stretch",
                on_click=generate_and_email_action,
                disabled=st.session_state.is_running,
                key="generate_email_btn",
            )
        else:
            st.button(
                "Generate & Email",
                width="stretch",
                disabled=True,
                key="generate_email_btn_disabled",
            )

        if flow["current_step"] == 5 and st.session_state.get("paid_ok"):
            st.success("Current step: click Generate & Email.")
        elif flow["current_step"] < 5:
            st.caption("Step 5 will unlock after payment.")

        render_progress_box(height=205)

        with st.expander("➕ Add a new location", expanded=False):
            st.text_input("New location name", key="new_loc_name", disabled=st.session_state.is_running)
            st.selectbox("State", ["VIC", "NSW", "QLD", "SA", "WA", "TAS", "NT", "ACT"], key="new_state", disabled=st.session_state.is_running)

            cols2 = st.columns([1, 1], gap="small")
            with cols2[0]:
                if st.button("Find matches", width="stretch", disabled=st.session_state.is_running, key="find_matches_btn"):
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
                current_choice = st.session_state.get("chosen_geo_label")
                safe_index = labels.index(current_choice) if current_choice in labels else 0
                st.selectbox(
                    "Select best match",
                    labels,
                    index=safe_index,
                    key="chosen_geo_label",
                    disabled=st.session_state.is_running,
                )

            with cols2[1]:
                st.button(
                    "Save new location",
                    type="primary",
                    width="stretch",
                    on_click=add_location_action,
                    disabled=st.session_state.is_running,
                    key="save_location_btn",
                )

with right:
    with st.container(border=True):
        st.subheader("Examples")
        tab_surf, tab_sky, tab_weather, tab_trip = st.tabs(["Surf", "Sky", "Weather", "Trip"])

        with tab_surf:
            st.markdown("**Surf example**")
            st.caption("Today panel + next best day + 7-day trend with surf windows.")

        with tab_sky:
            st.markdown("**Sky example**")
            st.caption("Depends on your sky_worker output structure.")

        with tab_weather:
            st.markdown("**Weather example**")
            st.caption("Depends on your weather_worker output structure.")

        with tab_trip:
            st.markdown("**Trip example**")
            demo = pd.DataFrame(
                [
                    {"Leg": "1. Start → Next", "Distance (km)": 120.0, "Fuel (L)": 11.40, "Fuel cost ($)": 23.94},
                    {"Leg": "2. Next → Next 2", "Distance (km)": 65.0, "Fuel (L)": 6.18, "Fuel cost ($)": 12.98},
                ]
            )
            st.dataframe(demo, width="stretch", hide_index=True)

        outputs = st.session_state.get("outputs") or {}
        if outputs:
            st.divider()
            st.caption("Latest outputs")
            for k, v in outputs.items():
                with st.expander(k, expanded=False):
                    st.write(v)
