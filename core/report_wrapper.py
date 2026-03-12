#!/usr/bin/env python3
"""
Report Wrapper - Traffic Controller for all workers.
Ensures the right worker gets the right data payload.
"""

from core import surf_worker, sky_worker, weather_worker, trip_worker


def generate_report(target, kind, data, output_dir):

    workers = {
        "surf": surf_worker,
        "sky": sky_worker,
        "weather": weather_worker,
        "trip": trip_worker
    }

    worker = workers.get(kind.lower().strip())

    if not worker:
        print(f"❌ Error: No worker found for report type '{kind}'")
        return None

    try:

        print(f"➡ Generating {kind} report for {target}")

        return worker.generate_report(target, data, output_dir)

    except Exception as e:

        print(f"❌ Critical failure in {kind}_worker: {e}")

        return None