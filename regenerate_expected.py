#!/usr/bin/env python3
"""
Regenerate expected.csv from NASA JPL Horizons.

For every chart in charts.csv, queries the JPL Horizons API for the geocentric
ecliptic longitude of each major body at the chart's exact moment, then writes
expected.csv with one row per (chart, body) pair.

This script populates the dataset that benchmark.py reads. Run it once when you
add charts to charts.csv. The result is reproducible: anyone can re-run this and
get the same numbers (within the precision Horizons publishes).

Usage:
    python3 regenerate_expected.py

JPL Horizons API: https://ssd-api.jpl.nasa.gov/doc/horizons.html
No authentication required. Rate limit is courtesy-based (~1 request/second).
"""

from __future__ import annotations

import csv
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError

HORIZONS_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

# JPL Horizons COMMAND codes for major bodies, geocentric (CENTER=500@399)
BODY_CODES: dict[str, str] = {
    "Sun": "10",
    "Moon": "301",
    "Mercury": "199",
    "Venus": "299",
    "Mars": "499",
    "Jupiter": "599",
    "Saturn": "699",
    "Uranus": "799",
    "Neptune": "899",
    "Pluto": "999",
}

# Tolerance per body. Sub-arcminute for outer bodies; looser for the Moon
# (~13 deg/day motion amplifies any timing precision difference).
TOLERANCES: dict[str, float] = {
    "Sun": 0.05,
    "Moon": 0.20,
    "Mercury": 0.05,
    "Venus": 0.05,
    "Mars": 0.05,
    "Jupiter": 0.05,
    "Saturn": 0.05,
    "Uranus": 0.05,
    "Neptune": 0.05,
    "Pluto": 0.05,
}

SIGN_OFFSET = {
    "aries": 0.0,
    "taurus": 30.0,
    "gemini": 60.0,
    "cancer": 90.0,
    "leo": 120.0,
    "virgo": 150.0,
    "libra": 180.0,
    "scorpio": 210.0,
    "sagittarius": 240.0,
    "capricorn": 270.0,
    "aquarius": 300.0,
    "pisces": 330.0,
}

SIGN_NAMES = list(SIGN_OFFSET.keys())


def to_sign_and_degree(longitude: float) -> tuple[str, float]:
    """Convert absolute ecliptic longitude (0-360) to (sign, degree-within-sign)."""
    longitude = longitude % 360.0
    sign_index = int(longitude // 30)
    degree_within = longitude - (sign_index * 30)
    return SIGN_NAMES[sign_index], degree_within


def chart_utc_iso(date_str: str, time_str: str, timezone_offset: float) -> str:
    """Convert local-civil chart time (date, time, decimal timezone offset) to UTC ISO."""
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
    tz_seconds = int(timezone_offset * 3600)
    tz_obj = timezone(timedelta(seconds=tz_seconds))
    aware_local = naive.replace(tzinfo=tz_obj)
    aware_utc = aware_local.astimezone(timezone.utc)
    return aware_utc.strftime("%Y-%m-%d %H:%M")


def horizons_query(body_code: str, start_utc: str, stop_utc: str) -> str:
    """One Horizons query. Returns the raw text response."""
    params = {
        "format": "text",
        "COMMAND": f"'{body_code}'",
        "CENTER": "'500@399'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'OBSERVER'",
        "START_TIME": f"'{start_utc}'",
        "STOP_TIME": f"'{stop_utc}'",
        "STEP_SIZE": "'1'",
        "QUANTITIES": "'31'",
    }
    url = f"{HORIZONS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url=url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def parse_ecliptic_longitude(response_text: str) -> float | None:
    """Extract Observer Ecliptic Longitude from the first $$SOE row."""
    soe_match = re.search(
        r"\$\$SOE\s*\n(.+?)(?:\s*\$\$EOE|\Z)",
        response_text,
        re.DOTALL,
    )
    if not soe_match:
        return None
    block = soe_match.group(1).strip()
    first_row = block.splitlines()[0].strip() if block else ""
    if not first_row:
        return None
    parts = first_row.split()
    if len(parts) < 4:
        return None
    try:
        return float(parts[-2])
    except ValueError:
        return None


def regenerate(charts_path: str, expected_path: str, sleep_seconds: float = 1.0) -> int:
    with open(charts_path, newline="", encoding="utf-8") as f:
        charts = list(csv.DictReader(f))

    rows: list[dict] = []
    total_queries = len(charts) * len(BODY_CODES)
    queries_done = 0

    for chart in charts:
        chart_id = chart["chart_id"]
        utc_start = chart_utc_iso(
            chart["date"], chart["time"], float(chart["timezone"])
        )
        utc_dt = datetime.strptime(utc_start, "%Y-%m-%d %H:%M")
        utc_stop = (utc_dt + timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M")

        for body, code in BODY_CODES.items():
            queries_done += 1
            print(
                f"[{queries_done}/{total_queries}] {chart_id} {body} at {utc_start} UTC",
                file=sys.stderr,
            )
            try:
                response = horizons_query(code, utc_start, utc_stop)
            except (HTTPError, URLError) as e:
                print(f"  ERROR: {e}", file=sys.stderr)
                return 1
            longitude = parse_ecliptic_longitude(response)
            if longitude is None:
                print(f"  parse failure for {body}", file=sys.stderr)
                continue
            sign, degree_within = to_sign_and_degree(longitude)
            rows.append(
                {
                    "chart_id": chart_id,
                    "body": body,
                    "sign": sign,
                    "degree_within_sign": round(degree_within, 4),
                    "source": "JPL Horizons (DE441)",
                    "tolerance_deg": TOLERANCES[body],
                }
            )
            time.sleep(sleep_seconds)

    with open(expected_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "chart_id",
                "body",
                "sign",
                "degree_within_sign",
                "source",
                "tolerance_deg",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} reference rows to {expected_path}")
    return 0


if __name__ == "__main__":
    sys.exit(regenerate("charts.csv", "expected.csv"))
