#!/usr/bin/env python3
from __future__ import annotations

import json
import math
from datetime import datetime
from io import BytesIO
from pathlib import Path

import matplotlib
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
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from core.build_spot_profile import build_profile, save_profile

REQUEST_TIMEOUT = 20
FORECAST_DAYS = 7
USE_ESTIMATED_TIDE_IF_MISSING = False
PROFILE_PATH = Path(__file__).resolve().parents[1] / "config" / "spot_profile.json"


def _log(logger, msg: str) -> None:
    try:
        if callable(logger):
            logger(msg)
        else:
            print(msg)
    except Exception:
        print(msg)


def deg_to_text(deg):
    if deg is None or pd.isna(deg):
        return ""
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
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


def score_out_of_10(score_100):
    if score_100 is None or pd.isna(score_100):
        return "n/a"
    return f"{round(float(score_100) / 10.0):.0f}/10"


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
        "&timezone=auto"
    )
    data = fetch_json(url)
    hourly = data.get("hourly", {})
    df = pd.DataFrame(hourly)
    if df.empty or "time" not in df.columns:
        raise ValueError("Marine API returned no hourly data.")
    df["time"] = pd.to_datetime(df["time"])
    return df


def fetch_open_meteo_weather(lat: float, lon: float) -> pd.DataFrame:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&hourly=wind_speed_10m,wind_direction_10m"
        f"&forecast_days={FORECAST_DAYS}"
        "&timezone=auto"
    )
    data = fetch_json(url)
    hourly = data.get("hourly", {})
    df = pd.DataFrame(hourly)
    if df.empty or "time" not in df.columns:
        raise ValueError("Forecast API returned no hourly data.")
    df["time"] = pd.to_datetime(df["time"])
    return df.rename(columns={
        "wind_speed_10m": "wind_speed_10m_main",
        "wind_direction_10m": "wind_direction_10m_main",
    })


def fetch_bom_access_g_weather(lat: float, lon: float) -> pd.DataFrame | None:
    try:
        url = (
            "https://api.open-meteo.com/v1/bom"
            f"?latitude={lat}&longitude={lon}"
            "&hourly=wind_speed_10m,wind_direction_10m"
            f"&forecast_days={FORECAST_DAYS}"
            "&timezone=auto"
        )
        data = fetch_json(url)
        hourly = data.get("hourly", {})
        df = pd.DataFrame(hourly)
        if df.empty or "time" not in df.columns:
            return None
        df["time"] = pd.to_datetime(df["time"])
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
    }

    if wx_bom is not None:
        df = df.merge(wx_bom, on="time", how="left")
    else:
        df["wind_speed_10m_bom"] = np.nan
        df["wind_direction_10m_bom"] = np.nan

    df["wind_speed_10m"] = df[["wind_speed_10m_main", "wind_speed_10m_bom"]].mean(axis=1, skipna=True)

    df["wind_direction_10m"] = df.apply(
        lambda row: circular_mean_deg([row.get("wind_direction_10m_main"), row.get("wind_direction_10m_bom")]),
        axis=1,
    )

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


def score_row_factory(spot: dict):
    beach_orientation_deg = float(spot["beach_orientation_deg"])
    preferred_swell_dir_min = spot["preferred_swell_dir_min"]
    preferred_swell_dir_max = spot["preferred_swell_dir_max"]
    preferred_swell_min_m = float(spot["preferred_swell_min_m"])
    preferred_swell_max_m = float(spot["preferred_swell_max_m"])
    preferred_tide_min_m = spot["preferred_tide_min_m"]
    preferred_tide_max_m = spot["preferred_tide_max_m"]

    def score_row(row: pd.Series) -> pd.Series:
        reasons = []
        swell_h = row.get("swell_wave_height", np.nan)
        swell_dir = row.get("swell_wave_direction", np.nan)
        wave_period = row.get("wave_period", np.nan)
        wind_kmh = row.get("wind_speed_10m", np.nan)
        wind_dir = row.get("wind_direction_10m", np.nan)
        tide_h = row.get("tide_height", np.nan)

        score = 0.0

        swell_score = 0.0
        if not pd.isna(swell_h):
            if preferred_swell_min_m <= swell_h <= preferred_swell_max_m:
                swell_score = 30.0
                reasons.append(f"swell size in range ({swell_h:.1f}m)")
            elif swell_h < preferred_swell_min_m:
                swell_score = max(0.0, 30.0 - (preferred_swell_min_m - swell_h) * 20.0)
                reasons.append(f"swell a bit small ({swell_h:.1f}m)")
            else:
                swell_score = max(0.0, 30.0 - (swell_h - preferred_swell_max_m) * 10.0)
                reasons.append(f"swell a bit oversized ({swell_h:.1f}m)")
        score += swell_score

        swell_dir_score = 0.0
        if not pd.isna(swell_dir) and preferred_swell_dir_min is not None and preferred_swell_dir_max is not None:
            if in_direction_window(float(swell_dir), preferred_swell_dir_min, preferred_swell_dir_max):
                swell_dir_score = 20.0
                reasons.append(f"swell suits break ({deg_to_text(swell_dir)})")
            else:
                diffs = [
                    angular_diff(float(swell_dir), float(preferred_swell_dir_min)),
                    angular_diff(float(swell_dir), float(preferred_swell_dir_max)),
                ]
                swell_dir_score = max(0.0, 20.0 - min(diffs) * 0.35)
                reasons.append(f"swell less ideal ({deg_to_text(swell_dir)})")
        score += swell_dir_score

        period_score = 10.0 if not pd.isna(wave_period) and wave_period >= 14 else 7.5 if not pd.isna(wave_period) and wave_period >= 10 else 5.0 if not pd.isna(wave_period) and wave_period >= 8 else 2.0
        score += period_score

        offshore_from_deg = (beach_orientation_deg + 180) % 360
        wind_score = 0.0
        if not pd.isna(wind_kmh) and not pd.isna(wind_dir):
            alignment = angular_diff(float(wind_dir), offshore_from_deg)
            dir_component = 20.0 if alignment <= 30 else 14.0 if alignment <= 60 else 7.0 if alignment <= 100 else 0.0
            speed_component = 10.0 if wind_kmh <= 12 else 7.0 if wind_kmh <= 20 else 4.0 if wind_kmh <= 28 else 1.0
            wind_score = dir_component + speed_component
        score += wind_score

        tide_score = 0.0
        if preferred_tide_min_m is not None and preferred_tide_max_m is not None and not pd.isna(tide_h):
            if preferred_tide_min_m <= tide_h <= preferred_tide_max_m:
                tide_score = 10.0
            elif tide_h < preferred_tide_min_m:
                tide_score = max(0.0, 10.0 - (preferred_tide_min_m - tide_h) * 6.0)
            else:
                tide_score = max(0.0, 10.0 - (tide_h - preferred_tide_max_m) * 4.0)
        score += tide_score

        hour = row["time"].hour
        score += 5.0 if 5 <= hour <= 9 else 2.0 if 10 <= hour <= 12 else 0.0

        confidence = 0.85
        if pd.isna(swell_h) or pd.isna(swell_dir) or pd.isna(wind_kmh) or pd.isna(wind_dir):
            confidence -= 0.25
        confidence *= float(row.get("wind_agreement", 0.65))
        if USE_ESTIMATED_TIDE_IF_MISSING and not pd.isna(tide_h):
            confidence -= 0.10
        confidence = clamp(confidence, 0.15, 0.98)

        score_10 = round(score / 10.0)
        rating = "Good" if score_10 >= 8 else "Fair" if score_10 >= 6 else "Marginal" if score_10 >= 4 else "Poor"

        return pd.Series({
            "surf_score": round(score, 1),
            "surf_rating": rating,
            "confidence": round(confidence, 2),
            "summary_reasons": ", ".join(reasons[:5]),
        })

    return score_row


def find_best_windows(df: pd.DataFrame, spot: dict) -> pd.DataFrame:
    scored = df.copy()
    scored[["surf_score", "surf_rating", "confidence", "summary_reasons"]] = scored.apply(score_row_factory(spot), axis=1)
    return scored


def get_today_df(df: pd.DataFrame) -> pd.DataFrame:
    now = datetime.now()
    today_df = df[df["time"].dt.date == now.date()].copy()
    return today_df if not today_df.empty else df.head(24).copy()


def get_next_best_day_df(df: pd.DataFrame) -> pd.DataFrame:
    day_scores = []
    today = datetime.now().date()
    for day, group in df.groupby(df["time"].dt.date):
        if not group.empty:
            day_scores.append((day, float(group["surf_score"].max())))
    if not day_scores:
        return df.head(24).copy()
    future_days = [(day, score) for day, score in day_scores if day != today]
    next_best_date = sorted(future_days if future_days else day_scores, key=lambda x: x[1], reverse=True)[0][0]
    return df[df["time"].dt.date == next_best_date].copy()


def annotate_direction_points(ax1, ax2, day_df: pd.DataFrame, y_max: float, include_current_line: bool = False) -> None:
    if day_df.empty:
        return
    label_rows = day_df.iloc[::4].copy()
    if len(label_rows) == 0:
        label_rows = day_df.copy()

    wind_max = max(5.0, float(day_df["wind_speed_10m"].max()) * 1.15 if not day_df["wind_speed_10m"].isna().all() else 5.0)
    ax2.set_ylim(0, wind_max)

    for _, row in label_rows.iterrows():
        swell_txt = deg_to_text(row.get("swell_wave_direction"))
        wind_txt = deg_to_text(row.get("wind_direction_10m"))

        ax1.text(row["time"], row["swell_wave_height"] + max(0.08, y_max * 0.03), f"S:{swell_txt}",
                 ha="center", va="bottom", fontsize=6.3, color="black",
                 bbox=dict(facecolor="white", alpha=0.65, edgecolor="none", pad=0.15), zorder=9)

        wind_y = row["wind_speed_10m"]
        if not pd.isna(wind_y):
            ax2.text(row["time"], wind_y + max(0.4, wind_max * 0.03), f"W:{wind_txt}",
                     ha="center", va="bottom", fontsize=6.3, color="darkgreen",
                     bbox=dict(facecolor="white", alpha=0.65, edgecolor="none", pad=0.15), zorder=9)

    if include_current_line:
        ax1.axvline(datetime.now(), color="red", lw=1.7, label="Current Time")


def base_day_chart(day_df: pd.DataFrame, title: str, include_current_line: bool) -> BytesIO:
    fig, ax1 = plt.subplots(figsize=(10.8, 2.95))
    ax2 = ax1.twinx()

    ax1.plot(day_df["time"], day_df["swell_wave_height"], lw=2.2, color="#1f77b4", label="Swell (m)")
    ax2.plot(day_df["time"], day_df["wind_speed_10m"], lw=1.2, ls="--", color="#2ca02c", alpha=0.75, label="Wind (km/h)")

    y_max = max(1.0, float(day_df["swell_wave_height"].max()) * 1.35 if not day_df["swell_wave_height"].isna().all() else 1.0)
    ax1.set_ylim(0, y_max)

    top = day_df.nlargest(min(3, len(day_df)), "surf_score").sort_values("time")
    for _, row in top.iterrows():
        ax1.scatter(row["time"], row["swell_wave_height"], marker="o", s=34, zorder=10, color="darkblue")
        ax1.annotate(
            f"{row['time'].strftime('%H:%M')}  {row['surf_rating']} {score_out_of_10(row['surf_score'])}",
            (row["time"], row["swell_wave_height"]),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=6.7,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.18", facecolor="white", alpha=0.85),
        )

    annotate_direction_points(ax1, ax2, day_df, y_max, include_current_line=include_current_line)
    ax1.set_title(title, fontweight="bold", fontsize=10.5, pad=6)
    ax1.set_ylabel("Swell", fontsize=7)
    ax2.set_ylabel("Wind", fontsize=7)
    ax1.tick_params(axis="both", labelsize=7)
    ax2.tick_params(axis="y", labelsize=7)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

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
    return base_day_chart(get_today_df(df), f"{location_name} — Today", include_current_line=True)


def generate_next_best_day_chart(df: pd.DataFrame, location_name: str) -> BytesIO:
    day_df = get_next_best_day_df(df)
    day_title = day_df["time"].iloc[0].strftime("%a %d %b")
    return base_day_chart(day_df, f"{location_name} — Next Best Day ({day_title})", include_current_line=False)


def generate_weekly_chart(df: pd.DataFrame, location_name: str) -> BytesIO:
    fig, ax1 = plt.subplots(figsize=(10.8, 3.05))
    ax2 = ax1.twinx()

    ax1.plot(df["time"], df["swell_wave_height"], lw=2.0, color="#1f77b4", label="Swell (m)")
    ax2.plot(df["time"], df["wind_speed_10m"], lw=1.1, ls="--", color="#2ca02c", alpha=0.7, label="Wind (km/h)")

    y_max = max(1.0, float(df["swell_wave_height"].max()) * 1.30 if not df["swell_wave_height"].isna().all() else 1.0)
    ax1.set_ylim(0, y_max)

    wind_max = max(5.0, float(df["wind_speed_10m"].max()) * 1.15 if not df["wind_speed_10m"].isna().all() else 5.0)
    ax2.set_ylim(0, wind_max)

    for _, group in df.groupby(df["time"].dt.date):
        if group.empty:
            continue
        best = group.loc[group["surf_score"].idxmax()]
        ax1.scatter(best["time"], best["swell_wave_height"], marker="x", s=42, zorder=8, color="darkred")
        ax1.annotate(
            f"{best['time'].strftime('%a %H:%M')}\n{best['surf_rating']} {score_out_of_10(best['surf_score'])}\nS:{deg_to_text(best['swell_wave_direction'])} W:{deg_to_text(best['wind_direction_10m'])}",
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
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))

    lines = ax1.get_lines() + ax2.get_lines()
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="upper left", fontsize=6.7, framealpha=0.9)

    plt.tight_layout(pad=0.8)
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=145, bbox_inches="tight")
    plt.close()
    buf.seek(0)
    return buf


def build_pdf(df: pd.DataFrame, diagnostics: dict, spot: dict, output_dir: str | Path) -> str:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    location_name = spot["location_name"]
    safe_name = "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in location_name.replace(" ", "_"))
    filename = f"{safe_name}_Surf_Forecast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    ppath = output_path / filename

    doc = SimpleDocTemplate(
        str(ppath),
        pagesize=A4,
        leftMargin=0.65 * cm,
        rightMargin=0.65 * cm,
        topMargin=0.45 * cm,
        bottomMargin=0.45 * cm,
    )

    styles = getSampleStyleSheet()
    compact = ParagraphStyle("compact", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=9.6, spaceAfter=0)
    compact_bold = ParagraphStyle("compact_bold", parent=compact, fontName="Helvetica-Bold")

    today_df = get_today_df(df)
    next_best_df = get_next_best_day_df(df)
    best_today = today_df.loc[today_df["surf_score"].idxmax()]
    today_sorted = today_df.sort_values("surf_score", ascending=False).reset_index(drop=True)
    backup_today = today_sorted.iloc[1] if len(today_sorted) > 1 else best_today
    next_best = next_best_df.loc[next_best_df["surf_score"].idxmax()]

    daily_rows = [
        [Paragraph("Location", compact_bold), Paragraph(location_name, compact)],
        [Paragraph("Best window today", compact_bold), Paragraph(f"{best_today['time'].strftime('%H:%M')} — {best_today['surf_rating']} ({score_out_of_10(best_today['surf_score'])})", compact)],
        [Paragraph("Backup window", compact_bold), Paragraph(f"{backup_today['time'].strftime('%H:%M')} — {backup_today['surf_rating']} ({score_out_of_10(backup_today['surf_score'])})", compact)],
        [Paragraph("Next best day", compact_bold), Paragraph(f"{next_best['time'].strftime('%a %d %b %H:%M')} — {next_best['surf_rating']} ({score_out_of_10(next_best['surf_score'])})", compact)],
        [Paragraph("Wind", compact_bold), Paragraph(f"{safe_float_text(best_today['wind_speed_10m'], '.0f', ' km/h')} {deg_to_text(best_today['wind_direction_10m'])}", compact)],
        [Paragraph("Swell", compact_bold), Paragraph(f"{safe_float_text(best_today['swell_wave_height'], '.1f', ' m')} {deg_to_text(best_today['swell_wave_direction'])}", compact)],
        [Paragraph("Wave period", compact_bold), Paragraph(f"{safe_float_text(best_today['wave_period'], '.0f', ' s')}", compact)],
        [Paragraph("Confidence", compact_bold), Paragraph(f"{int(best_today['confidence'] * 100)}%", compact)],
        [Paragraph("Why", compact_bold), Paragraph(best_today["summary_reasons"], compact)],
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
        Paragraph(f"<b>{location_name.upper()} SURF REPORT</b>", styles["Title"]),
        Spacer(1, 0.08 * cm),
        t1,
        Spacer(1, 0.10 * cm),
        Image(generate_daily_chart(df, location_name), 18.6 * cm, 5.00 * cm),
        Spacer(1, 0.05 * cm),
        Image(generate_next_best_day_chart(df, location_name), 18.6 * cm, 5.00 * cm),
        Spacer(1, 0.05 * cm),
        Image(generate_weekly_chart(df, location_name), 18.6 * cm, 5.20 * cm),
        Spacer(1, 0.03 * cm),
        Paragraph("<font size=7.0><b>Guide:</b> Good 8–10/10 | Fair 6–7/10 | Marginal 4–5/10 | Poor 0–3/10</font>", styles["Normal"]),
    ]

    doc.build(story)
    return str(ppath)


def generate_report(target, data, output_dir, logger=print):
    display_name = None
    if isinstance(data, dict):
        display_name = data.get("display_name")
    search_name = display_name or target

    _log(logger, f"[SURF] Building spot profile for {search_name}")
    spot = build_profile(search_name)
    save_profile(spot, PROFILE_PATH)
    _log(logger, f"[SURF] Spot profile saved to {PROFILE_PATH}")

    lat = float(spot["lat"])
    lon = float(spot["lon"])

    _log(logger, f"[SURF] Fetching marine and weather data for {spot['location_name']}")
    df, diagnostics = build_dataset(lat, lon)

    _log(logger, "[SURF] Scoring surf windows")
    df = find_best_windows(df, spot)

    _log(logger, "[SURF] Building PDF")
    pdf_path = build_pdf(df, diagnostics, spot, output_dir)

    best = df.loc[df["surf_score"].idxmax()]
    _log(logger, f"[SURF] Best window: {best['time'].strftime('%Y-%m-%d %H:%M')} — {best['surf_rating']} ({score_out_of_10(best['surf_score'])})")
    _log(logger, f"[SURF] PDF saved: {pdf_path}")

    return pdf_path
