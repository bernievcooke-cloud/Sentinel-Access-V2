#!/usr/bin/env python3
from __future__ import annotations

import os
import platform
from datetime import datetime, timedelta, time as dtime
from io import BytesIO
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import requests

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet


DEFAULT_TZ = "Australia/Melbourne"

LOCAL_DIR = (
    r"C:\RuralAI\OUTPUT\SKY"
    if platform.system() == "Windows"
    else os.path.join(os.path.expanduser("~"), "Documents", "Sky Reports")
)
os.makedirs(LOCAL_DIR, exist_ok=True)


def make_safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("_", "-") else "_" for c in name.replace(" ", "_"))


def now_local() -> datetime:
    return datetime.now(ZoneInfo(DEFAULT_TZ))


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_get_json(url: str, timeout: int = 15) -> dict:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _parse_local_times(series: pd.Series, tz_name: str) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)

    if getattr(dt.dt, "tz", None) is None:
        return dt.dt.tz_localize(tz).dt.tz_localize(None)
    return dt.dt.tz_convert(tz).dt.tz_localize(None)


def fetch_sky_data(lat: float, lon: float, logger: Callable[[str], None] = print):
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&hourly=cloud_cover,visibility,precipitation,wind_speed_10m,weather_code"
            "&daily=sunrise,sunset"
            "&timezone=Australia/Melbourne"
            "&forecast_days=7"
        )

        j = _safe_get_json(url)

        hourly = j.get("hourly") or {}
        daily = j.get("daily") or {}

        if "time" not in hourly:
            logger("SKY worker: hourly data missing 'time'.")
            return None, None, DEFAULT_TZ

        tz_name = j.get("timezone") or DEFAULT_TZ

        h_df = pd.DataFrame(hourly)
        h_df["time"] = _parse_local_times(h_df["time"], tz_name)
        h_df = h_df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)

        for col in ["cloud_cover", "visibility", "precipitation", "wind_speed_10m", "weather_code"]:
            if col not in h_df.columns:
                h_df[col] = np.nan
            h_df[col] = pd.to_numeric(h_df[col], errors="coerce")

        d_df = pd.DataFrame(daily) if daily and "time" in daily else pd.DataFrame()
        if not d_df.empty:
            d_df["time"] = _parse_local_times(d_df["time"], tz_name)
            if "sunrise" in d_df.columns:
                d_df["sunrise"] = _parse_local_times(d_df["sunrise"], tz_name)
            if "sunset" in d_df.columns:
                d_df["sunset"] = _parse_local_times(d_df["sunset"], tz_name)

        return h_df, d_df, tz_name

    except Exception as e:
        logger(f"SKY worker fetch failed: {e}")
        return None, None, DEFAULT_TZ


def calculate_day_score(df: pd.DataFrame) -> pd.Series:
    cloud_component = (100 - df["cloud_cover"].fillna(100)).clip(lower=0, upper=100) * 0.40
    vis_component = (df["visibility"].fillna(0) / 20000.0).clip(lower=0, upper=1) * 30.0
    rain_component = (1 - (df["precipitation"].fillna(0) / 3.0).clip(lower=0, upper=1)) * 20.0
    wind_component = (1 - (df["wind_speed_10m"].fillna(0) / 40.0).clip(lower=0, upper=1)) * 10.0
    return (cloud_component + vis_component + rain_component + wind_component).clip(lower=0, upper=100)


def calculate_night_score(df: pd.DataFrame) -> pd.Series:
    cloud_component = (100 - df["cloud_cover"].fillna(100)).clip(lower=0, upper=100) * 0.55
    vis_component = (df["visibility"].fillna(0) / 20000.0).clip(lower=0, upper=1) * 20.0
    rain_component = (1 - (df["precipitation"].fillna(0) / 3.0).clip(lower=0, upper=1)) * 15.0
    wind_component = (1 - (df["wind_speed_10m"].fillna(0) / 40.0).clip(lower=0, upper=1)) * 10.0
    return (cloud_component + vis_component + rain_component + wind_component).clip(lower=0, upper=100)


def _moon_phase_info(dt_obj) -> dict[str, str]:
    if isinstance(dt_obj, pd.Timestamp):
        dt_obj = dt_obj.to_pydatetime()

    known_new_moon = datetime(2000, 1, 6, 18, 14)
    synodic_month = 29.53058867

    days_since = (dt_obj - known_new_moon).total_seconds() / 86400.0
    lunar_age = days_since % synodic_month
    phase_index = int((lunar_age / synodic_month) * 8 + 0.5) % 8

    phases = [
        {"icon": "NM", "name": "New Moon"},
        {"icon": "WC", "name": "Waxing Crescent"},
        {"icon": "FQ", "name": "First Quarter"},
        {"icon": "WG", "name": "Waxing Gibbous"},
        {"icon": "FM", "name": "Full Moon"},
        {"icon": "WNG", "name": "Waning Gibbous"},
        {"icon": "LQ", "name": "Last Quarter"},
        {"icon": "WNC", "name": "Waning Crescent"},
    ]
    return phases[phase_index]


def _day_window_for_date(day_date):
    start = datetime.combine(day_date, dtime(6, 0))
    end = datetime.combine(day_date, dtime(18, 0))
    return start, end


def _night_window_for_date(day_date):
    start = datetime.combine(day_date, dtime(18, 0))
    end = datetime.combine(day_date + timedelta(days=1), dtime(6, 0))
    return start, end


def _subset_between(df: pd.DataFrame, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
    out = df[(df["time"] >= start_dt) & (df["time"] < end_dt)].copy()
    return out.reset_index(drop=True)


def _daily_window_scores(df: pd.DataFrame):
    dates = sorted(df["time"].dt.date.unique())
    rows = []

    for d in dates:
        ds, de = _day_window_for_date(d)
        ns, ne = _night_window_for_date(d)

        day_df = _subset_between(df, ds, de)
        night_df = _subset_between(df, ns, ne)

        day_score = float(day_df["day_score"].mean()) if not day_df.empty else np.nan
        night_score = float(night_df["night_score"].mean()) if not night_df.empty else np.nan

        moon = _moon_phase_info(datetime.combine(d, dtime(21, 0)))

        rows.append(
            {
                "date": d,
                "day_score": day_score,
                "night_score": night_score,
                "moon_icon": moon["icon"],
                "moon_name": moon["name"],
            }
        )

    return pd.DataFrame(rows)


def _plot_condition_panel(
    ax,
    dfx: pd.DataFrame,
    title: str,
    score_col: str,
    best_label: str,
    score_color: str,
    moon_text: str | None = None,
):
    if moon_text:
        ax.set_title(f"{title}   |   Moon: {moon_text}", fontweight="bold", fontsize=10)
    else:
        ax.set_title(title, fontweight="bold", fontsize=10)

    if dfx.empty:
        ax.text(0.5, 0.5, "No data available.", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return

    ax.plot(dfx["time"], dfx[score_col], lw=2.0, color=score_color, label="Photography Score")
    ax.set_ylabel("Score / 100", fontweight="bold", fontsize=8, color=score_color)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.grid(True, alpha=0.18)
    ax.tick_params(axis="x", labelsize=8)
    ax.tick_params(axis="y", labelsize=8, colors=score_color)

    ax2 = ax.twinx()
    ax2.plot(dfx["time"], dfx["cloud_cover"], lw=1.8, ls="--", color="red", label="Cloud Cover %")
    ax2.set_ylabel("Cloud Cover %", fontweight="bold", fontsize=8, color="red")
    ax2.set_ylim(0, 100)
    ax2.set_yticks([0, 25, 50, 75, 100])
    ax2.tick_params(axis="y", labelsize=8, colors="red")

    best_idx = dfx[score_col].idxmax()
    best_time = dfx.loc[best_idx, "time"]
    best_score = float(dfx.loc[best_idx, score_col])
    best_score_10 = best_score / 10.0

    ax.scatter(
        [best_time],
        [best_score],
        marker="x",
        s=110,
        color="red",
        linewidths=2.0,
        zorder=6,
        label=best_label,
    )
    ax.annotate(
        f"{best_time.strftime('%H:%M')}\n{best_score_10:.1f}/10",
        (best_time, best_score),
        textcoords="offset points",
        xytext=(0, 8),
        ha="center",
        fontsize=7,
        fontweight="bold",
    )

    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[6, 9, 12, 15, 18, 21, 0, 3]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=7)


def generate_visuals(h_df: pd.DataFrame, location_name: str) -> tuple[BytesIO, pd.DataFrame]:
    df = h_df.copy()
    df["day_score"] = calculate_day_score(df)
    df["night_score"] = calculate_night_score(df)

    now_dt = now_local().replace(tzinfo=None)
    today_date = now_dt.date()

    today_day_start, today_day_end = _day_window_for_date(today_date)
    today_night_start, today_night_end = _night_window_for_date(today_date)

    today_day_df = _subset_between(df, today_day_start, today_day_end)
    today_night_df = _subset_between(df, today_night_start, today_night_end)

    daily_scores = _daily_window_scores(df)

    future_day_scores = daily_scores[daily_scores["date"] != today_date].copy()
    if not future_day_scores.empty and future_day_scores["day_score"].notna().any():
        next_best_day_date = future_day_scores.sort_values("day_score", ascending=False).iloc[0]["date"]
    else:
        next_best_day_date = today_date

    best_day_start, best_day_end = _day_window_for_date(next_best_day_date)
    best_night_start, best_night_end = _night_window_for_date(next_best_day_date)

    best_day_df = _subset_between(df, best_day_start, best_day_end)
    best_night_df = _subset_between(df, best_night_start, best_night_end)

    today_moon = _moon_phase_info(datetime.combine(today_date, dtime(21, 0)))
    best_night_moon = _moon_phase_info(datetime.combine(next_best_day_date, dtime(21, 0)))

    fig, axes = plt.subplots(6, 1, figsize=(9.0, 14.2))
    fig.subplots_adjust(top=0.97, bottom=0.06, left=0.08, right=0.90, hspace=0.55)

    _plot_condition_panel(
        axes[0],
        today_day_df,
        f"1A) TODAY — DAY PHOTOGRAPHY (6AM–6PM) — {location_name}",
        "day_score",
        "Best Daytime Window",
        score_color="blue",
        moon_text=None,
    )
    _plot_condition_panel(
        axes[1],
        today_night_df,
        f"1B) TODAY — NIGHT PHOTOGRAPHY (6PM–6AM) — {location_name}",
        "night_score",
        "Best Night Window",
        score_color="green",
        moon_text=f"{today_moon['icon']} {today_moon['name']}",
    )

    _plot_condition_panel(
        axes[2],
        best_day_df,
        f"2A) NEXT BEST DAY — DAY PHOTOGRAPHY ({next_best_day_date})",
        "day_score",
        "Best Daytime Window",
        score_color="blue",
        moon_text=None,
    )
    _plot_condition_panel(
        axes[3],
        best_night_df,
        f"2B) NEXT BEST DAY — NIGHT PHOTOGRAPHY ({next_best_day_date})",
        "night_score",
        "Best Night Window",
        score_color="green",
        moon_text=f"{best_night_moon['icon']} {best_night_moon['name']}",
    )

    ax5 = axes[4]
    ax5.set_title("3A) WEEKLY DAY PHOTOGRAPHY TREND (6AM–6PM)", fontweight="bold", fontsize=10)
    x_positions = np.arange(len(daily_scores))
    ax5.bar(
        x_positions,
        daily_scores["day_score"].fillna(0),
        color="blue",
        alpha=0.75,
        width=0.55,
        label="Day Score",
    )
    if not daily_scores.empty and daily_scores["day_score"].notna().any():
        best_row = daily_scores.sort_values("day_score", ascending=False).iloc[0]
        best_i = daily_scores.index[daily_scores["date"] == best_row["date"]][0]
        ax5.scatter(best_i, best_row["day_score"], marker="x", s=110, color="red", linewidths=2.0, zorder=6)
        ax5.annotate(
            f"{best_row['day_score'] / 10.0:.1f}/10",
            (best_i, best_row["day_score"]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=7,
            fontweight="bold",
        )
    ax5.set_xticks(x_positions)
    ax5.set_xticklabels(daily_scores["date"].astype(str), fontsize=8)
    ax5.set_ylabel("Score / 100", fontsize=8, fontweight="bold", color="blue")
    ax5.set_ylim(0, 100)
    ax5.set_yticks([0, 25, 50, 75, 100])
    ax5.grid(True, axis="y", alpha=0.18)
    ax5.tick_params(axis="y", labelsize=8, colors="blue")

    ax6 = axes[5]
    ax6.set_title("3B) WEEKLY NIGHT PHOTOGRAPHY TREND (6PM–6AM)", fontweight="bold", fontsize=10)
    ax6.bar(
        x_positions,
        daily_scores["night_score"].fillna(0),
        color="green",
        alpha=0.75,
        width=0.55,
        label="Night Score",
    )
    if not daily_scores.empty and daily_scores["night_score"].notna().any():
        best_row_n = daily_scores.sort_values("night_score", ascending=False).iloc[0]
        best_i_n = daily_scores.index[daily_scores["date"] == best_row_n["date"]][0]
        ax6.scatter(best_i_n, best_row_n["night_score"], marker="x", s=110, color="red", linewidths=2.0, zorder=6)
        ax6.annotate(
            f"{best_row_n['night_score'] / 10.0:.1f}/10",
            (best_i_n, best_row_n["night_score"]),
            textcoords="offset points",
            xytext=(0, 8),
            ha="center",
            fontsize=7,
            fontweight="bold",
        )

    for i, row in daily_scores.iterrows():
        if pd.notna(row["night_score"]):
            ax6.annotate(
                row["moon_icon"],
                (i, float(row["night_score"])),
                textcoords="offset points",
                xytext=(0, 16),
                ha="center",
                fontsize=8,
                fontweight="bold",
            )

    ax6.set_xticks(x_positions)
    ax6.set_xticklabels(daily_scores["date"].astype(str), fontsize=8)
    ax6.set_ylabel("Score / 100", fontsize=8, fontweight="bold", color="green")
    ax6.set_ylim(0, 100)
    ax6.set_yticks([0, 25, 50, 75, 100])
    ax6.grid(True, axis="y", alpha=0.18)
    ax6.tick_params(axis="y", labelsize=8, colors="green")

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=140, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)

    return buf, daily_scores


def _build_sky_pdf(
    location_name: str,
    lat: float,
    lon: float,
    output_dir: str,
    logger: Callable[[str], None] = print,
):
    h_df, d_df, tz_name = fetch_sky_data(lat, lon, logger=logger)
    if h_df is None or h_df.empty:
        logger("SKY worker error: No sky forecast data returned.")
        return None

    img_buffer, daily_scores = generate_visuals(h_df, location_name)

    best_day_text = "N/A"
    best_night_text = "N/A"

    if not daily_scores.empty:
        if daily_scores["day_score"].notna().any():
            best_day_row = daily_scores.sort_values("day_score", ascending=False).iloc[0]
            best_day_text = f"{best_day_row['date']} ({best_day_row['day_score'] / 10.0:.1f}/10)"
        if daily_scores["night_score"].notna().any():
            best_night_row = daily_scores.sort_values("night_score", ascending=False).iloc[0]
            best_night_text = (
                f"{best_night_row['date']} "
                f"({best_night_row['night_score'] / 10.0:.1f}/10, "
                f"{best_night_row['moon_icon']} {best_night_row['moon_name']})"
            )

    tonight_moon = _moon_phase_info(datetime.combine(now_local().date(), dtime(21, 0)))
    tonight_moon_text = f"{tonight_moon['icon']} {tonight_moon['name']}"

    os.makedirs(output_dir, exist_ok=True)
    filename = f"{make_safe_name(location_name)}_Sky_Report_{now_local().strftime('%Y%m%d_%H%M%S')}.pdf"
    ppath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(ppath, pagesize=A4, topMargin=0.55 * cm, bottomMargin=0.55 * cm)
    styles = getSampleStyleSheet()

    story = [
        Paragraph(f"<b>SKY REPORT: {location_name}</b>", styles["Title"]),
        Spacer(1, 0.12 * cm),
        Paragraph(
            f"<b>Best Day Photography:</b> {best_day_text} &nbsp;&nbsp; "
            f"<b>Best Night Photography:</b> {best_night_text}",
            styles["Normal"],
        ),
        Spacer(1, 0.08 * cm),
        Paragraph(
            f"<b>Tonight's Moon:</b> {tonight_moon_text}",
            styles["Normal"],
        ),
        Spacer(1, 0.18 * cm),
        Image(img_buffer, width=18.3 * cm, height=25.2 * cm),
    ]

    doc.build(story)

    if os.path.exists(ppath) and os.path.getsize(ppath) > 1000:
        logger(f"SUCCESS: Sky PDF created at {ppath}")
        return ppath

    logger("ERROR: Sky PDF not written or too small.")
    return None


def generate_report(
    location_name: str,
    lat: float,
    lon: float,
    logger: Callable[[str], None] = print,
):
    """
    App-friendly worker signature.
    Matches app.py:
        generate_report(location_name=..., lat=..., lon=...)
    """
    return _build_sky_pdf(
        location_name=location_name,
        lat=float(lat),
        lon=float(lon),
        output_dir=LOCAL_DIR,
        logger=logger,
    )
