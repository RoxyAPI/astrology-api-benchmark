"""NASA JPL Horizons OBSERVER queries for pull scripts, geocentric unless a site is given.

Documentation: https://ssd-api.jpl.nasa.gov/doc/horizons.html (no key, courtesy rate limit).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timedelta

from benchmark.fetch import get_text

URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
LICENCE = "NASA JPL data, public domain US government work; cite Horizons"
GEOCENTRE = "500@399"
_STAMP = "%Y-%m-%d %H:%M:%S"
_ROWS = re.compile(r"\$\$SOE\s*\n(.+?)(?:\s*\$\$EOE|\Z)", re.DOTALL)


def observer(
    command: str,
    start: datetime,
    quantities: str,
    center: str = GEOCENTRE,
    extra: Mapping[str, str] | None = None,
    *,
    stop: datetime | None = None,
    step: str = "1",
) -> str:
    """Raw OBSERVER text from ``start`` to ``stop`` (UT, to the second), by default one minute.

    ``step`` is a Horizons ``STEP_SIZE``: ``"1"`` returns the two ends, ``"1h"`` a row every
    hour. ``extra`` adds Horizons parameters, values quoted as its documentation writes them: for a
    site, ``SITE_COORD`` and ``COORD_TYPE`` with ``center="coord@399"``; for decimal degree
    angles, ``ANG_FORMAT``.
    """
    return get_text(
        URL,
        {
            "format": "text",
            "COMMAND": f"'{command}'",
            "CENTER": f"'{center}'",
            "MAKE_EPHEM": "'YES'",
            "EPHEM_TYPE": "'OBSERVER'",
            "START_TIME": f"'{start.strftime(_STAMP)}'",
            "STOP_TIME": f"'{(stop or start + timedelta(minutes=1)).strftime(_STAMP)}'",
            "STEP_SIZE": f"'{step}'",
            "QUANTITIES": f"'{quantities}'",
            **(extra or {}),
        },
    )


def rows(text: str) -> list[list[str]]:
    """Whitespace fields of every ephemeris row between ``$$SOE`` and ``$$EOE``."""
    match = _ROWS.search(text)
    if not match:
        raise ValueError("no ephemeris rows in the Horizons response")
    return [line.split() for line in match.group(1).strip().splitlines()]


def first_row(text: str) -> list[str]:
    """Whitespace fields of the first ephemeris row."""
    return rows(text)[0]
