#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from datetime import datetime
from io import BytesIO
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from core.location_manager import LocationManager


LM = LocationManager()


def _get_lat_lon_from_location(name: str) -> tuple[float, float]:
    payload = LM.get(name)
    if not isinstance(payload, dict):
        raise ValueError(f"Unknown location: {name}")

    lat = payload.get("latitude", payload.get("lat"))
    lon = payload.get("longitude", payload.get("lon"))

    if lat is None or lon is None:
        raise ValueError(f"Location '{name}' is missing latitude/longitude in locations.json")

    return float(lat), float(lon)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p = math.pi / 180.0
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2.0
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2.0
    )
    return 12742.0 * math.asin(math.sqrt(a))


def _litres(distance_km: float, fuel_l_per_100km: float) -> float:
    return max(0.0, float(distance_km)) * (float(fuel_l_per_100km) / 100.0)


def _make_charts(
    legs_rows: list[dict[str, Any]],
    fuel_type: str,
    price_per_l: float,
    fuel_l_per_100km: float,
) -> BytesIO:
    df = pd.DataFrame(legs_rows)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.2, 8.2))
    fig.subplots_adjust(top=0.93, bottom=0.08, left=0.10, right=0.92, hspace=0.38)

    names = df["name"].tolist()
    dists = df["dist_km"].tolist()
    costs = df["cost"].tolist()

    green_main = "#2e7d32"
    green_soft = "#66bb6a"
    edge_col = "#1b5e20"

    bars1 = ax1.bar(
        names,
        dists,
        color=green_main,
        edgecolor=edge_col,
        linewidth=0.7,
        width=0.42,
    )
    ax1.set_title("Distance per Leg", fontsize=12, fontweight="bold", pad=10)
    ax1.bar_label(bars1, padding=3, fmt="%.1f km", fontsize=8)
    ax1.set_ylabel("Kilometres", fontsize=9, fontweight="bold")
    ax1.grid(True, axis="y", alpha=0.18, linewidth=0.7)
    ax1.set_axisbelow(True)
    ax1.tick_params(axis="x", labelsize=8)
    ax1.tick_params(axis="y", labelsize=8)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)

    bars2 = ax2.bar(
        names,
        costs,
        color=green_soft,
        edgecolor=edge_col,
        linewidth=0.7,
        width=0.42,
    )
    ax2.set_title(
        f"Fuel Cost per Leg ({fuel_type} @ ${price_per_l:.3f}/L, {fuel_l_per_100km:.1f} L/100km)",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax2.bar_label(bars2, padding=3, fmt="$%.2f", fontsize=8)
    ax2.set_ylabel("Cost ($)", fontsize=9, fontweight="bold")
    ax2.grid(True, axis="y", alpha=0.18, linewidth=0.7)
    ax2.set_axisbelow(True)
    ax2.tick_params(axis="x", labelsize=8)
    ax2.tick_params(axis="y", labelsize=8)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


def generate_report(
    target: str,
    data: Any,
    output_dir: str,
    logger: Callable[[str], None] = print,
):
    """
    Standardized signature:
      generate_report(target, data, output_dir, logger=...)

    data dict expected:
      {
        "route": ["Start", "Stop1", "Stop2"],
        "fuel_type": "Petrol"|"Diesel",
        "fuel_l_per_100km": 9.5,
        "fuel_price": 2.10
      }

    Returns PDF path or None.
    """
    try:
        if not isinstance(data, dict):
            raise ValueError("Trip worker expects data dict with 'route' etc.")

        route = data.get("route") or data.get("sequence") or data.get("locations")
        if not isinstance(route, (list, tuple)) or len(route) < 2:
            raise ValueError("Trip route must contain at least 2 locations.")

        fuel_type = str(data.get("fuel_type", "Petrol")).strip().title()
        fuel_l_per_100km = float(data.get("fuel_l_per_100km", 9.5))
        price_per_l = float(data.get("fuel_price", 2.10))

        logger(
            f"Trip worker: target={target} route={route} fuel={fuel_type} "
            f"{fuel_l_per_100km:.1f}L/100km @ ${price_per_l:.2f}/L"
        )

        legs_rows: list[dict[str, Any]] = []
        total_km = total_l = total_cost = 0.0

        for i in range(len(route) - 1):
            s = str(route[i])
            e = str(route[i + 1])

            lat1, lon1 = _get_lat_lon_from_location(s)
            lat2, lon2 = _get_lat_lon_from_location(e)

            dist_km = _haversine_km(lat1, lon1, lat2, lon2)
            litres = _litres(dist_km, fuel_l_per_100km)
            cost = litres * price_per_l

            total_km += dist_km
            total_l += litres
            total_cost += cost

            legs_rows.append(
                {
                    "name": f"{s[:3]}→{e[:3]}",
                    "start": s,
                    "end": e,
                    "dist_km": dist_km,
                    "litres": litres,
                    "cost": cost,
                }
            )

        chart_buf = _make_charts(legs_rows, fuel_type, price_per_l, fuel_l_per_100km)

        os.makedirs(output_dir, exist_ok=True)
        filename = f"Trip_{target}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        ppath = os.path.join(output_dir, filename)

        # Full route title using all route locations
        route_title = "_".join(str(x) for x in route)

        styles = getSampleStyleSheet()
        doc = SimpleDocTemplate(
            ppath,
            pagesize=A4,
            topMargin=0.7 * cm,
            bottomMargin=0.7 * cm,
        )

        summary_table = Table(
            [
                ["Fuel type", fuel_type],
                ["Price per litre", f"${price_per_l:.3f}"],
                ["Consumption", f"{fuel_l_per_100km:.1f} L/100km"],
                ["Total distance", f"{total_km:.1f} km"],
                ["Total fuel", f"{total_l:.1f} L"],
                ["Total cost", f"${total_cost:.2f}"],
            ],
            colWidths=[4.6 * cm, 4.8 * cm],
        )
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f5e9")),
                    ("BACKGROUND", (1, 0), (1, -1), colors.white),
                    ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bdbdbd")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        story = [
            Paragraph(f"<b>TRIP REPORT: {route_title}</b>", styles["Title"]),
            Spacer(1, 0.20 * cm),
            Paragraph("<b>Trip Summary</b>", styles["Heading2"]),
            Spacer(1, 0.12 * cm),
            summary_table,
            Spacer(1, 0.28 * cm),
            Paragraph("<b>Leg Breakdown</b>", styles["Heading2"]),
            Spacer(1, 0.10 * cm),
        ]

        for idx, leg in enumerate(legs_rows, start=1):
            story.append(
                Paragraph(
                    f"{idx}. <b>{leg['start']} → {leg['end']}</b>  |  "
                    f"{leg['dist_km']:.1f} km  |  "
                    f"{leg['litres']:.1f} L  |  "
                    f"${leg['cost']:.2f}",
                    styles["Normal"],
                )
            )
            story.append(Spacer(1, 0.05 * cm))

        story.append(Spacer(1, 0.25 * cm))
        story.append(Image(chart_buf, 18.2 * cm, 15.2 * cm))

        doc.build(story)

        if os.path.exists(ppath) and os.path.getsize(ppath) > 1000:
            logger(f"SUCCESS: Trip PDF created at {ppath}")
            return ppath

        logger("ERROR: Trip PDF not written or too small.")
        return None

    except Exception as e:
        logger(f"TRIP worker error: {e}")
        return None
