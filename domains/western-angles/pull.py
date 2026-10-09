"""Regenerate ``references.json``: the chart angles recomputed from NASA JPL Horizons.

For every chart this asks Horizons for two things at the chart instant converted to UT:

1. The local apparent sidereal time at the birthplace (OBSERVER quantity 7, printed to 0.0001
   seconds of time). Horizons reads times after 1962 as UTC and converts them to UT1 with its
   Earth orientation table before it computes sidereal time; times before 1962 it reads as UT1
   directly. So the sidereal angle carries UT1 without this script holding any UT1 table.
2. The apparent right ascension and declination of date (quantity 2) and the apparent ecliptic
   longitude and latitude of date (quantity 31) of a geocentric body. The same direction in
   both frames gives the true obliquity of date, the angle that turns one frame into the other
   (Meeus, eq. 12.1 and 12.2, solved for the obliquity). A body near the equinox line leaves
   that rotation ill conditioned, so the Sun, Moon, Mars, Jupiter and Saturn are read in turn
   until two lie well away from it; the two must agree and the better placed one is used.

From the sidereal angle, the true obliquity and the latitude the angles follow by the standard
spherical astronomy formulas, cited from Jean Meeus, Astronomical Algorithms, first edition,
Willmann-Bell, 1991:

- Midheaven: the ecliptic point on the meridian, the ecliptic longitude whose right ascension
  is the sidereal angle (chapter 12, eq. 12.3 with zero latitude).
- Ascendant: the rising one of the two ecliptic points on the horizon (chapter 12, "Ecliptic and
  Horizon", eq. 12.9).
- Placidus cusps: the ecliptic points whose hour angle is one third or two thirds of their own
  diurnal or nocturnal semi arc, the definition of Placidus de Titis, Tabulae Primi Mobilis
  (1657). The semi arc is the rising hour angle at zero altitude (chapter 14, eq. 14.1), the
  declination of an ecliptic point is chapter 12, eq. 12.4, and the cusp is found by fixed point
  iteration on its right ascension.

Placidus is undefined where part of the ecliptic never rises or sets, at or beyond the polar
circles, so charts there are skipped. Run it with ``uv run python -m benchmark pull
western-angles``; nothing else in the repo contacts Horizons.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime
from typing import Any

from benchmark import horizons
from benchmark.schema import Chart, load_charts

HORIZONS_DECIMALS = 7

OBLIQUITY_BODIES = {
    "Sun": "10",
    "Moon": "301",
    "Mars": "499",
    "Jupiter": "5",
    "Saturn": "6",
}
MIN_CONDITIONING = 0.3
"""Least distance from the equinox line, as a sine, for a body to fix the obliquity well."""
OBLIQUITY_AGREEMENT_ARCSEC = 0.01
"""Two well conditioned bodies agree to the printed digits; more than this is a parsing fault."""

CONVERGED_DEGREES = 1e-10
MAX_ITERATIONS = 200

BAND_ARCSEC = 36

# Cusps 1 and 10 are the Ascendant and the Midheaven; the other ten pair up across the chart.
# For cusp n: the right ascension is the sidereal angle plus base plus share times the diurnal
# semi arc of the cusp itself. Cusps 11 and 12 sit one and two thirds of the diurnal semi arc east
# of the meridian; cusps 2 and 3 sit two and one thirds of the nocturnal semi arc (180 minus the
# diurnal) west of the lower meridian, which reduces to the same form.
PLACIDUS: dict[int, tuple[float, float]] = {
    11: (0.0, 1 / 3),
    12: (0.0, 2 / 3),
    2: (60.0, 2 / 3),
    3: (120.0, 1 / 3),
}
OPPOSITE = {5: 11, 6: 12, 8: 2, 9: 3}


def cusp_name(number: int) -> str:
    return f"Cusp {number}"


QUANTITIES = ("Ascendant", "Midheaven", *(cusp_name(n) for n in (2, 3, 5, 6, 8, 9, 11, 12)))


class PlacidusUndefinedError(ValueError):
    """A cusp point never rises or sets at this latitude."""


def _norm(degrees: float) -> float:
    return degrees % 360.0


def midheaven(sidereal: float, obliquity: float) -> float:
    """Ecliptic longitude whose right ascension is the sidereal angle (Meeus eq. 12.3)."""
    t, e = math.radians(sidereal), math.radians(obliquity)
    return _norm(math.degrees(math.atan2(math.sin(t), math.cos(t) * math.cos(e))))


def ascendant(sidereal: float, obliquity: float, latitude: float) -> float:
    """The rising ecliptic point on the horizon (Meeus eq. 12.9, rising root)."""
    t, e, p = (math.radians(x) for x in (sidereal, obliquity, latitude))
    y = math.cos(t)
    x = -(math.sin(t) * math.cos(e) + math.tan(p) * math.sin(e))
    return _norm(math.degrees(math.atan2(y, x)))


def diurnal_semi_arc(declination: float, latitude: float) -> float:
    """Hour angle of rising at zero altitude, in degrees (Meeus eq. 14.1 with h0 = 0)."""
    c = -math.tan(math.radians(latitude)) * math.tan(math.radians(declination))
    if abs(c) > 1:
        raise PlacidusUndefinedError(f"declination {declination:.4f} never rises or sets here")
    return math.degrees(math.acos(c))


def ecliptic_longitude_of(right_ascension: float, obliquity: float) -> float:
    """Ecliptic longitude of the ecliptic point with this right ascension (Meeus eq. 12.3)."""
    a, e = math.radians(right_ascension), math.radians(obliquity)
    return _norm(math.degrees(math.atan2(math.sin(a), math.cos(a) * math.cos(e))))


def declination_of(longitude: float, obliquity: float) -> float:
    """Declination of the ecliptic point at this longitude (Meeus eq. 12.4 with zero latitude)."""
    s = math.sin(math.radians(obliquity)) * math.sin(math.radians(longitude))
    return math.degrees(math.asin(s))


def placidus_cusp(number: int, sidereal: float, obliquity: float, latitude: float) -> float:
    """Ecliptic longitude of an intermediate Placidus cusp (11, 12, 2 or 3) by iteration."""
    base, share = PLACIDUS[number]
    semi_arc = 90.0
    right_ascension = sidereal + base + share * semi_arc
    for _ in range(MAX_ITERATIONS):
        longitude = ecliptic_longitude_of(right_ascension, obliquity)
        semi_arc = diurnal_semi_arc(declination_of(longitude, obliquity), latitude)
        updated = sidereal + base + share * semi_arc
        if abs(updated - right_ascension) < CONVERGED_DEGREES:
            return ecliptic_longitude_of(updated, obliquity)
        right_ascension = updated
    raise PlacidusUndefinedError(f"cusp {number} did not converge")


def polar_limit(obliquity: float) -> float:
    """Latitude beyond which part of the ecliptic is circumpolar and Placidus is undefined."""
    return 90.0 - obliquity


def angles(sidereal: float, obliquity: float, latitude: float) -> dict[str, float]:
    """Ascendant, Midheaven and the intermediate Placidus cusps, in decimal degrees."""
    if abs(latitude) >= polar_limit(obliquity):
        raise PlacidusUndefinedError(f"latitude {latitude} is at or beyond the polar circle")
    values = {
        "Ascendant": ascendant(sidereal, obliquity, latitude),
        "Midheaven": midheaven(sidereal, obliquity),
    }
    cusps = {n: placidus_cusp(n, sidereal, obliquity, latitude) for n in PLACIDUS}
    cusps |= {n: _norm(cusps[pair] + 180.0) for n, pair in OPPOSITE.items()}
    values |= {cusp_name(n): cusps[n] for n in sorted(cusps)}
    return values


def obliquity_from(
    right_ascension: float, declination: float, longitude: float, latitude: float
) -> tuple[float, float]:
    """True obliquity from one direction given in both frames of date, and its conditioning.

    Meeus eq. 12.1 and 12.2 rotate the equatorial direction about the equinox line by the
    obliquity. Writing A = sin(dec) and B = cos(dec) sin(ra), the pair (B, A) turns into
    (cos(lat) sin(lon), sin(lat)), so the obliquity is the difference of their polar angles.
    The conditioning is the length of (B, A): the sine of the distance from the equinox line.
    """
    a, d, lon, lat = (math.radians(x) for x in (right_ascension, declination, longitude, latitude))
    big_a, big_b = math.sin(d), math.cos(d) * math.sin(a)
    obliquity = math.atan2(big_a, big_b) - math.atan2(math.sin(lat), math.cos(lat) * math.sin(lon))
    obliquity = (obliquity + math.pi) % (2 * math.pi) - math.pi
    return math.degrees(obliquity), math.hypot(big_a, big_b)


def local_sidereal_time(chart: Chart, instant: datetime) -> float:
    """Local apparent sidereal time at the birthplace, in degrees."""
    text = horizons.observer(
        "10",
        instant,
        "7",
        center="coord@399",
        extra={
            "COORD_TYPE": "'GEODETIC'",
            "SITE_COORD": f"'{chart.longitude},{chart.latitude},0'",
            "EXTRA_PREC": "'YES'",
        },
    )
    # The row ends with the sidereal time as hours, minutes and seconds of time.
    hours, minutes, seconds = (float(f) for f in horizons.first_row(text)[-3:])
    return (hours + minutes / 60 + seconds / 3600) * 15.0


def true_obliquity(instant: datetime) -> tuple[float, str]:
    """True obliquity of date in degrees, and the body that fixed it.

    Bodies are read in order until two lie well away from the equinox line; they must agree,
    and the better conditioned one is kept.
    """
    found: dict[str, tuple[float, float]] = {}
    for body, command in OBLIQUITY_BODIES.items():
        text = horizons.observer(
            command, instant, "2,31", extra={"ANG_FORMAT": "'DEG'", "EXTRA_PREC": "'YES'"}
        )
        # The row ends with right ascension, declination, ecliptic longitude and latitude.
        ra, dec, lon, lat = (float(f) for f in horizons.first_row(text)[-4:])
        obliquity, conditioning = obliquity_from(ra, dec, lon, lat)
        if conditioning >= MIN_CONDITIONING:
            found[body] = (obliquity, conditioning)
        if len(found) == 2:
            (first, (a, wa)), (second, (b, wb)) = found.items()
            if abs(a - b) * 3600 > OBLIQUITY_AGREEMENT_ARCSEC:
                raise ValueError(f"{instant}: obliquity from {first} and {second} disagree")
            return (a, first) if wa >= wb else (b, second)
    raise ValueError(f"{instant}: fewer than two bodies lie away from the equinox line")


def pull() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    skipped: list[str] = []
    for chart in load_charts().values():
        instant = chart.utc()
        print(f"{chart.id} {instant.isoformat()}", file=sys.stderr)
        obliquity, body = true_obliquity(instant)
        if abs(chart.latitude) >= polar_limit(obliquity):
            skipped.append(chart.id)
            continue
        sidereal = local_sidereal_time(chart, instant)
        print(f"  sidereal {sidereal:.7f} obliquity {obliquity:.7f} ({body})", file=sys.stderr)
        expected = {
            q: round(v, HORIZONS_DECIMALS)
            for q, v in angles(sidereal, obliquity, chart.latitude).items()
        }
        cases.append({"id": chart.id, "chart": chart.id, "expected": expected})
    return {
        "format": 1,
        "domain": "western-angles",
        "sources": [
            {
                "name": "NASA JPL Horizons",
                "url": horizons.URL,
                "command": "python -m benchmark pull western-angles (OBSERVER tables: QUANTITIES 7 "
                "at the birthplace; QUANTITIES 2 and 31 of geocentric bodies)",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "licence": horizons.LICENCE,
                "method": "Local apparent sidereal time at the birthplace at the chart instant "
                "converted to UT, and the true obliquity of date solved from the apparent "
                "equatorial and ecliptic coordinates of one direction. Horizons converts UTC to "
                "UT1 with its Earth orientation table before computing sidereal time; before "
                "1962 it reads the time as UT1.",
                "notes": "Frame IAU 1976/1980 as Horizons prints it. Charts at or beyond the "
                "polar circles are skipped because Placidus is undefined there: "
                + (", ".join(skipped) or "none")
                + ".",
            },
            {
                "name": "Spherical astronomy formulas",
                "citation": "Jean Meeus, Astronomical Algorithms, first edition, Willmann-Bell, "
                "1991: chapter 12 eq. 12.1 to 12.4 and 12.9, chapter 14 eq. 14.1. Placidus de "
                "Titis, Tabulae Primi Mobilis, 1657, for the house definition.",
                "command": "python -m benchmark pull western-angles",
                "retrieved": datetime.now(UTC).date().isoformat(),
                "licence": "Formulas and definitions only; no text reproduced",
                "method": "Midheaven: the ecliptic longitude whose right ascension is the "
                "sidereal angle. Ascendant: the rising ecliptic point on the horizon. Placidus "
                "cusps 11 and 12: the ecliptic points one and two thirds of their own diurnal "
                "semi arc east of the meridian; cusps 2 and 3: two and one thirds of their own "
                "nocturnal semi arc west of the lower meridian, each by fixed point iteration "
                "to 1e-10 degrees; cusps 5, 6, 8 and 9 are their opposites. Seven decimal "
                "degrees.",
            },
        ],
        "families": [
            {
                "label": "Ascendant, Midheaven and Placidus cusps",
                "quantities": [
                    "Ascendant",
                    "Midheaven",
                    "Cusp 2",
                    "Cusp 3",
                    "Cusp 5",
                    "Cusp 6",
                    "Cusp 8",
                    "Cusp 9",
                    "Cusp 11",
                    "Cusp 12",
                ],
            },
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": BAND_ARCSEC,
                "unit": "arcsec",
                "why": "A vendor-neutral pass bar, not sized to any one API, the same as the "
                "planets. The sky turns 15 arcseconds per second of time, so the bar admits two "
                "good implementations that differ by milliarcseconds in their precession and "
                "nutation model, or by the under one second between UTC and UT1, and fails a "
                "wrong timezone resolution, mean in place of true obliquity at high latitude, a "
                "sign or quadrant slip, or a different house system. Angles and cusps magnify a "
                "time error at high latitude, so read the per quantity "
                "maxima for regressions.",
            }
        ],
        "cases": cases,
    }
