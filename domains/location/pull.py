"""Rebuild ``references.json`` from the IANA Time Zone Database, with no network access.

The database comes from the pinned ``tzdata`` package, read directly and never through the
operating system copy. For each place the zone is chosen from the database own zone table
(``zone1970.tab``: country codes, coordinates, zone, comment), and the offset schedule is the
database rule evaluated across 2020 to 2040: each row is the instant a new offset takes effect
and the offset in seconds from then on. The search endpoint returns the offset in force today
only, so the checker reads this schedule at the run instant.
"""

from __future__ import annotations

import zoneinfo
from datetime import UTC, datetime, timedelta
from importlib import resources
from typing import Any

import tzdata  # type: ignore[import-untyped]

SCHEDULE_START = datetime(2020, 1, 1, tzinfo=UTC)
SCHEDULE_END = datetime(2041, 1, 1, tzinfo=UTC)
RETRIEVED = "2026-10-09"

# (case id, name, country code, province as the search lists it, database zone)
PLACES = (
    ("kolkata", "Kolkata", "IN", "West Bengal", "Asia/Kolkata"),  # a half hour offset
    ("kathmandu", "Kathmandu", "NP", "Bagmati Province", "Asia/Kathmandu"),  # 45 minutes
    ("apia", "Apia", "WS", "Tuamasaga", "Pacific/Apia"),  # date line move 2011, no DST since 2021
    ("moscow", "Moscow", "RU", "Moscow", "Europe/Moscow"),  # DST removed 2011, offset moved 2014
    ("istanbul", "Istanbul", "TR", "Istanbul", "Europe/Istanbul"),  # permanent summer time 2016
    ("sydney", "Sydney", "AU", "New South Wales", "Australia/Sydney"),  # southern DST
    ("adelaide", "Adelaide", "AU", "South Australia", "Australia/Adelaide"),  # southern DST, :30
    ("santiago", "Santiago", "CL", "Santiago Metropolitan", "America/Santiago"),  # southern DST
    ("phoenix", "Phoenix", "US", "Arizona", "America/Phoenix"),  # no DST inside a DST country
    ("springfield-illinois", "Springfield", "US", "Illinois", "America/Chicago"),  # ambiguous
    ("springfield-oregon", "Springfield", "US", "Oregon", "America/Los_Angeles"),  # same name
    ("london-ontario", "London", "CA", "Ontario", "America/Toronto"),  # name of a bigger city
)


def zone_table() -> dict[str, str]:
    """Zone name to its comma separated country codes from the pinned database ``zone1970.tab``."""
    text = (resources.files("tzdata.zoneinfo") / "zone1970.tab").read_text(encoding="utf-8")
    table: dict[str, str] = {}
    for line in text.splitlines():
        if line and not line.startswith("#"):
            fields = line.split("\t")
            table[fields[2]] = fields[0]
    return table


def database_zone(name: str) -> zoneinfo.ZoneInfo:
    """A zone read from the ``tzdata`` package only, never from the system copy."""
    zoneinfo.reset_tzpath(to=[])
    return zoneinfo.ZoneInfo(name)


def offset_seconds(zone: zoneinfo.ZoneInfo, when: datetime) -> int:
    offset = zone.utcoffset(when.astimezone(zone))
    assert offset is not None
    return int(offset.total_seconds())


def schedule(zone: zoneinfo.ZoneInfo) -> list[list[Any]]:
    """``[instant, seconds]`` per change of offset, found daily and bisected to the second."""
    rows: list[list[Any]] = [[SCHEDULE_START.isoformat(), offset_seconds(zone, SCHEDULE_START)]]
    day = SCHEDULE_START
    while day < SCHEDULE_END:
        nxt = day + timedelta(days=1)
        if offset_seconds(zone, nxt) != offset_seconds(zone, day):
            low, high = day, nxt
            while high - low > timedelta(seconds=1):
                mid = low + (high - low) / 2
                low, high = (
                    (mid, high)
                    if offset_seconds(zone, mid) == offset_seconds(zone, day)
                    else (low, mid)
                )
            rows.append([high.replace(microsecond=0).isoformat(), offset_seconds(zone, high)])
        day = nxt
    return rows


def pull() -> dict[str, Any]:
    table = zone_table()
    cases = []
    for case_id, name, country, province, zone_name in PLACES:
        if country not in table.get(zone_name, "").split(","):
            raise ValueError(f"{zone_name} is not a {country} zone in the database zone table")
        zone = database_zone(zone_name)
        cases.append(
            {
                "id": case_id,
                "input": {
                    "q": name,
                    "iso2": country,
                    "province": province,
                    "offsets": schedule(zone),
                },
                "expected": {
                    "timezone": zone_name,
                    "utc_offset_seconds": offset_seconds(
                        zone, datetime.fromisoformat(RETRIEVED).replace(tzinfo=UTC)
                    ),
                },
            }
        )
    return {
        "format": 1,
        "domain": "location",
        "sources": [
            {
                "name": "IANA Time Zone Database",
                "url": "https://www.iana.org/time-zones",
                "command": "uv run python -m benchmark pull location",
                "retrieved": RETRIEVED,
                "licence": "Public domain",
                "method": (
                    f"Release {tzdata.IANA_VERSION} (tzdata package {tzdata.__version__}). The "
                    "zone of each place is the one the database zone table lists for its "
                    "country and region; the offset schedule is the database rule evaluated "
                    "from 2020 to 2040 and read at the run instant, because the search "
                    "endpoint returns the offset in force today, not at a chosen date."
                ),
                "notes": (
                    "Places are pinned by name, country code and province, never by name "
                    "alone. The stored utc_offset is the offset on the pull date and is replaced "
                    "by the scheduled offset at the run instant."
                ),
            }
        ],
        "families": [
            {"label": "Time zone and UTC offset", "quantities": ["timezone", "utc_offset_seconds"]},
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": "A zone name and an offset in seconds are discrete: any other value fails.",
            }
        ],
        "cases": cases,
    }
