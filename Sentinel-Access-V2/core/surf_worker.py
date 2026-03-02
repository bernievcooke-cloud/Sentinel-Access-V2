"""
Surf Report Generator - V2.9
Generates comprehensive surf forecasts with 3 charts:
1. Daily  - Today's swell/wind/tide with X-factor beach markers
2. Next Best Day - Tomorrow's peak window with best location highlighted
3. Weekly - 7-day outlook showing strategic X-windows and locations
Uses Open-Meteo Marine & Weather APIs (swell, wind, tide approximation).
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import cm
import requests
import tempfile
import shutil

from config.settings import BASE_OUTPUT

# =============================================
# CHART LAYOUT CONSTANTS
# =============================================

# Extra vertical space above the highest data point so labels are visible
CHART_HEADROOM_FACTOR = 1.35

# M2 tidal constituent: approximate amplitude (m) and period (hours)
TIDE_AMPLITUDE_M = 0.6
M2_PERIOD_HOURS  = 12.42

# Fallback wind values when API data is missing
DEFAULT_WIND_SPEED_KMH   = 10.0
DEFAULT_WIND_DIR_DEGREES = 270.0

# Tertiary (tide) axis position relative to chart width
TERTIARY_AXIS_OFFSET = 1.12

# Minimum qualifying hours per day for a beach to be flagged as X-factor active
MIN_XFACTOR_HOURS = 2

# Weekly bar chart geometry
BAR_WIDTH          = 0.3
BAR_X_OFFSET       = 0.15   # bars are shifted left by this amount
LABEL_Y_SPACING    = 0.07   # label offset as fraction of s_max

# =============================================
# X-FACTOR BEACH DEFINITIONS (Philip Island)
# =============================================

# wind_dir_min / wind_dir_max are inclusive degree boundaries
XFACTOR_BEACHES = {
    "Woolamai": {"swell_min": 1.5, "wind_max": 20, "wind_dir_min": 225, "wind_dir_max": 360},
    "Smiths":   {"swell_min": 1.0, "wind_max": 25, "wind_dir_min": 135, "wind_dir_max": 270},
    "Cat Bay":  {"swell_min": 0.8, "wind_max": 30, "wind_dir_min":  45, "wind_dir_max": 180},
}


def check_xfactor(wave_height, wind_speed, wind_dir, beach="Woolamai"):
    """Return True if conditions meet X-factor criteria for a named beach."""
    cfg = XFACTOR_BEACHES.get(beach, XFACTOR_BEACHES["Woolamai"])
    try:
        d = float(wind_dir) % 360
        return (
            float(wave_height) >= cfg["swell_min"]
            and float(wind_speed) <= cfg["wind_max"]
            and cfg["wind_dir_min"] <= d <= cfg["wind_dir_max"]
        )
    except (TypeError, ValueError):
        return False


# =============================================
# DATA FETCHING
# =============================================

def fetch_surf_data(lat, lon):
    """Fetch wave data — tries Open-Meteo Marine API, falls back to forecast API."""
    try:
        print(f"[FETCH] Fetching marine data for {lat}, {lon}")
        url = (
            f"https://marine-api.open-meteo.com/v1/marine"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=wave_height,wave_period,swell_wave_height,swell_wave_period"
            f"&forecast_days=7&timezone=auto"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        for col in ["wave_height", "wave_period", "swell_wave_height"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        print(f"[OK] Marine API: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARN] Marine API unavailable ({e}), falling back to forecast API")

    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=wave_height,wave_period"
            f"&forecast_days=7&timezone=auto"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        df["wave_height"] = pd.to_numeric(df["wave_height"], errors="coerce")
        df["wave_period"] = pd.to_numeric(df["wave_period"], errors="coerce")
        print(f"[OK] Forecast API fallback: {len(df)} records")
        return df
    except Exception as e2:
        print(f"[ERROR] Both surf APIs failed: {e2}")
        return None


def fetch_wind_data(lat, lon):
    """Fetch hourly wind speed & direction from Open-Meteo."""
    try:
        print(f"[FETCH] Fetching wind data for {lat}, {lon}")
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&hourly=wind_speed_10m,wind_direction_10m"
            f"&forecast_days=7&timezone=auto"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data["hourly"])
        df["time"] = pd.to_datetime(df["time"])
        df["wind_speed_10m"] = pd.to_numeric(df["wind_speed_10m"], errors="coerce")
        df["wind_direction_10m"] = pd.to_numeric(df["wind_direction_10m"], errors="coerce")
        print(f"[OK] Wind data: {len(df)} records")
        return df
    except Exception as e:
        print(f"[WARN] Wind data unavailable: {e}")
        return None


def build_tide_column(df):
    """Approximate tidal height via M2 sinusoidal model (period = M2_PERIOD_HOURS)."""
    times = df["time"].dt.tz_localize(None) if df["time"].dt.tz is not None else df["time"]
    t0 = times.iloc[0]
    hours = np.array([(t - t0).total_seconds() / 3600 for t in times])
    return TIDE_AMPLITUDE_M * np.sin(2 * np.pi * hours / M2_PERIOD_HOURS) + TIDE_AMPLITUDE_M


def merge_data(surf_df, wind_df):
    """Left-join wind columns onto the surf dataframe."""
    if wind_df is None:
        surf_df = surf_df.copy()
        surf_df["wind_speed_10m"] = np.nan
        surf_df["wind_direction_10m"] = np.nan
        return surf_df
    try:
        s = surf_df.copy()
        w = wind_df.copy()
        s["time"] = s["time"].dt.tz_localize(None) if s["time"].dt.tz is not None else s["time"]
        w["time"] = w["time"].dt.tz_localize(None) if w["time"].dt.tz is not None else w["time"]
        return pd.merge(s, w[["time", "wind_speed_10m", "wind_direction_10m"]], on="time", how="left")
    except Exception as e:
        print(f"[WARN] Wind merge failed: {e}")
        surf_df = surf_df.copy()
        surf_df["wind_speed_10m"] = np.nan
        surf_df["wind_direction_10m"] = np.nan
        return surf_df


# =============================================
# ANALYSIS HELPERS
# =============================================

def get_condition_text(wave_height):
    """Return a text label for wave height quality."""
    try:
        h = float(wave_height)
        if h >= 2.0:   return "EXCELLENT"
        elif h >= 1.5: return "GOOD"
        elif h >= 1.0: return "FAIR"
        else:          return "POOR"
    except Exception:
        return "N/A"


def find_best_swell_day(df):
    """Return (date, avg_height) for the day with the highest mean wave height."""
    try:
        d = df.copy()
        d["wave_height"] = pd.to_numeric(d["wave_height"], errors="coerce")
        d["date"] = d["time"].dt.date
        d = d.dropna(subset=["wave_height"])
        if d.empty:
            return None, 0.0
        daily = d.groupby("date")["wave_height"].mean()
        best_date = daily.idxmax()
        return best_date, float(daily[best_date])
    except Exception as e:
        print(f"[ERROR] find_best_swell_day: {e}")
        return None, 0.0


def _best_xfactor_beach(day_df):
    """Return the best-matching X-factor beach for a day slice, default Woolamai."""
    avg_swell = day_df["wave_height"].mean()
    avg_wind = float(day_df["wind_speed_10m"].mean()) if day_df["wind_speed_10m"].notna().any() else DEFAULT_WIND_SPEED_KMH
    avg_dir = float(day_df["wind_direction_10m"].mean()) if day_df["wind_direction_10m"].notna().any() else DEFAULT_WIND_DIR_DEGREES
    for beach in ["Woolamai", "Smiths", "Cat Bay"]:
        if check_xfactor(avg_swell, avg_wind, avg_dir, beach):
            return beach
    return "Woolamai"


# =============================================
# CHART HELPERS — multi-axis setup
# =============================================

def _add_wind_axis(ax2, times, wind_series):
    """Plot wind on secondary axis; return line or None."""
    if wind_series is None or not wind_series.notna().any():
        return None
    w_max = wind_series.max()
    ax2.set_ylim(0, max(w_max * CHART_HEADROOM_FACTOR, 1))
    (l,) = ax2.plot(times, wind_series, color="green", lw=2, ls="--", label="Wind (km/h)")
    ax2.set_ylabel("Wind Speed (km/h)", fontweight="bold", fontsize=9, color="green")
    ax2.tick_params(axis="y", colors="green")
    return l


def _add_tide_axis(ax3, times, tide_series):
    """Plot tide on tertiary axis; return line."""
    t_max = tide_series.max()
    ax3.set_ylim(0, max(t_max * CHART_HEADROOM_FACTOR, 0.1))
    (l,) = ax3.plot(times, tide_series, color="cyan", lw=2, ls=":", label="Tide (m)", alpha=0.9)
    ax3.set_ylabel("Tide (m)", fontweight="bold", fontsize=9, color="cyan")
    ax3.tick_params(axis="y", colors="cyan")
    return l


def _scatter_xfactor_markers(ax, day_df):
    """Add green (peak) and blue (alternative) X markers to swell axis."""
    has_peak = has_alt = False
    for _, row in day_df.iterrows():
        h = row["wave_height"]
        ws = row["wind_speed_10m"] if pd.notna(row.get("wind_speed_10m")) else DEFAULT_WIND_SPEED_KMH
        wd = row["wind_direction_10m"] if pd.notna(row.get("wind_direction_10m")) else DEFAULT_WIND_DIR_DEGREES
        if check_xfactor(h, ws, wd, "Woolamai"):
            ax.scatter(row["time"], h, color="green", marker="X", s=130, zorder=10, lw=2)
            has_peak = True
        elif check_xfactor(h, ws, wd, "Smiths") or check_xfactor(h, ws, wd, "Cat Bay"):
            ax.scatter(row["time"], h, color="#1f77b4", marker="X", s=100, zorder=9, lw=1.5, alpha=0.7)
            has_alt = True
    return has_peak, has_alt


def _format_hourly_axis(ax):
    """Apply consistent hourly time labels to a chart x-axis."""
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.HourLocator(interval=3))
    plt.xticks(rotation=45)


# =============================================
# CHART 1: TODAY'S CONDITIONS (Daily)
# =============================================

def generate_today_chart(df, chart_path):
    """Chart 1: Today's swell/wind/tide with X-factor beach markers."""
    try:
        now = datetime.now()
        day_df = df[df["time"].dt.date == now.date()].copy()
        if day_df.empty:
            day_df = df.head(24).copy()

        day_df["wave_height"] = pd.to_numeric(day_df["wave_height"], errors="coerce")
        day_df = day_df.dropna(subset=["wave_height"]).reset_index(drop=True)
        if day_df.empty:
            return False

        day_df["tide"] = build_tide_column(day_df)

        fig, ax1 = plt.subplots(figsize=(11, 5.5))
        ax2 = ax1.twinx()
        ax3 = ax1.twinx()
        ax3.spines["right"].set_position(("axes", TERTIARY_AXIS_OFFSET))

        # Swell — blue, primary axis, 35 % headroom
        s_max = day_df["wave_height"].max()
        ax1.set_ylim(0, s_max * CHART_HEADROOM_FACTOR)
        (l1,) = ax1.plot(day_df["time"], day_df["wave_height"], color="#1f77b4", lw=3.5, label="Swell (m)")
        ax1.fill_between(day_df["time"], day_df["wave_height"], alpha=0.25, color="#1f77b4")
        ax1.set_ylabel("Swell Height (m)", fontweight="bold", fontsize=9, color="#1f77b4")
        ax1.tick_params(axis="y", colors="#1f77b4")

        lines = [l1]

        # Wind — green dashed, secondary axis
        wind_line = _add_wind_axis(ax2, day_df["time"], day_df.get("wind_speed_10m"))
        if wind_line:
            lines.append(wind_line)

        # Tide — cyan dotted, tertiary axis
        lines.append(_add_tide_axis(ax3, day_df["time"], day_df["tide"]))

        # X-factor markers
        has_peak, has_alt = _scatter_xfactor_markers(ax1, day_df)

        # Current-time marker
        ax1.axvline(now, color="red", lw=1.5, ls="--")

        # Time labels
        _format_hourly_axis(ax1)

        # Legend
        labels = [l.get_label() for l in lines]
        dummy_handles = list(lines)
        if has_peak:
            dummy_handles.append(plt.scatter([], [], color="green", marker="X", s=80))
            labels.append("Peak X (Woolamai)")
        if has_alt:
            dummy_handles.append(plt.scatter([], [], color="#1f77b4", marker="X", s=80, alpha=0.7))
            labels.append("Alt X (Smiths/Cat Bay)")

        ax1.legend(dummy_handles, labels, loc="upper left", fontsize=9)
        ax1.set_title("TODAY'S SWELL / WIND / TIDE CONDITIONS", fontweight="bold", fontsize=13)
        ax1.grid(True, alpha=0.25)
        plt.tight_layout()
        plt.savefig(chart_path, format="png", dpi=140, bbox_inches="tight")
        plt.close(fig)
        print(f"[OK] Chart 1 saved: {chart_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Chart 1: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# CHART 2: NEXT BEST DAY
# =============================================

def generate_best_day_chart(df, chart_path):
    """Chart 2: Next best day — peak window highlight and best beach."""
    try:
        best_date, _ = find_best_swell_day(df)
        if best_date is None:
            best_date = datetime.now().date() + timedelta(days=1)

        day_df = df[df["time"].dt.date == best_date].copy()
        if day_df.empty:
            day_df = df.iloc[24:48].copy()

        day_df["wave_height"] = pd.to_numeric(day_df["wave_height"], errors="coerce")
        day_df = day_df.dropna(subset=["wave_height"]).reset_index(drop=True)
        if day_df.empty:
            return False

        day_df["tide"] = build_tide_column(day_df)

        # Identify peak window (top-quartile swell)
        threshold = day_df["wave_height"].quantile(0.75)
        peak_df = day_df[day_df["wave_height"] >= threshold]
        best_beach = _best_xfactor_beach(peak_df if not peak_df.empty else day_df)

        fig, ax1 = plt.subplots(figsize=(11, 5.5))
        ax2 = ax1.twinx()
        ax3 = ax1.twinx()
        ax3.spines["right"].set_position(("axes", TERTIARY_AXIS_OFFSET))

        # Swell — orange, 35 % headroom
        s_max = day_df["wave_height"].max()
        ax1.set_ylim(0, s_max * CHART_HEADROOM_FACTOR)
        (l1,) = ax1.plot(day_df["time"], day_df["wave_height"], color="#ff7f0e", lw=3.5, label="Swell (m)")
        ax1.fill_between(day_df["time"], day_df["wave_height"], alpha=0.25, color="#ff7f0e")
        ax1.set_ylabel("Swell Height (m)", fontweight="bold", fontsize=9, color="#ff7f0e")
        ax1.tick_params(axis="y", colors="#ff7f0e")

        lines = [l1]

        wind_line = _add_wind_axis(ax2, day_df["time"], day_df.get("wind_speed_10m"))
        if wind_line:
            lines.append(wind_line)

        lines.append(_add_tide_axis(ax3, day_df["time"], day_df["tide"]))

        # Highlight peak window
        if not peak_df.empty:
            ax1.axvspan(peak_df["time"].min(), peak_df["time"].max(), color="gold", alpha=0.2)

        # X markers for best beach
        for _, row in day_df.iterrows():
            ws = row["wind_speed_10m"] if pd.notna(row.get("wind_speed_10m")) else DEFAULT_WIND_SPEED_KMH
            wd = row["wind_direction_10m"] if pd.notna(row.get("wind_direction_10m")) else DEFAULT_WIND_DIR_DEGREES
            if check_xfactor(row["wave_height"], ws, wd, best_beach):
                ax1.scatter(row["time"], row["wave_height"], color="green", marker="X", s=130, zorder=10, lw=2)

        _format_hourly_axis(ax1)

        try:
            title_date = best_date.strftime("%A, %B %d")
        except Exception:
            title_date = str(best_date)

        ax1.set_title(
            f"NEXT BEST DAY: {title_date}  |  Best: {best_beach}",
            fontweight="bold", fontsize=13,
        )
        ax1.legend(lines, [l.get_label() for l in lines], loc="upper left", fontsize=9)
        ax1.grid(True, alpha=0.25)
        plt.tight_layout()
        plt.savefig(chart_path, format="png", dpi=140, bbox_inches="tight")
        plt.close(fig)
        print(f"[OK] Chart 2 saved: {chart_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Chart 2: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# CHART 3: 7-DAY WEEKLY OUTLOOK
# =============================================

def generate_weekly_chart(df, chart_path):
    """Chart 3: 7-day swell outlook with X-factor windows and beach labels."""
    try:
        df_copy = df.copy()
        df_copy["wave_height"] = pd.to_numeric(df_copy["wave_height"], errors="coerce")
        df_copy["date"] = df_copy["time"].dt.date
        df_copy = df_copy.dropna(subset=["wave_height"])
        if df_copy.empty:
            return False

        daily = (
            df_copy.groupby("date")["wave_height"]
            .agg(["mean", "max"])
            .reset_index()
        )
        daily.columns = ["date", "mean", "max"]

        # X-factor active beaches per day
        xfactor_labels = []
        for d in daily["date"]:
            rows = df_copy[df_copy["date"] == d]
            active = []
            for beach, cfg in XFACTOR_BEACHES.items():
                cands = rows[rows["wave_height"] >= cfg["swell_min"]]
                if "wind_speed_10m" in cands.columns:
                    cands = cands[cands["wind_speed_10m"].fillna(DEFAULT_WIND_SPEED_KMH) <= cfg["wind_max"]]
                if len(cands) >= MIN_XFACTOR_HOURS:
                    active.append(beach[0])  # W / S / C
            xfactor_labels.append("+".join(active) if active else "")

        fig, ax1 = plt.subplots(figsize=(11, 5.5))
        ax2 = ax1.twinx()

        x = np.arange(len(daily))
        best_i = int(daily["mean"].idxmax())

        # Swell bars + max line, 35 % headroom
        s_max = daily["max"].max()
        ax1.set_ylim(0, s_max * CHART_HEADROOM_FACTOR)
        bar_colors = ["#ff7f0e" if i == best_i else "#1f77b4" for i in range(len(daily))]
        ax1.bar(x - BAR_X_OFFSET, daily["mean"], width=BAR_WIDTH, color=bar_colors, alpha=0.75,
                label="Avg Swell (m)", edgecolor="black", lw=1)
        ax1.plot(x, daily["max"], "b--o", lw=1.5, ms=5, label="Max Swell (m)", alpha=0.7)
        ax1.set_ylabel("Swell Height (m)", fontweight="bold", fontsize=9, color="#1f77b4")
        ax1.tick_params(axis="y", colors="#1f77b4")

        # Daily-mean wind line
        if "wind_speed_10m" in df_copy.columns:
            daily_wind = df_copy.groupby("date")["wind_speed_10m"].mean().reset_index()
            daily_wind.columns = ["date", "wind_mean"]
            merged_w = pd.merge(daily, daily_wind, on="date", how="left")
            if merged_w["wind_mean"].notna().any():
                w_max = merged_w["wind_mean"].max()
                ax2.set_ylim(0, max(w_max * CHART_HEADROOM_FACTOR, 1))
                ax2.plot(x, merged_w["wind_mean"], color="green", lw=2, ls="--",
                         marker="s", ms=4, label="Avg Wind (km/h)")
                ax2.set_ylabel("Wind Speed (km/h)", fontweight="bold", fontsize=9, color="green")
                ax2.tick_params(axis="y", colors="green")

        # X-factor annotations above bars
        for i, (d, lbl) in enumerate(zip(daily["date"], xfactor_labels)):
            h_val = daily.loc[daily["date"] == d, "mean"].values[0]
            if lbl:
                color = "green" if i == best_i else "#1f77b4"
                ax1.annotate(
                    f"\u2717{lbl}",
                    (i - BAR_X_OFFSET, h_val + s_max * LABEL_Y_SPACING),
                    ha="center", fontsize=9, fontweight="bold", color=color,
                )

        ax1.set_xticks(x)
        ax1.set_xticklabels([d.strftime("%a %d") for d in daily["date"]], fontsize=9)
        ax1.set_title(
            "7-DAY SWELL OUTLOOK \u2014 X-FACTOR WINDOWS & LOCATIONS",
            fontweight="bold", fontsize=13,
        )

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=9)
        ax1.grid(True, alpha=0.25, axis="y")
        plt.tight_layout()
        plt.savefig(chart_path, format="png", dpi=140, bbox_inches="tight")
        plt.close(fig)
        print(f"[OK] Chart 3 saved: {chart_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Chart 3: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# GENERATE COMPLETE PDF REPORT
# =============================================

def generate_report(location, report_type, coords, output_dir=BASE_OUTPUT):
    """Generate complete surf report PDF with 3 charts."""
    temp_dir = tempfile.mkdtemp()

    try:
        print(f"\n{'='*50}")
        print(f"GENERATING SURF REPORT: {location}")
        print(f"{'='*50}")

        lat, lon = coords

        # Fetch and merge data
        df = fetch_surf_data(lat, lon)
        if df is None or df.empty:
            raise Exception("No surf data fetched")

        wind_df = fetch_wind_data(lat, lon)
        df = merge_data(df, wind_df)
        df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)

        # Output path
        loc_dir = os.path.join(output_dir, location)
        os.makedirs(loc_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
        save_path = os.path.join(loc_dir, f"Surf_Report_{location}_{timestamp}.pdf")

        # Summary stats
        try:
            current_height = float(df["wave_height"].dropna().iloc[-1])
        except Exception:
            current_height = 0.0

        best_date, best_height = find_best_swell_day(df)
        best_day_text = best_date.strftime("%A") if best_date else "N/A"

        print(f"Current height: {current_height:.2f}m")
        print(f"Best day: {best_day_text}, height: {best_height:.2f}m")

        # Generate charts
        print("[INFO] Generating charts...")
        chart1_path = os.path.join(temp_dir, "chart1.png")
        chart2_path = os.path.join(temp_dir, "chart2.png")
        chart3_path = os.path.join(temp_dir, "chart3.png")

        c1_ok = generate_today_chart(df, chart1_path)
        c2_ok = generate_best_day_chart(df, chart2_path)
        c3_ok = generate_weekly_chart(df, chart3_path)

        # Build PDF
        doc = SimpleDocTemplate(
            save_path, pagesize=A4,
            topMargin=0.5*cm, bottomMargin=0.5*cm,
            leftMargin=0.5*cm, rightMargin=2.5*cm,
        )
        styles = getSampleStyleSheet()
        story = []

        story.append(Paragraph(f"<b>SENTINEL SURF REPORT: {location.upper()}</b>", styles["Title"]))
        story.append(Spacer(1, 8))

        t = Table([
            ["LOCATION",        location.upper()],
            ["COORDINATES",     f"{lat:.4f}, {lon:.4f}"],
            ["CURRENT SWELL",   f"{current_height:.1f}m \u2014 {get_condition_text(current_height)}"],
            ["BEST SWELL DAY",  f"{best_day_text} \u2014 {best_height:.1f}m avg"],
            ["X-FACTOR BEACHES","Woolamai | Smiths | Cat Bay"],
            ["GENERATED",       datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        ], colWidths=[5*cm, 13.5*cm])

        t.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#1f77b4")),
            ("TEXTCOLOR",     (0, 0), (0, -1), colors.white),
            ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
            ("FONTSIZE",      (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS",(0, 0), (-1, -1), [colors.white, colors.HexColor("#f0f0f0")]),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.grey),
        ]))

        story.append(t)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Chart 1: Today's Swell / Wind / Tide</b>", styles["Normal"]))
        if c1_ok and os.path.exists(chart1_path):
            story.append(Image(chart1_path, 18.5*cm, 9*cm))
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Chart 2: Next Best Day \u2014 Peak Window</b>", styles["Normal"]))
        if c2_ok and os.path.exists(chart2_path):
            story.append(Image(chart2_path, 18.5*cm, 9*cm))
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Chart 3: 7-Day Swell Outlook \u2014 X-Factor Windows</b>", styles["Normal"]))
        if c3_ok and os.path.exists(chart3_path):
            story.append(Image(chart3_path, 18.5*cm, 9*cm))
        story.append(Spacer(1, 8))

        story.append(Paragraph(
            "<font size=8><b>Legend:</b> Green \u2717 = Peak X-factor (Woolamai) | "
            "Blue \u2717 = Alt X-factor (Smiths/Cat Bay) | "
            "Gold shading = Peak window | W=Woolamai S=Smiths C=Cat Bay</font>",
            styles["Normal"],
        ))

        doc.build(story)
        print(f"[OK] Report saved: {save_path}")
        print(f"{'='*50}\n")
        return save_path

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        print(f"{'='*50}\n")
        raise
    finally:
        try:
            shutil.rmtree(temp_dir)
            print("[OK] Temp files cleaned up")
        except Exception:
            pass