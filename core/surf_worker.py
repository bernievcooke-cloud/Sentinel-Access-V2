#!/usr/bin/env python3
from __future__ import annotations

import io
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
import requests
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm


# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def deg_to_compass(deg):
    if deg is None or (isinstance(deg, float) and np.isnan(deg)):
        return "N/A"
    dirs = [
        "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
        "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
    ]
    idx = int((deg + 11.25) / 22.5) % 16
    return dirs[idx]


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _extract_lat_lon(data: Any) -> tuple[Optional[float], Optional[float]]:
    """
    Accepts:
      - list/tuple [lat, lon, ...]
      - dict with lat/lon or latitude/longitude/lng keys
      - nested dicts: coords/coordinates/location/geo/position
    """
    if data is None:
        return None, None

    if isinstance(data, (list, tuple)) and len(data) >= 2:
        return _to_float(data[0]), _to_float(data[1])

    if not isinstance(data, dict):
        return None, None

    candidates_lat = ["lat", "LAT", "latitude", "Latitude", "y", "Y"]
    candidates_lon = ["lon", "LON", "lng", "LNG", "longitude", "Longitude", "x", "X"]

    lat = None
    lon = None

    for k in candidates_lat:
        if k in data:
            lat = _to_float(data.get(k))
            if lat is not None:
                break

    for k in candidates_lon:
        if k in data:
            lon = _to_float(data.get(k))
            if lon is not None:
                break

    if lat is None or lon is None:
        for nest_key in ["coords", "coord", "coordinates", "location", "geo", "position"]:
            nested = data.get(nest_key)
            if isinstance(nested, dict):
                if lat is None:
                    for k in candidates_lat:
                        if k in nested:
                            lat = _to_float(nested.get(k))
                            if lat is not None:
                                break
                if lon is None:
                    for k in candidates_lon:
                        if k in nested:
                            lon = _to_float(nested.get(k))
                            if lon is not None:
                                break

    return lat, lon


def _in_dir_range(deg: float, start: float, end: float) -> bool:
    """
    True if wind direction in [start, end] with wrap-around support (e.g. 300..60).
    """
    if deg is None or (isinstance(deg, float) and np.isnan(deg)):
        return False
    deg = float(deg) % 360
    start = float(start) % 360
    end = float(end) % 360
    if start <= end:
        return start <= deg <= end
    return deg >= start or deg <= end


def _default_profile() -> dict:
    return {
        "offshore_dir_ranges": [[290, 70]],
        "max_wind_kmh": 28,
        "swell_min": 0.9,
        "swell_max": 3.8,
        "tide_min": 1.1,
    }


def is_surf_window(row: pd.Series, target: str, profile: dict) -> Optional[str]:
    wdir = row.get("wind_direction_10m")
    ws = row.get("wind_speed_10m")
    swell = row.get("swell_wave_height")
    tide = row.get("tide_height")

    if pd.isna(wdir) or pd.isna(ws) or pd.isna(swell) or pd.isna(tide):
        return None

    wdir = float(wdir)
    ws = float(ws)
    swell = float(swell)
    tide = float(tide)

    cfg = _default_profile()
    if isinstance(profile, dict):
        cfg.update(profile)

    ranges = cfg.get("offshore_dir_ranges", [[290, 70]])
    ranges = [(float(a), float(b)) for a, b in ranges]

    max_wind = float(cfg.get("max_wind_kmh", 28))
    swell_min = float(cfg.get("swell_min", 0.9))
    swell_max = float(cfg.get("swell_max", 3.8))
    tide_min = float(cfg.get("tide_min", 1.1))

    ok_dir = any(_in_dir_range(wdir, a, b) for (a, b) in ranges)
    ok_wind = ws <= max_wind
    ok_swell = swell_min <= swell <= swell_max
    ok_tide = tide >= tide_min

    if ok_dir and ok_wind and ok_swell and ok_tide:
        return target
    return None


def _safe_hourly_df(url: str, timeout: int = 15) -> pd.DataFrame:
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    j = r.json()
    hourly = j.get("hourly")
    if not hourly or "time" not in hourly:
        return pd.DataFrame()
    df = pd.DataFrame(hourly)
    df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
    return df


def _build_surf_score(df: pd.DataFrame) -> pd.Series:
    dfx = df.copy()
    dfx["date"] = dfx["time"].dt.date
    dfx["score"] = 0.0

    dfx.loc[dfx["active_x"].notna(), "score"] += 3.0

    swell = dfx["swell_wave_height"].clip(lower=0)
    dfx["score"] += 1.2 * (1.0 - (swell - 1.6).abs() / 2.5).clip(lower=0)

    ws = dfx["wind_speed_10m"].fillna(0)
    dfx["score"] -= 0.06 * (ws - 25).clip(lower=0)

    return dfx.groupby("date")["score"].sum().sort_values(ascending=False)


def _score_to_rating(score: float, best_score: float) -> int:
    if best_score <= 0:
        return 0
    rating = round((score / best_score) * 10)
    return max(0, min(10, int(rating)))


def _get_day_window(df: pd.DataFrame, day_date):
    start = datetime.combine(day_date, datetime.min.time())
    end = start + timedelta(days=1)
    out = df[(df["time"] >= start) & (df["time"] < end)].copy()
    if out.empty:
        return df.iloc[:24].copy()
    return out


def _format_hour_axis(ax):
    ax.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 3, 6, 9, 12, 15, 18, 21]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.tick_params(axis="x", rotation=0)


def _shade_surf_windows(ax, dfx: pd.DataFrame):
    good = dfx[dfx["active_x"].notna()].copy()
    if good.empty:
        return

    good = good.sort_values("time")
    times = good["time"].tolist()
    block_start = times[0]
    prev = times[0]

    for t in times[1:]:
        if (t - prev) > timedelta(hours=1.5):
            ax.axvspan(block_start, prev + timedelta(hours=1), alpha=0.18)
            block_start = t
        prev = t

    ax.axvspan(block_start, prev + timedelta(hours=1), alpha=0.18)


def _annotate_wind_dirs(ax_wind, dfx: pd.DataFrame, step=3):
    for _, row in dfx.iloc[::step].iterrows():
        compass = deg_to_compass(row.get("wind_direction_10m"))
        ws = row.get("wind_speed_10m", np.nan)
        if pd.notna(ws):
            ax_wind.annotate(
                compass,
                (row["time"], ws),
                xytext=(0, 7),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                fontweight="bold",
            )


def _best_point_for_day(dfx: pd.DataFrame) -> Optional[pd.Series]:
    if dfx.empty:
        return None

    work = dfx.copy()
    work["point_score"] = 0.0
    work.loc[work["active_x"].notna(), "point_score"] += 5.0

    swell = work["swell_wave_height"].fillna(0)
    work["point_score"] += 2.0 * (1.0 - (swell - 1.6).abs() / 2.5).clip(lower=0)

    wind = work["wind_speed_10m"].fillna(0)
    work["point_score"] -= 0.08 * (wind - 20).clip(lower=0)

    tide = work["tide_height"].fillna(0)
    work["point_score"] += 0.6 * (tide >= 1.1).astype(float)

    if work.empty:
        return None

    idx = work["point_score"].idxmax()
    return work.loc[idx]


def _plot_day_panel(ax, dfx: pd.DataFrame, title: str, mark_best: bool = False):
    ax.set_title(title, fontweight="bold")

    if dfx.empty:
        ax.text(0.5, 0.5, "No data available for this day window.", ha="center", va="center", transform=ax.transAxes)
        return

    ax.plot(dfx["time"], dfx["swell_wave_height"], lw=2.4, color="red", label="Swell (m)")
    ax.set_ylabel("Swell (m)", color="red")
    ax.grid(True, alpha=0.2)
    _format_hour_axis(ax)

    ax_wind = ax.twinx()
    ax_wind.plot(dfx["time"], dfx["wind_speed_10m"], lw=1.8, ls="--", label="Wind (km/h)")
    ax_wind.set_ylabel("Wind (km/h)")

    ax_tide = ax.twinx()
    ax_tide.spines["right"].set_position(("axes", 1.12))
    ax_tide.plot(dfx["time"], dfx["tide_height"], lw=1.4, ls=":", color="green", label="Tide (m)")
    ax_tide.set_ylabel("Tide (m)", color="green")

    _shade_surf_windows(ax, dfx)

    good = dfx[dfx["active_x"].notna()]
    if not good.empty:
        ax.scatter(good["time"], good["swell_wave_height"], s=30, label="Surf window")

        step = max(1, len(good) // 6)
        for _, r in good.iloc[::step].iterrows():
            ax.annotate(
                str(r["active_x"]),
                (r["time"], r["swell_wave_height"]),
                textcoords="offset points",
                xytext=(0, 8),
                ha="center",
                fontsize=8,
            )

    if mark_best:
        best_point = _best_point_for_day(dfx)
        if best_point is not None and pd.notna(best_point["swell_wave_height"]):
            ax.scatter(
                [best_point["time"]],
                [best_point["swell_wave_height"]],
                color="red",
                marker="x",
                s=130,
                linewidths=2.2,
                zorder=6,
                label="Best point",
            )
            ax.annotate(
                "Best",
                (best_point["time"], best_point["swell_wave_height"]),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=8,
                fontweight="bold",
                color="red",
            )

    _annotate_wind_dirs(ax_wind, dfx, step=3)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax_wind.get_legend_handles_labels()
    h3, l3 = ax_tide.get_legend_handles_labels()
    ax.legend(h1 + h2 + h3, l1 + l2 + l3, loc="upper left", fontsize=8)


# -------------------------------------------------
# MAIN WORKER
# -------------------------------------------------
def generate_report(
    target: str | None = None,
    data: Any = None,
    output_dir: str | None = None,
    logger: Callable[[str], None] = print,
    *,
    location_name: str | None = None,
    coords: Any = None,
) -> str | None:
    if not callable(logger):
        logger = print

    try:
        name = (location_name or target or "").strip() or "Location"

        if not output_dir:
            output_dir = str(os.path.join(os.getcwd(), "outputs"))
        os.makedirs(output_dir, exist_ok=True)

        src = coords if coords is not None else data
        lat, lon = _extract_lat_lon(src)
        if lat is None or lon is None:
            logger(f"CRITICAL: Surf worker could not parse lat/lon for target={name}")
            return None

        profile = {}
        if isinstance(data, (list, tuple)) and len(data) >= 3 and isinstance(data[2], dict):
            profile = data[2]
        elif isinstance(src, dict) and isinstance(src.get("surf_profile"), dict):
            profile = src["surf_profile"]

        logger(f"Surf worker: target={name} lat={float(lat)} lon={float(lon)}")
        logger("Surf worker: using surf_profile from locations.json" if profile else "Surf worker: using default surf_profile")

        marine_url = (
            "https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={float(lat)}&longitude={float(lon)}"
            "&hourly=swell_wave_height"
            "&timezone=auto"
        )

        wind_url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={float(lat)}&longitude={float(lon)}"
            "&hourly=wind_speed_10m,wind_direction_10m"
            "&timezone=auto"
        )

        logger("Surf worker: fetching marine hourly…")
        df_m = _safe_hourly_df(marine_url)

        logger("Surf worker: fetching wind hourly…")
        df_w = _safe_hourly_df(wind_url)

        if df_m.empty or df_w.empty:
            logger("CRITICAL: Missing marine or wind data from API.")
            return None

        df = pd.merge(df_m, df_w, on="time", how="inner").sort_values("time").head(168).copy()
        if df.empty:
            logger("CRITICAL: merged dataframe empty.")
            return None

        tide_cycle = 12.4
        df["tide_height"] = 1.35 + 0.85 * np.sin(np.arange(len(df)) * (2 * np.pi / tide_cycle))

        df["active_x"] = df.apply(lambda r: is_surf_window(r, name, profile), axis=1)

        scores = _build_surf_score(df)
        best_day = scores.index[0] if not scores.empty else None
        best_break = name if best_day is not None else "None"
        top_days = list(scores.head(3).index) if not scores.empty else []

        best_score_value = float(scores.iloc[0]) if not scores.empty else 0.0
        best_day_rating = _score_to_rating(float(scores.iloc[0]), best_score_value) if not scores.empty else 0
        top_day_ratings = {day: _score_to_rating(float(scores.loc[day]), best_score_value) for day in top_days} if top_days else {}

        fig = plt.figure(figsize=(9.3, 12.4))
        gs = fig.add_gridspec(3, 1, height_ratios=[1.25, 1.25, 1.15], hspace=0.38)

        ax1 = fig.add_subplot(gs[0, 0])
        ax2 = fig.add_subplot(gs[1, 0])
        ax3 = fig.add_subplot(gs[2, 0])

        today_date = datetime.now().date()
        today_df = _get_day_window(df, today_date)
        _plot_day_panel(ax1, today_df, f"1) Today — {name} — Swell / Wind / Tide + Surf Windows", mark_best=False)

        if best_day is None:
            ax2.set_title("2) Next Best Surf Day — No best day detected", fontweight="bold")
            ax2.text(
                0.5, 0.5, "No surf windows detected in the 7-day forecast window.",
                ha="center", va="center", transform=ax2.transAxes
            )
        else:
            best_df = _get_day_window(df, best_day)
            _plot_day_panel(
                ax2,
                best_df,
                f"2) Next Best Surf Day: {best_day} ({name}) — {best_day_rating}/10",
                mark_best=True,
            )

        ax3.set_title(f"3) 7-Day Trend — {name} — Swell / Wind / Tide + Best Days", fontweight="bold")
        ax3.plot(df["time"], df["swell_wave_height"], lw=2.2, color="red", label="Swell (m)")
        ax3.set_ylabel("Swell (m)", color="red")
        ax3.grid(True, alpha=0.2)

        ax3b = ax3.twinx()
        ax3b.plot(df["time"], df["wind_speed_10m"], lw=1.6, ls="--", label="Wind (km/h)")
        ax3b.set_ylabel("Wind (km/h)")

        ax3c = ax3.twinx()
        ax3c.spines["right"].set_position(("axes", 1.12))
        ax3c.plot(df["time"], df["tide_height"], lw=1.3, ls=":", color="green", label="Tide (m)")
        ax3c.set_ylabel("Tide (m)", color="green")

        surf_pts = df[df["active_x"].notna()]
        if not surf_pts.empty:
            ax3.scatter(surf_pts["time"], surf_pts["swell_wave_height"], s=20, label="Surf window")

        for i, day in enumerate(top_days):
            start = datetime.combine(day, datetime.min.time())
            end = start + timedelta(days=1)
            label = "Best surf day" if i == 0 else f"Surf day #{i+1}"
            ax3.axvspan(start, end, alpha=0.12, label=label)

            day_rows = df[df["time"].dt.date == day].copy()
            if not day_rows.empty:
                best_point = _best_point_for_day(day_rows)
                if best_point is not None and pd.notna(best_point["swell_wave_height"]):
                    ax3.scatter(
                        [best_point["time"]],
                        [best_point["swell_wave_height"]],
                        color="red",
                        marker="x",
                        s=130,
                        linewidths=2.2,
                        zorder=6,
                    )

                peak_idx = day_rows["swell_wave_height"].fillna(-999).idxmax()
                peak_row = day_rows.loc[peak_idx]
                rating = top_day_ratings.get(day, 0)

                ax3.annotate(
                    f"{day.strftime('%a %d')}\n{rating}/10",
                    (peak_row["time"], peak_row["swell_wave_height"]),
                    textcoords="offset points",
                    xytext=(0, 10),
                    ha="center",
                    fontsize=8,
                    fontweight="bold",
                )

        ax3.xaxis.set_major_locator(mdates.DayLocator())
        ax3.xaxis.set_major_formatter(mdates.DateFormatter("%a %d"))
        ax3.tick_params(axis="x", rotation=0)

        ax3.text(
            0.01,
            -0.24,
            "Surf day rating is a comparative score out of 10 for this forecast run only, based on surf-window hours, swell fit, and wind.",
            transform=ax3.transAxes,
            fontsize=8,
            ha="left",
            va="top",
        )

        h1, l1 = ax3.get_legend_handles_labels()
        h2, l2 = ax3b.get_legend_handles_labels()
        h3, l3 = ax3c.get_legend_handles_labels()
        ax3.legend(h1 + h2 + h3, l1 + l2 + l3, loc="upper left", fontsize=8)

        img_buf = io.BytesIO()
        fig.savefig(img_buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        img_buf.seek(0)

        filename = f"Surf_{name}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        pdf_path = os.path.join(output_dir, filename)

        styles = getSampleStyleSheet()
        story = [Paragraph(f"SURF REPORT: {name}", styles["Title"]), Spacer(1, 6)]

        if best_day is not None:
            story.append(
                Paragraph(
                    f"<b>Next Best Day:</b> {best_day} &nbsp;&nbsp; <b>Location:</b> {best_break} &nbsp;&nbsp; <b>Rating:</b> {best_day_rating}/10",
                    styles["Heading2"],
                )
            )
        else:
            story.append(Paragraph("<b>Next Best Day:</b> None detected in current forecast window.", styles["Heading2"]))

        if top_days:
            top_days_text = ", ".join(f"{day.strftime('%a %d %b')} ({top_day_ratings.get(day, 0)}/10)" for day in top_days)
            story.append(Spacer(1, 4))
            story.append(
                Paragraph(
                    f"<b>Best Surf Days This Week:</b> {top_days_text}",
                    styles["BodyText"],
                )
            )

        cfg = _default_profile()
        if isinstance(profile, dict):
            cfg.update(profile)
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                f"<b>Surf profile:</b> offshore={cfg.get('offshore_dir_ranges')} "
                f"max_wind={cfg.get('max_wind_kmh')}km/h "
                f"swell={cfg.get('swell_min')}-{cfg.get('swell_max')}m "
                f"tide_min={cfg.get('tide_min')}m",
                styles["BodyText"],
            )
        )

        story.append(Spacer(1, 10))
        story.append(RLImage(img_buf, width=18.0 * cm, height=23.0 * cm))

        doc = SimpleDocTemplate(pdf_path, pagesize=A4, topMargin=0.7 * cm, bottomMargin=0.7 * cm)
        doc.build(story)

        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 1000:
            logger(f"SUCCESS: Report created at {pdf_path}")
            return pdf_path

        logger("ERROR: PDF not written or too small.")
        return None

    except Exception as e:
        logger(f"CRITICAL SYSTEM ERROR: {e}")
        return None
