#!/usr/bin/env python3
"""
Vendor-agnostic astrology API accuracy benchmark.

Reads chart inputs from charts.csv and expected reference values from expected.csv,
queries any astrology API that exposes a natal-chart endpoint, computes per-body
deviation against the reference, and writes a results CSV plus a summary table.

Default target is RoxyAPI. Point at any other API by setting --base-url and adjusting
--natal-path / --planet-key as needed.

Usage:
    export API_KEY=your_key_here
    python3 benchmark.py
    python3 benchmark.py --base-url https://other-api.example.com --natal-path /chart
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import urllib.request
from urllib.error import HTTPError, URLError

# Sign offsets in degrees (tropical zodiac, 0 = vernal equinox)
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


def to_longitude(sign: str, degree_within_sign: float) -> float:
    """Convert sign + degree-within-sign to absolute ecliptic longitude (0-360)."""
    return (SIGN_OFFSET[sign.lower()] + degree_within_sign) % 360.0


def angular_distance(a: float, b: float) -> float:
    """Smallest angular distance between two longitudes in degrees, handling 0/360 wrap."""
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def post_natal_chart(base_url: str, natal_path: str, api_key: str, body: dict) -> dict:
    req = urllib.request.Request(
        url=f"{base_url.rstrip('/')}{natal_path}",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def extract_body_longitude(response: dict, body_name: str) -> float | None:
    """Find a body in the API response and return its absolute longitude (0-360)."""
    name_lower = body_name.lower()

    if name_lower in ("ascendant", "asc"):
        asc = response.get("ascendant")
        if isinstance(asc, dict):
            sign = asc.get("sign", "").lower()
            deg = asc.get("degree")
            if sign in SIGN_OFFSET and isinstance(deg, (int, float)):
                return to_longitude(sign, float(deg))

    if name_lower in ("midheaven", "mc"):
        mc = response.get("midheaven")
        if isinstance(mc, dict):
            sign = mc.get("sign", "").lower()
            deg = mc.get("degree")
            if sign in SIGN_OFFSET and isinstance(deg, (int, float)):
                return to_longitude(sign, float(deg))

    planets = response.get("planets") or []
    for p in planets:
        if str(p.get("name", "")).lower() == name_lower:
            lon = p.get("longitude")
            if isinstance(lon, (int, float)):
                return float(lon) % 360.0
            sign = str(p.get("sign", "")).lower()
            deg = p.get("degree")
            if sign in SIGN_OFFSET and isinstance(deg, (int, float)):
                return to_longitude(sign, float(deg))
    return None


def load_charts(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_expected(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = []
        for row in csv.DictReader(f):
            row["degree_within_sign"] = float(row["degree_within_sign"])
            row["tolerance_deg"] = float(row["tolerance_deg"])
            row["expected_longitude"] = to_longitude(row["sign"], row["degree_within_sign"])
            rows.append(row)
        return rows


def run_benchmark(args: argparse.Namespace) -> int:
    api_key = os.environ.get("API_KEY", "").strip()
    if not api_key:
        print("ERROR: set API_KEY environment variable", file=sys.stderr)
        return 2

    charts = load_charts(args.charts)
    expected = load_expected(args.expected)
    chart_index = {c["chart_id"]: c for c in charts}

    results: list[dict] = []
    chart_responses: dict[str, dict] = {}

    for chart_id, chart in chart_index.items():
        body = {
            "date": chart["date"],
            "time": chart["time"],
            "latitude": float(chart["latitude"]),
            "longitude": float(chart["longitude"]),
            "timezone": float(chart["timezone"]),
        }
        try:
            response = post_natal_chart(args.base_url, args.natal_path, api_key, body)
        except (HTTPError, URLError) as e:
            print(f"ERROR fetching {chart_id}: {e}", file=sys.stderr)
            return 3
        chart_responses[chart_id] = response
        print(f"fetched {chart_id} ({chart['name']})", file=sys.stderr)

    for ref in expected:
        chart_id = ref["chart_id"]
        body_name = ref["body"]
        response = chart_responses.get(chart_id)
        if response is None:
            continue
        actual = extract_body_longitude(response, body_name)
        if actual is None:
            results.append(
                {
                    "chart_id": chart_id,
                    "body": body_name,
                    "expected_longitude": round(ref["expected_longitude"], 4),
                    "actual_longitude": "",
                    "deviation_deg": "",
                    "deviation_arcmin": "",
                    "tolerance_deg": ref["tolerance_deg"],
                    "within_tolerance": "MISSING",
                }
            )
            continue
        deviation = angular_distance(ref["expected_longitude"], actual)
        within = deviation < ref["tolerance_deg"]
        results.append(
            {
                "chart_id": chart_id,
                "body": body_name,
                "expected_longitude": round(ref["expected_longitude"], 4),
                "actual_longitude": round(actual, 4),
                "deviation_deg": round(deviation, 4),
                "deviation_arcmin": round(deviation * 60.0, 2),
                "tolerance_deg": ref["tolerance_deg"],
                "within_tolerance": "PASS" if within else "FAIL",
            }
        )

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "chart_id",
                "body",
                "expected_longitude",
                "actual_longitude",
                "deviation_deg",
                "deviation_arcmin",
                "tolerance_deg",
                "within_tolerance",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    numeric = [r["deviation_deg"] for r in results if isinstance(r["deviation_deg"], (int, float))]
    passes = sum(1 for r in results if r["within_tolerance"] == "PASS")
    fails = sum(1 for r in results if r["within_tolerance"] == "FAIL")
    missing = sum(1 for r in results if r["within_tolerance"] == "MISSING")
    total = len(results)

    print()
    print(f"Total reference points : {total}")
    print(f"Within tolerance       : {passes}")
    print(f"Outside tolerance      : {fails}")
    print(f"Missing in API response: {missing}")
    if numeric:
        print()
        print(f"Mean deviation : {statistics.mean(numeric):.4f} deg ({statistics.mean(numeric) * 60:.2f} arcmin)")
        print(f"Median         : {statistics.median(numeric):.4f} deg ({statistics.median(numeric) * 60:.2f} arcmin)")
        print(f"Max            : {max(numeric):.4f} deg ({max(numeric) * 60:.2f} arcmin)")
        if len(numeric) >= 5:
            sorted_dev = sorted(numeric)
            p95_idx = int(len(sorted_dev) * 0.95)
            print(f"p95            : {sorted_dev[p95_idx]:.4f} deg ({sorted_dev[p95_idx] * 60:.2f} arcmin)")
    print()
    print(f"Detailed results written to {args.output}")
    return 0 if fails == 0 and missing == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://roxyapi.com/api/v2/astrology")
    parser.add_argument("--natal-path", default="/natal-chart")
    parser.add_argument("--charts", default="charts.csv")
    parser.add_argument("--expected", default="expected.csv")
    parser.add_argument("--output", default="results.csv")
    return run_benchmark(parser.parse_args())


if __name__ == "__main__":
    sys.exit(main())
