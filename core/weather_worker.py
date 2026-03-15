#!/usr/bin/env python3
from __future__ import annotations

import os
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Callable

import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm


def deg_to_compass(deg):
    if deg is None or (isinstance(deg, float) and np.isnan(deg)):
        return "N/A"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    idx = int((deg + 11.25) / 22.5) % 16
    return dirs[idx]


def _safe_get_json(url: str, timeout: int = 12):
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_weather_data(lat, lon):
    try:
        h_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&hourly=temperature_2m,precipitation,wind_speed_10m,wind_direction_10m,wind_gusts_10m,weather_code"
            "&timezone=auto"
            "&forecast_days=3"
        )

        d_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&daily=temperature_2m_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant,precipitation_sum,weather_code"
            "&timezone=auto"
            "&forecast_days=7"
        )

        h_resp = _safe_get_json(h_url)
        d_resp = _safe_get_json(d_url)

        if "hourly" not in h_resp or "time" not in h_resp["hourly"]:
            return None, None
        if "daily" not in d_resp or "time" not in d_resp["daily"]:
            return None, None

        h_df = pd.DataFrame(h_resp["hourly"])
        d_df = pd.DataFrame(d_resp["daily"])

        h_df["time"] = pd.to_datetime(h_df["time"]).dt.tz_localize(None)
        d_df["time"] = pd.to_datetime(d_df["time"]).dt.tz_localize(None)

        h_cols = ["temperature_2m", "precipitation", "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "weather_code"]
        d_cols = ["temperature_2m_max", "wind_speed_10m_max", "wind_gusts_10m_max", "wind_direction_10m_dominant", "precipitation_sum", "weather_code"]

        for col in h_cols:
            h_df[col] = pd.to_numeric(h_df.get(col), errors="coerce")

        for col in d_cols:
            d_df[col] = pd.to_numeric(d_df.get(col), errors="coerce")

        h_df["precipitation"] = h_df["precipitation"].fillna(0.0)
        d_df["precipitation_sum"] = d_df["precipitation_sum"].fillna(0.0)

        return h_df.sort_values("time"), d_df.sort_values("time")

    except Exception:
        return None, None


def _format_hour_axis(ax):
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 3, 6, 9, 12, 15, 18, 21]))
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(
            lambda x, p: mdates.DateFormatter("%I%p")(x).replace("AM", "A").replace("PM", "P").lstrip("0")
        )
    )
    ax.tick_params(axis="x", rotation=0)


def generate_daily(h_df, location_name):
    now_dt = datetime.now(ZoneInfo("Australia/Melbourne")).replace(tzinfo=None)
    day_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    day_df = h_df[(h_df["time"] >= day_start) & (h_df["time"] < day_end)].copy()
    if day_df.empty or len(day_df) < 8:
        day_df = h_df.head(24).copy()

    actual = day_df[day_df["time"] <= now_dt].copy()
    forecast = day_df[day_df["time"] > now_dt].copy()

    fig, ax_temp = plt.subplots(figsize=(11, 5.7))
    ax_wind = ax_temp.twinx()
    ax_rain = ax_temp.twinx()
    ax_rain.spines["right"].set_position(("axes", 1.12))

    l1a, = ax_temp.plot(actual["time"], actual["temperature_2m"], "-", lw=2.6, label="Actual Temp")
    l1f, = ax_temp.plot(forecast["time"], forecast["temperature_2m"], "--", lw=2.6, label="Forecast Temp")

    l2a, = ax_wind.plot(actual["time"], actual["wind_speed_10m"], "-", lw=1.6, label="Actual Wind")
    l2f, = ax_wind.plot(forecast["time"], forecast["wind_speed_10m"], "--", lw=1.6, label="Forecast Wind")
    l2g, = ax_wind.plot(day_df["time"], day_df["wind_gusts_10m"], ":", lw=1.2, label="Wind Gusts")

    l3 = ax_rain.bar(day_df["time"], day_df["precipitation"], alpha=0.25, width=0.03, label="Rain")

    for _, row in day_df.iloc[::3].iterrows():
        compass = deg_to_compass(row["wind_direction_10m"])
        if pd.notna(row["wind_speed_10m"]):
            ax_wind.annotate(compass, (row["time"], row["wind_speed_10m"]), xytext=(0, 7), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")

    ax_temp.axvline(now_dt, linestyle=":", lw=2)

    ax_temp.set_title(f"{location_name.upper()} — TODAY (Hourly)", fontweight="bold", fontsize=14)
    ax_temp.set_ylabel("Temp (°C)", fontweight="bold")
    ax_wind.set_ylabel("Wind (km/h)", fontweight="bold")
    ax_rain.set_ylabel("Rain (mm)", fontweight="bold")

    _format_hour_axis(ax_temp)
    ax_temp.grid(True, alpha=0.18)

    ax_temp.legend([l1f, l1f, l2f, l2g, l2g, l3],
                   ["Actual Temp", "Forecast Temp", "Actual Wind", "Forecast Wind", "Wind Gusts", "Rain"],
                   loc="upper left", fontsize=8)

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_weekly(d_df, location_name):
    fig, ax_temp = plt.subplots(figsize=(11, 5.7))

    if d_df is None or d_df.empty or "time" not in d_df.columns:
        ax_temp.text(0.5, 0.5, "No weekly data returned from API.", ha="center", va="center", transform=ax_temp.transAxes)
        ax_temp.set_title(f"7-DAY OUTLOOK: {location_name}", fontweight="bold", fontsize=14)
        ax_temp.axis("off")
        buf = BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
        plt.close(fig)
        buf.seek(0)
        return buf

    ax_wind = ax_temp.twinx()
    ax_rain = ax_temp.twinx()
    ax_rain.spines["right"].set_position(("axes", 1.12))

    l1, = ax_temp.plot(d_df["time"], d_df["temperature_2m_max"], lw=2.6, label="Max Temp")
    l2, = ax_wind.plot(d_df["time"], d_df["wind_speed_10m_max"], lw=1.8, label="Max Wind")
    l2g, = ax_wind.plot(d_df["time"], d_df["wind_gusts_10m_max"], linestyle=":", lw=1.3, label="Max Gusts")
    l3 = ax_rain.bar(d_df["time"], d_df["precipitation_sum"], alpha=0.25, width=0.55, label="Rain")

    for _, row in d_df.iterrows():
        compass = deg_to_compass(row["wind_direction_10m_dominant"])
        if pd.notna(row["wind_speed_10m_max"]):
            ax_wind.annotate(compass, (row["time"], row["wind_speed_10m_max"]), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=9, fontweight="bold")

    ax_temp.set_title(f"7-DAY OUTLOOK: {location_name}", fontweight="bold", fontsize=14)
    ax_temp.set_ylabel("Max Temp (°C)", fontweight="bold")
    ax_wind.set_ylabel("Wind (km/h)", fontweight="bold")
    ax_rain.set_ylabel("Rain (mm)", fontweight="bold")

    ax_temp.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
    ax_temp.grid(True, alpha=0.18)

    ax_temp.legend([l2, l1, l2g, l3], ["Max Temp", "Max Wind", "Max Gusts", "Rain"], loc="upper left", fontsize=8)

    buf = BytesIO()
    plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_report(target: str, data: Any, output_dir: str, logger: Callable[[str], None] = print):
    """
    Standardized signature: (target, data, output_dir, logger=...)
    data: dict or tuple/list (lat, lon)
    Returns PDF path or None.
    """
    try:
        if isinstance(data, dict):
            lat = float(data.get("latitude", data.get("lat", 0)))
            lon = float(data.get("longitude", data.get("lon", 0)))
        elif isinstance(data, (list, tuple)) and len(data) >= 2:
            lat, lon = float(data[0]), float(data[1])
        else:
            logger(f"❌ Error: Unexpected data format in weather_worker for {target}")
            return None

        logger(f"Weather worker: target={target} lat={lat} lon={lon}")

        h_df, d_df = fetch_weather_data(lat, lon)
        if h_df is None or h_df.empty:
            logger(f"❌ API failure in weather_worker for {target}")
            return None

        final_folder = os.path.join(output_dir, target)
        os.makedirs(final_folder, exist_ok=True)

        timestamp = datetime.now(ZoneInfo("Australia/Melbourne")).strftime("%Y-%m-%d_%H%M%S")
        ppath = os.path.join(final_folder, f"Weather_Report_{target}_{timestamp}.pdf")

        daily_img = generate_daily(h_df, target)
        weekly_img = generate_weekly(d_df, target)

        doc = SimpleDocTemplate(ppath, pagesize=A4, topMargin=0.6 * cm, bottomMargin=0.6 * cm)
        styles = getSampleStyleSheet()

        story = [
            Paragraph(f"<b>WEATHER SENTINEL REPORT: {target}</b>", styles["Title"]),
            Spacer(1, 10),
            Image(daily_img, 19 * cm, 9.2 * cm),
            Spacer(1, 10),
            Image(weekly_img, 19 * cm, 9.2 * cm),
            Spacer(1, 6),
            Paragraph(f"<font size=8>Generated | {datetime.now(ZoneInfo('Australia/Melbourne')).strftime('%Y-%m-%d %H:%M')}</font>", styles["Normal"]),
        ]

        doc.build(story)

        if os.path.exists(ppath) and os.path.getsize(ppath) > 1000:
            logger(f"SUCCESS: Weather PDF created at {ppath}")
            return ppath

        logger("❌ Weather PDF was not written or is too small.")
        return None

    except Exception as e:
        logger(f"❌ Critical failure in weather_worker for {target}: {e}")
        return None
