#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet


def fetch_sky_data(lat: float, lon: float):
    # Mock data (kept as your structure)
    data = []
    base_time = datetime.now()
    for i in range(168):
        time_point = base_time + timedelta(hours=i)
        data.append({"time": time_point, "cloud_cover": 50 + 50 * (i % 24 / 24)})
    return data


def calculate_sky_score(df: pd.DataFrame) -> pd.Series:
    return 100 - df["cloud_cover"]


def generate_visuals(data_list):
    df = pd.DataFrame(data_list)
    df["time"] = pd.to_datetime(df["time"])
    df["score"] = calculate_sky_score(df)

    fig = plt.figure(figsize=(10, 12))

    ax1 = fig.add_subplot(3, 1, 1)
    ax1.plot(df["time"], df["cloud_cover"], label="Cloud Cover (%)")
    ax1.fill_between(df["time"], df["cloud_cover"], 100, alpha=0.3)

    best_idx = df["score"].idxmax()
    best_time = df.loc[best_idx, "time"]
    ax1.scatter([best_time], [df.loc[best_idx, "cloud_cover"]], marker="x", s=100, label="Best Viewing")
    ax1.set_title(f"Today's Sky - Best Viewing: {best_time.strftime('%H:%M')}")
    ax1.legend()

    ax2 = fig.add_subplot(3, 1, 2)
    daily_scores = df.groupby(df["time"].dt.date)["score"].mean()
    next_best_day = daily_scores.idxmax()
    ax2.bar(daily_scores.index.astype(str), daily_scores.values)
    ax2.set_title(f"Next Best Viewing Day: {next_best_day}")

    ax3 = fig.add_subplot(3, 1, 3)
    weekly_clouds = df.groupby(df["time"].dt.date)["cloud_cover"].min()
    ax3.plot(weekly_clouds.index.astype(str), weekly_clouds.values, marker="o")
    ax3.set_title("7-Day Minimum Cloud Trend")

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_report(target: str, data: Any, output_dir: str, logger: Callable[[str], None] = print):
    """
    Standardized signature: (target, data, output_dir, logger=...)
    data: dict or (lat, lon)
    Returns PDF path or None
    """
    try:
        if isinstance(data, dict):
            lat = float(data.get("latitude", data.get("lat")))
            lon = float(data.get("longitude", data.get("lon")))
        elif isinstance(data, (tuple, list)) and len(data) >= 2:
            lat, lon = float(data[0]), float(data[1])
        else:
            raise ValueError("Unexpected data format for sky_worker (need dict or [lat, lon]).")

        logger(f"Sky worker: target={target} lat={lat} lon={lon}")

        sky_data = fetch_sky_data(lat, lon)
        img_buffer = generate_visuals(sky_data)

        os.makedirs(output_dir, exist_ok=True)
        filename = f"Sky_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ppath = os.path.join(output_dir, filename)

        doc = SimpleDocTemplate(ppath, pagesize=A4, topMargin=0.7 * cm, bottomMargin=0.7 * cm)
        styles = getSampleStyleSheet()

        story = [
            Paragraph(f"<b>SKY REPORT: {target}</b>", styles["Title"]),
            Spacer(1, 0.5 * cm),
            Image(img_buffer, width=18 * cm, height=23 * cm),
        ]

        doc.build(story)

        if os.path.exists(ppath) and os.path.getsize(ppath) > 1000:
            logger(f"SUCCESS: Sky PDF created at {ppath}")
            return ppath
        logger("ERROR: Sky PDF not written or too small.")
        return None

    except Exception as e:
        logger(f"SKY worker error: {e}")
        return None