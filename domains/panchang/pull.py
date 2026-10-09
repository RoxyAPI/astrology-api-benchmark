"""Rebuild ``references.json``: tithi, yoga, karana and vara by definition, sunrise from USNO.

The three instant limbs are fixed by the apparent geocentric ecliptic longitudes of the Sun and
Moon at the instant, read from NASA JPL Horizons. Surya Siddhanta, chapter 2 (E. Burgess
translation, Journal of the American Oriental Society, volume 6, 1860):

- Tithi: the Moon longitude minus the Sun longitude, divided by 12 degrees (verse 66, pages 236
  and 237). Thirty tithis fill the lunar month, so the number runs 1 to 30.
- Karana: half a tithi, 6 degrees of that difference (verses 67 to 69, pages 237 and 238). Slot 1
  is the fixed Kimstughna, slots 2 to 57 cycle the seven movable karanas Bava, Balava, Kaulava,
  Taitila, Gara, Vanija, Vishti eight times, slots 58 to 60 are the other fixed ones.
- Yoga: the sum of the two sidereal longitudes, divided by 13 degrees 20 minutes, 800 arcminutes
  (verse 65, pages 235 and 236). The sum needs the sidereal frame, so it carries twice the
  ayanamsa; the difference does not, the ayanamsa cancelling.

The karana number is the position in the list the API publishes: movable 1 to 7 in the order of
the text, then Shakuni 8 and Kimstughna 11. The other two fixed karanas, Naga and Chatushpada,
fill the two halves of the Amavasya tithi, and the text and common usage order them differently,
so a case that falls in them carries no karana.

Vara is the weekday of the civil date whose sunrise opens the Hindu day. The text counts the
civil day from sunrise to sunrise (chapter 1 verse 13 and the note, page 151) and names the day
for its lord counted from the Sun (chapter 1 verses 51 and 52, pages 175 and 176), Sunday first.

The ayanamsa is the Lahiri one, recomputed from its published definition exactly as the vedic
domain does and never read from a program: 23 deg 15 min 00.658 sec at 0h TT on 21 March 1956
(Report of the Calendar Reform Committee, Government of India, 1955, recommendations for the
religious calendar, item 7, pages 7 and 8), made mean, carried by the IERS Conventions 2010
general precession in longitude and made true again with the IAU 2000A nutation in longitude of
the instant. The Positional Astronomy Centre, Kolkata, tabulates the sidereal Sun and Moon at 0h
TT; the recomputation reproduces three of its dates and a test checks that the limbs follow.

Sunrise comes from the USNO Astronomical Applications API (one day of Sun and Moon data), which
defines it as the upper limb on a level horizon under 34 arcminutes of refraction and prints
whole minutes in the local zone given. Cases carry a fixed UTC offset in hours, never a zone name.

Run it with ``uv run python -m benchmark pull panchang``; nothing else contacts a source.
"""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import UTC, date, datetime, timedelta
from typing import Any

from benchmark import horizons
from benchmark.fetch import get_text

IERS_NUTATION_URL = "https://iers-conventions.obspm.fr/content/chapter5/additional_info/tab5.3a.txt"
REPORT_URL = "https://archive.org/details/calendar_reform_comittee_report"
PAC_URL = "https://packolkata.imd.gov.in/download/nirlon/nlongitude.htm"
SURYA_SIDDHANTA_URL = "https://archive.org/details/jstor-592174"
USNO_URL = "https://aa.usno.navy.mil/api/rstt/oneday"
USNO_DOC_URL = "https://aa.usno.navy.mil/data/api"
USNO_DEFINITION_URL = "https://aa.usno.navy.mil/faq/RST_defs"

SUN = "10"
MOON = "301"

ARCSEC_PER_RADIAN = 180 * 3600 / math.pi
J2000 = 2451545.0
UNIX_EPOCH_JD = 2440587.5
EPOCH_JD = 2435553.5
"""1956 March 21, 0h TT, the Lahiri epoch."""
EPOCH_AYANAMSA_ARCSEC = 23 * 3600 + 15 * 60 + 0.658
"""23 deg 15 min 00.658 sec, the true ayanamsa at the epoch."""

TITHI_SPAN = 12.0
KARANA_SPAN = 6.0
YOGA_SPAN = 40 / 3
VARAS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
"""Indexed by ``date.weekday()``."""

KIMSTUGHNA = 11
SHAKUNI = 8
MOVABLE = 7
FIRST_SHAKUNI_SLOT = 57
"""Zero based half tithi slot of Shakuni, the 58th half of the lunar month."""
UNORDERED_SLOTS = (58, 59)
"""Naga and Chatushpada: ordered differently by the text and by common usage, so never expected."""

# The Delaunay arguments of IERS Conventions 2010 equation 5.43: degrees at J2000, then arcseconds
# per Julian century to the first, second, third and fourth power.
DELAUNAY = (
    (134.96340251, 1717915923.2178, 31.8792, 0.051635, -0.0002447),
    (357.52910918, 129596581.0481, -0.5532, 0.000136, -0.00001149),
    (93.27209062, 1739527262.8478, -12.7512, -0.001037, 0.00000417),
    (297.85019547, 1602961601.2090, -6.3706, 0.006593, -0.00003169),
    (125.04455501, -6962890.5431, 7.4722, 0.007702, -0.00005939),
)
# The planetary arguments of equation 5.44, radians and radians per Julian century.
PLANETARY = (
    (4.402608842, 2608.7903141574),
    (3.176146697, 1021.3285546211),
    (1.753470314, 628.3075849991),
    (6.203480913, 334.0612426700),
    (0.599546497, 52.9690962641),
    (0.874016757, 21.3299104960),
    (5.481293872, 7.4781598567),
    (5.311886287, 3.8133035638),
)
PRECESSION_RADIANS = (0.02438175, 0.00000538691)

# Positional Astronomy Centre, Kolkata: nirayana (Lahiri sidereal) longitudes of the Sun and Moon
# at 0h TT as its per-body tables print them, degrees, minutes and seconds, transcribed from the
# PDFs linked at PAC_URL. The API is called at the UT second nearest 0h TT.
PAC_DATES = ("2026-01-01", "2026-04-15", "2026-07-01")
PAC_LONGITUDES: dict[str, dict[str, tuple[int, int, float]]] = {
    "2026-01-01": {"Sun": (256, 20, 45.4864), "Moon": (42, 28, 54.8589)},
    "2026-04-15": {"Sun": (0, 48, 50.4128), "Moon": (327, 36, 43.6938)},
    "2026-07-01": {"Sun": (74, 58, 21.1991), "Moon": (265, 58, 42.3498)},
}

# (id, local date and time, latitude, longitude, UTC offset in hours, why the case is here).
# Latitudes and longitudes in decimal degrees, east and north positive.
CASES: tuple[tuple[str, str, float, float, float, str], ...] = (
    ("mumbai-noon", "2026-03-08 12:00:00", 19.076, 72.8777, 5.5, "an ordinary day"),
    ("new-york-evening", "2026-11-01 19:30:00", 40.7128, -74.006, -5, "west longitude, Sunday"),
    ("sydney-morning", "2026-01-15 08:15:00", -33.8688, 151.2093, 11, "south latitude, summer"),
    ("honolulu-night", "2026-08-02 23:40:00", 21.3099, -157.8581, -10, "far west, late evening"),
    ("reykjavik-solstice", "2026-06-21 12:00:00", 64.1466, -21.9426, 0, "high latitude, midsummer"),
    ("tromso-may", "2026-05-12 12:00:00", 69.6492, 18.9553, 2, "beyond the polar circle"),
    ("delhi-purnima", "2026-10-26 02:00:00", 28.6139, 77.209, 5.5, "tithi 15, the full Moon"),
    ("delhi-shakuni", "2026-11-08 05:00:00", 28.6139, 77.209, 5.5, "the fixed karana Shakuni"),
    ("delhi-amavasya", "2026-11-09 12:00:00", 28.6139, 77.209, 5.5, "tithi 30, no karana expected"),
    ("delhi-kimstughna", "2026-11-09 21:00:00", 28.6139, 77.209, 5.5, "fixed karana Kimstughna"),
)  # fmt: skip

# Instants placed just past a boundary of one limb: (id, quantity, local date and time, latitude,
# longitude, UTC offset). Found with ``find_boundary``; ``pull`` fails when one leaves its margin.
BOUNDARY_CASES: tuple[tuple[str, str, str, float, float, float], ...] = (
    ("mumbai-tithi-edge", "tithi", "2026-02-20 14:40:11", 19.076, 72.8777, 5.5),
    ("london-karana-edge", "karana", "2026-10-28 09:08:02", 51.5074, -0.1278, 0),
    ("tokyo-yoga-edge", "yoga", "2026-10-31 00:12:18", 35.6762, 139.6503, 9),
)

TITHI_MARGIN_ARCSEC = 45
"""A tithi or karana boundary case sits closer than this past its edge: about 90 seconds."""
YOGA_MARGIN_ARCSEC = 30
"""A yoga boundary case sits closer than this past its edge. The edge moves by twice an ayanamsa
error, so an ayanamsa 17.5 arcseconds higher (another Lahiri revision) puts the case back across."""

SUNRISE_BAND_SECONDS = 90

FAMILIES: list[dict[str, Any]] = [
    {"label": "Tithi, yoga, karana and vara", "quantities": ["tithi", "yoga", "karana", "vara"]},
    {"label": "Sunrise", "quantities": ["sunrise"]},
]

type NutationTerm = tuple[float, float, tuple[int, ...], bool]
"""In phase and out of phase amplitudes in microarcseconds, argument multipliers, times t."""


def parse_nutation_table(text: str) -> list[NutationTerm]:
    """The rows of IERS Table 5.3a: the j = 0 block, then the j = 1 block that scales with t."""
    terms: list[NutationTerm] = []
    secular = None
    for line in text.splitlines():
        if block := re.match(r"\s*j = (\d)", line):
            secular = block.group(1) == "1"
            continue
        fields = line.split()
        if secular is not None and len(fields) == 17 and fields[0].isdigit():
            multipliers = tuple(int(f) for f in fields[3:])
            terms.append((float(fields[1]), float(fields[2]), multipliers, secular))
    if len(terms) < 1300:
        raise ValueError(f"IERS Table 5.3a: parsed {len(terms)} terms, expected the full series")
    return terms


def julian_centuries(jd: float) -> float:
    return (jd - J2000) / 36525.0


def general_precession_arcsec(jd: float) -> float:
    t = julian_centuries(jd)
    linear, quadratic = PRECESSION_RADIANS
    return (linear * t + quadratic * t * t) * ARCSEC_PER_RADIAN


def nutation_in_longitude_arcsec(terms: list[NutationTerm], jd: float) -> float:
    t = julian_centuries(jd)
    powers = (1.0, t, t * t, t**3, t**4)
    arguments = [
        math.radians(c[0])
        + sum(k * p for k, p in zip(c[1:], powers[1:], strict=True)) / ARCSEC_PER_RADIAN
        for c in DELAUNAY
    ]
    arguments += [base + rate * t for base, rate in PLANETARY]
    arguments.append(general_precession_arcsec(jd) / ARCSEC_PER_RADIAN)
    total = 0.0
    for in_phase, out_of_phase, multipliers, secular in terms:
        angle = sum(k * a for k, a in zip(multipliers, arguments, strict=True))
        term = in_phase * math.sin(angle) + out_of_phase * math.cos(angle)
        total += term * t if secular else term
    return total * 1e-6


def lahiri_ayanamsa(terms: list[NutationTerm], jd: float) -> float:
    """The true Lahiri ayanamsa in degrees at Julian date ``jd``."""
    mean_at_epoch = EPOCH_AYANAMSA_ARCSEC - nutation_in_longitude_arcsec(terms, EPOCH_JD)
    precession = general_precession_arcsec(jd) - general_precession_arcsec(EPOCH_JD)
    return (mean_at_epoch + precession + nutation_in_longitude_arcsec(terms, jd)) / 3600


def julian_date(instant: datetime) -> float:
    return instant.replace(tzinfo=UTC).timestamp() / 86400 + UNIX_EPOCH_JD


def elongation(sun: float, moon: float) -> float:
    """Moon minus Sun longitude, degrees from 0 to 360; the frame and the ayanamsa cancel."""
    return (moon - sun) % 360


def yoga_sum(sidereal_sun: float, sidereal_moon: float) -> float:
    return (sidereal_sun + sidereal_moon) % 360


def tithi(elong: float) -> int:
    """1 for Shukla Pratipada to 30 for Amavasya."""
    return int(elong // TITHI_SPAN) + 1


def yoga(total: float) -> int:
    """1 for Vishkumbha to 27 for Vaidhriti."""
    return int(total // YOGA_SPAN) + 1


def karana_slot(elong: float) -> int:
    """Zero based half tithi of the lunar month, 0 to 59."""
    return int(elong // KARANA_SPAN)


def karana(slot: int) -> int | None:
    """Number in the API list: 1 to 7 movable in text order, Shakuni 8, Kimstughna 11.

    None for Naga and Chatushpada, whose order the sources do not agree on.
    """
    if slot == 0:
        return KIMSTUGHNA
    if slot == FIRST_SHAKUNI_SLOT:
        return SHAKUNI
    if slot in UNORDERED_SLOTS:
        return None
    return (slot - 1) % MOVABLE + 1


def vara(day: str) -> str:
    """English weekday of the civil date whose sunrise opens the Hindu day."""
    return VARAS[date.fromisoformat(day).weekday()]


def offset_text(hours: float) -> str:
    sign = "-" if hours < 0 else "+"
    minutes = round(abs(hours) * 60)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


def local_to_utc(local: str, offset_hours: float) -> datetime:
    return datetime.fromisoformat(local) - timedelta(hours=offset_hours)


def input_body(
    local: str, latitude: float, longitude: float, offset_hours: float
) -> dict[str, Any]:
    stamp = datetime.fromisoformat(local)
    return {
        "date": stamp.strftime("%Y-%m-%d"),
        "time": stamp.strftime("%H:%M:%S"),
        "latitude": latitude,
        "longitude": longitude,
        "timezone": offset_hours,
    }


def sky_at(start: datetime, time_scale: str = "UT") -> tuple[float, float, float]:
    """Apparent ecliptic longitudes of date of the Sun and Moon, and TDB minus UT in seconds."""
    extra = {"TIME_TYPE": f"'{time_scale}'", "ANG_FORMAT": "'DEG'", "EXTRA_PREC": "'YES'"}
    longitudes: list[float] = []
    delta_t = 0.0
    for command in (SUN, MOON):
        # The row ends with TDB minus UT, then the ecliptic longitude and latitude.
        row = horizons.first_row(horizons.observer(command, start, "30,31", extra=extra))
        delta_t, longitude, _ = (float(f) for f in row[-3:])
        longitudes.append(longitude)
    return longitudes[0], longitudes[1], delta_t


def limbs(
    terms: list[NutationTerm], start: datetime, time_scale: str = "UT"
) -> tuple[dict[str, int], float, float]:
    """The three instant limbs at a UT instant, with the elongation and the yoga sum behind them."""
    sun, moon, _ = sky_at(start, time_scale)
    ayanamsa = lahiri_ayanamsa(terms, julian_date(start))
    elong = elongation(sun, moon)
    total = yoga_sum(sun - ayanamsa, moon - ayanamsa)
    values: dict[str, int] = {"tithi": tithi(elong), "yoga": yoga(total)}
    if (number := karana(karana_slot(elong))) is not None:
        values["karana"] = number
    return values, elong, total


def usno_sunrise(day: str, latitude: float, longitude: float, offset_hours: float) -> str:
    """The Rise entry of USNO one day Sun data, as an ISO 8601 local time with its offset."""
    text = get_text(
        USNO_URL,
        {"date": day, "coords": f"{latitude},{longitude}", "tz": f"{offset_hours:g}"},
    )
    entries = json.loads(text)["properties"]["data"]["sundata"]
    rise = next((e["time"] for e in entries if e["phen"] == "Rise"), None)
    if rise is None:
        raise ValueError(f"USNO prints no sunrise for {day} at {latitude}, {longitude}")
    return f"{day}T{rise}:00{offset_text(offset_hours)}"


def find_boundary(
    terms: list[NutationTerm], quantity: str, around: datetime, margin_arcsec: float
) -> datetime:
    """The first whole UT second at least ``margin_arcsec`` past the boundary nearest ``around``.

    The elongation (tithi, karana) or the yoga sum moves at a steady rate over a few minutes, so
    two Horizons rows a minute apart give the rate and the boundary by one linear step.
    """
    span = {"tithi": TITHI_SPAN, "karana": KARANA_SPAN, "yoga": YOGA_SPAN}[quantity]
    _, elong_a, total_a = limbs(terms, around)
    _, elong_b, total_b = limbs(terms, around + timedelta(seconds=60))
    here, there = (total_a, total_b) if quantity == "yoga" else (elong_a, elong_b)
    rate = ((there - here + 180) % 360 - 180) / 60
    past = (here % span) / rate
    boundary = around - timedelta(seconds=past)
    return boundary + timedelta(seconds=math.ceil(margin_arcsec / 3600 / rate))


def document(cases: list[dict[str, Any]], cross_checks: list[dict[str, Any]]) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    instant = ["tithi", "yoga", "karana"]
    return {
        "format": 1,
        "domain": "panchang",
        "sources": [
            {
                "name": "NASA JPL Horizons",
                "url": horizons.URL,
                "command": "python -m benchmark pull panchang (OBSERVER tables: QUANTITIES 30 "
                "and 31 of the geocentric Sun and Moon)",
                "retrieved": today,
                "licence": horizons.LICENCE,
                "method": "Apparent geocentric ecliptic longitude of date of the Sun and Moon "
                "at the case instant. Elongation for tithi and karana, sidereal sum for yoga.",
                "applies_to": instant,
            },
            {
                "name": "Surya Siddhanta, Burgess translation",
                "url": SURYA_SIDDHANTA_URL,
                "citation": "Translation of the Surya-Siddhanta, a Text-Book of Hindu Astronomy, "
                "by Ebenezer Burgess, Journal of the American Oriental Society, volume 6, 1860: "
                "chapter 2 verses 65 to 69 (pages 235 to 238) for yoga, tithi and karana; "
                "chapter 1 verse 13 note (page 151) and verses 51 and 52 (pages 175 and 176) for "
                "the day counted from sunrise and named for its lord",
                "retrieved": today,
                "licence": "Classical text in an openly digitised 1860 translation; the rules "
                "are cited, no text is reproduced",
                "method": "Tithi is the elongation in units of 12 degrees, karana in units of "
                "6 degrees, yoga the sidereal sum in units of 13 degrees 20 minutes, vara the "
                "weekday of the civil date whose sunrise opens the day.",
                "applies_to": [*instant, "vara"],
            },
            {
                "name": "Lahiri ayanamsa, Calendar Reform Committee definition",
                "url": REPORT_URL,
                "citation": "Report of the Calendar Reform Committee, Government of India, "
                "Council of Scientific and Industrial Research, 1955: Recommendations for the "
                "religious calendar, item 7, pages 7 and 8; general precession, page 209",
                "retrieved": today,
                "licence": "Government of India publication; the definition is cited, no text "
                "is reproduced",
                "method": "23 deg 15 min on 21 March 1956, growing with the general precession "
                "in longitude. Held at 23 deg 15 min 00.658 sec at 0h TT as a true ayanamsa, "
                "carried by IERS Conventions 2010 equation 5.44 and the IAU 2000A nutation in "
                "longitude (Table 5.3a, downloaded on each pull). Enters yoga only.",
                "applies_to": ["yoga"],
            },
            {
                "name": "Positional Astronomy Centre, Kolkata",
                "url": PAC_URL,
                "retrieved": today,
                "licence": "Government of India data, India Meteorological Department; values "
                "cited with attribution",
                "method": "Published nirayana longitudes of the Sun and Moon at 0h TT, "
                "transcribed for three dates as cross checks: the limbs they give must equal "
                "the recomputed ones.",
                "applies_to": instant,
            },
            {
                "name": "US Naval Observatory Astronomical Applications API",
                "url": USNO_DOC_URL,
                "citation": f"Complete Sun and Moon Data for One Day; rise and set defined at "
                f"{USNO_DEFINITION_URL}",
                "command": "python -m benchmark pull panchang (GET rstt/oneday with date, coords "
                "and tz in hours)",
                "retrieved": today,
                "licence": "US Government data, public domain; cite USNO",
                "method": "The Rise entry of the Sun data, in the local zone given. Sunrise is "
                "the upper limb of the Sun on a level sea horizon under 34 arcminutes of "
                "refraction. The service prints whole minutes.",
                "applies_to": ["sunrise"],
            },
        ],
        "tolerances": [
            {
                "applies_to": ["sunrise"],
                "value": SUNRISE_BAND_SECONDS,
                "unit": "seconds",
                "why": "The reference prints whole minutes and so does a typical response, so "
                "two exact values can differ by up to a minute through rounding alone; the "
                "half minute beyond covers the difference between two good ephemeris "
                "implementations of the same upper limb and 34 arcminute definition. A different "
                "limb (about 4 minutes at mid latitudes) or no refraction (about 2 to 3) fails.",
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": "Tithi, yoga, karana and vara are discrete: a value is the definition "
                "applied to the Sun and Moon longitudes, or the weekday of the sunrise date, or "
                "it is not.",
            },
        ],
        "cases": cases,
        "cross_checks": cross_checks,
        "families": FAMILIES,
    }


def published_limbs(published: dict[str, tuple[int, int, float]]) -> dict[str, int]:
    """The limbs the published sidereal Sun and Moon give; the frame is already sidereal."""
    sun, moon = (d + m / 60 + sec / 3600 for d, m, sec in (published["Sun"], published["Moon"]))
    values = {"tithi": tithi(elongation(sun, moon)), "yoga": yoga(yoga_sum(sun, moon))}
    if (number := karana(karana_slot(elongation(sun, moon)))) is not None:
        values["karana"] = number
    return values


def day_case(case_id: str, body: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    return {"id": case_id, "input": body, "expected": expected}


def pull() -> dict[str, Any]:
    terms = parse_nutation_table(get_text(IERS_NUTATION_URL))
    cases: list[dict[str, Any]] = []
    for case_id, local, latitude, longitude, offset, _ in CASES:
        print(case_id, file=sys.stderr)
        body = input_body(local, latitude, longitude, offset)
        limb_values, _, _ = limbs(terms, local_to_utc(local, offset))
        values: dict[str, Any] = dict(limb_values)
        values["vara"] = vara(body["date"])
        values["sunrise"] = usno_sunrise(body["date"], latitude, longitude, offset)
        cases.append(day_case(case_id, body, values))
    for case_id, quantity, local, latitude, longitude, offset in BOUNDARY_CASES:
        print(case_id, file=sys.stderr)
        start = local_to_utc(local, offset)
        body = input_body(local, latitude, longitude, offset)
        limb_values, elong, total = limbs(terms, start)
        values = dict[str, Any](limb_values)
        span, position = {
            "tithi": (TITHI_SPAN, elong),
            "karana": (KARANA_SPAN, elong),
            "yoga": (YOGA_SPAN, total),
        }[quantity]
        limit = YOGA_MARGIN_ARCSEC if quantity == "yoga" else TITHI_MARGIN_ARCSEC
        if not 0 < position % span * 3600 < limit:
            raise ValueError(f"{case_id}: no longer just past a {quantity} boundary")
        values["vara"] = vara(body["date"])
        values["sunrise"] = usno_sunrise(body["date"], latitude, longitude, offset)
        cases.append(day_case(case_id, body, values))
    cross_checks: list[dict[str, Any]] = []
    for day in PAC_DATES:
        case_id = f"pac-{day}"
        print(case_id, file=sys.stderr)
        midnight_tt = datetime.fromisoformat(day)
        delta_t = sky_at(midnight_tt, "TT")[2]
        local = (midnight_tt - timedelta(seconds=round(delta_t))).isoformat(sep=" ")
        body = input_body(local, 23.1765, 75.7885, 0)
        values, _, _ = limbs(terms, midnight_tt, "TT")
        cases.append(day_case(case_id, body, values))
        cross_checks.append(
            {
                "id": case_id,
                "source": "Positional Astronomy Centre, Kolkata",
                "input": body,
                "expected": published_limbs(PAC_LONGITUDES[day]),
            }
        )
    return document(cases, cross_checks)
