"""Rebuild ``references.json``: Lahiri sidereal positions from NASA JPL Horizons and definitions.

The sidereal longitude of a graha is its apparent geocentric ecliptic longitude of date from
Horizons minus the Lahiri ayanamsa at the same instant. The ayanamsa is recomputed here from its
published definition, never read from a program:

- The Calendar Reform Committee fixed it at 23 deg 15 min on 21 March 1956, growing thereafter
  with the general precession in longitude (Report of the Calendar Reform Committee, Government of
  India, 1955, Recommendations for the religious calendar, item 7, pages 7 and 8).
- The Positional Astronomy Centre, Kolkata, which publishes the Indian Astronomical Ephemeris,
  tabulates sidereal longitudes of the Sun, Moon and planets at 0h TT. They are reproduced to
  under half an arcsecond when the epoch value is the refined 23 deg 15 min 00.658 sec at 1956
  March 21, 0h TT, read as a true ayanamsa: measured from the true equinox of date, so carrying
  the nutation in longitude. With the round 1955 value they sit 0.8 arcseconds away, and without
  the nutation term up to 18. Three of its dates are cases here and a test pins the agreement.

So ``ayanamsa(t) = A0 - dpsi(t0) + pA(t) - pA(t0) + dpsi(t)``: the epoch value made mean, carried
by the general precession in longitude ``pA`` (IERS Conventions 2010, equation 5.44, F14) and
made true again with the nutation in longitude ``dpsi`` of the instant (IAU 2000A, IERS
Conventions 2010 Table 5.3a, downloaded on each pull). Precession and nutation take Julian
centuries from J2000 of the instant on the chart time scale; the minute between UT and TT moves
the ayanamsa by under a thousandth of an arcsecond.

Nakshatra, pada and navamsa follow from the sidereal longitude by their definitions in
Brihat Parasara Hora Sastra (R. Santhanam translation, Ranjan Publications): 27 nakshatras of 13
deg 20 min and four padas of 3 deg 20 min each (chapter 46, volume 2 page 509), navamsa counted from
the sign itself for a movable sign, from the 9th for a fixed sign and from the 5th for a dual sign
(chapter 6 sloka 12, volume 1 page 72). The Vimshottari dasha at birth follows chapter 46
slokas 12 to 16 (volume 2 pages 507 to 509): the lord from the Moon nakshatra counted from
Krittika, and the balance as the unexpired part of that nakshatra times the years of its lord,
taken by the longitude of the Moon as the notes of the translator give it, in Julian years of
365.25 days.

The Lagna is the rising ecliptic point recomputed from Horizons sidereal time at the birthplace and
the true obliquity of date (Meeus, Astronomical Algorithms, eq. 12.9), less the same ayanamsa.

Run it with ``uv run python -m benchmark pull vedic``; nothing else in the repo contacts a source.
"""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from benchmark import horizons
from benchmark.fetch import get_text
from benchmark.schema import load_charts

IERS_NUTATION_URL = "https://iers-conventions.obspm.fr/content/chapter5/additional_info/tab5.3a.txt"
REPORT_URL = "https://archive.org/details/calendar_reform_comittee_report"
PAC_URL = "https://packolkata.imd.gov.in/download/nirlon/nlongitude.htm"
BPHS_URL = "https://archive.org/details/BPHSEnglish"

# Sun to Mars by their own Horizons centres, Jupiter and Saturn by the system barycentres the
# planetary ephemeris integrates, as in the western-planets domain.
GRAHA_CODES: dict[str, str] = {
    "Sun": "10",
    "Moon": "301",
    "Mars": "499",
    "Mercury": "199",
    "Jupiter": "5",
    "Venus": "299",
    "Saturn": "6",
}

ARCSEC_PER_RADIAN = 180 * 3600 / math.pi
J2000 = 2451545.0
UNIX_EPOCH_JD = 2440587.5
EPOCH_JD = 2435553.5
"""1956 March 21, 0h TT, the Lahiri epoch."""
EPOCH_AYANAMSA_ARCSEC = 23 * 3600 + 15 * 60 + 0.658
"""23 deg 15 min 00.658 sec, the true ayanamsa at the epoch."""

NAKSHATRA_SPAN = 40 / 3
PADA_SPAN = 10 / 3
JULIAN_YEAR_DAYS = 365.25
SIGNS = (
    "aries", "taurus", "gemini", "cancer", "leo", "virgo",
    "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces",
)  # fmt: skip
DASHA_LORDS = ("Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury", "Ketu", "Venus")
"""Vimshottari lords in order, the first ruling Krittika, the third nakshatra."""
DASHA_YEARS = {
    "Sun": 6, "Moon": 10, "Mars": 7, "Rahu": 18, "Jupiter": 16,
    "Saturn": 19, "Mercury": 17, "Ketu": 7, "Venus": 20,
}  # fmt: skip
KRITTIKA = 3

# The Delaunay arguments of IERS Conventions 2010 equation 5.43: degrees at J2000, then arcseconds
# per Julian century to the first, second, third and fourth power.
DELAUNAY = (
    (134.96340251, 1717915923.2178, 31.8792, 0.051635, -0.0002447),
    (357.52910918, 129596581.0481, -0.5532, 0.000136, -0.00001149),
    (93.27209062, 1739527262.8478, -12.7512, -0.001037, 0.00000417),
    (297.85019547, 1602961601.2090, -6.3706, 0.006593, -0.00003169),
    (125.04455501, -6962890.5431, 7.4722, 0.007702, -0.00005939),
)
# The planetary arguments of equation 5.44, radians and radians per Julian century; the last row
# is pA, the general precession in longitude, with its quadratic term.
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

# Positional Astronomy Centre, Kolkata: nirayana (Lahiri sidereal) longitudes at 0h TT as its
# per-body tables print them, degrees, minutes and seconds, transcribed from the PDFs linked at
# PAC_URL. The API is called at the UT second nearest 0h TT, from the Horizons delta T.
PAC_DATES = ("2026-01-01", "2026-04-15", "2026-07-01")
PAC_LONGITUDES: dict[str, dict[str, tuple[int, int, float]]] = {
    "2026-01-01": {
        "Sun": (256, 20, 45.4864),
        "Moon": (42, 28, 54.8589),
        "Mars": (258, 27, 56.6724),
        "Mercury": (244, 25, 42.9394),
        "Jupiter": (87, 8, 9.4454),
        "Venus": (254, 59, 1.2244),
        "Saturn": (331, 56, 43.6184),
    },
    "2026-04-15": {
        "Sun": (0, 48, 50.4128),
        "Moon": (327, 36, 43.6938),
        "Mars": (339, 48, 13.4418),
        "Mercury": (335, 34, 35.3508),
        "Jupiter": (82, 44, 17.4468),
        "Venus": (24, 35, 28.4748),
        "Saturn": (343, 2, 38.8248),
    },
    "2026-07-01": {
        "Sun": (74, 58, 21.1991),
        "Moon": (265, 58, 42.3498),
        "Mars": (37, 19, 42.3311),
        "Mercury": (91, 57, 58.8431),
        "Jupiter": (95, 55, 55.1041),
        "Venus": (115, 57, 45.3991),
        "Saturn": (349, 57, 26.0451),
    },
}

# UT instants where a graha sits a few arcseconds past a pada boundary while the nutation in
# longitude is near its 18 arcsecond extreme: a frame that drops the nutation term, or one a tenth
# of a degree off, moves the graha back across and changes its pada and navamsa. The Moon case
# also changes its nakshatra and so the dasha lord. Found with the functions below.
BOUNDARY_CASES: dict[str, tuple[str, datetime]] = {
    "sun-pada-edge": ("Sun", datetime(2020, 5, 21, 9, 55)),
    "moon-nakshatra-edge": ("Moon", datetime(2001, 11, 10, 22, 11)),
}
BOUNDARY_MARGIN_ARCSEC = 20
"""A boundary case graha sits closer than this past its pada boundary."""

MIN_CONDITIONING = 0.3
"""Least distance from the equinox line, as a sine, for a graha to fix the obliquity well."""
OBLIQUITY_AGREEMENT_ARCSEC = 0.01
"""Two well placed grahas agree to the printed digits; more than this is a parsing fault."""

LONGITUDE_DECIMALS = 7
BALANCE_DECIMALS = 3
PLANET_BAND_ARCSEC = 36
MOON_BAND_ARCSEC = 72
LAGNA_BAND_ARCSEC = 36
AYANAMSA_BAND_ARCSEC = 3
BALANCE_BAND_DAYS = 1

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


def nakshatra(sidereal: float) -> int:
    """1 for Ashwini to 27 for Revati."""
    return int(sidereal // NAKSHATRA_SPAN) + 1


def pada(sidereal: float) -> int:
    return int(sidereal // PADA_SPAN) % 4 + 1


def navamsa(sidereal: float) -> str:
    """Navamsa sign: counted from the sign itself if movable, the 9th if fixed, the 5th if dual."""
    sign = int(sidereal // 30)
    start = sign + (0, 8, 4)[sign % 3]
    return SIGNS[(start + int(sidereal % 30 // PADA_SPAN)) % 12]


def dasha_lord(sidereal_moon: float) -> str:
    return DASHA_LORDS[(nakshatra(sidereal_moon) - KRITTIKA) % 9]


def dasha_balance_days(sidereal_moon: float) -> float:
    """Unexpired part of the birth nakshatra times the years of its lord, in days."""
    remaining = 1 - (sidereal_moon % NAKSHATRA_SPAN) / NAKSHATRA_SPAN
    return remaining * DASHA_YEARS[dasha_lord(sidereal_moon)] * JULIAN_YEAR_DAYS


def julian_date(instant: datetime) -> float:
    return instant.timestamp() / 86400 + UNIX_EPOCH_JD


def expected_values(sidereal: dict[str, float], ayanamsa: float) -> dict[str, Any]:
    """The reference values of one case; ``sidereal`` may carry the Lagna beside the grahas."""
    values: dict[str, Any] = {"ayanamsa": round(ayanamsa, LONGITUDE_DECIMALS)}
    for point, longitude in sidereal.items():
        values[point] = round(longitude, LONGITUDE_DECIMALS)
        values[f"{point} nakshatra"] = nakshatra(longitude)
        values[f"{point} pada"] = pada(longitude)
        values[f"{point} navamsa"] = navamsa(longitude)
    values["dasha lord"] = dasha_lord(sidereal["Moon"])
    values["dasha balance"] = round(dasha_balance_days(sidereal["Moon"]), BALANCE_DECIMALS)
    return values


def obliquity_from(
    right_ascension: float, declination: float, longitude: float, latitude: float
) -> tuple[float, float]:
    """True obliquity from one direction given in both frames of date, and its conditioning.

    Meeus eq. 12.1 and 12.2 rotate the equatorial direction about the equinox line by the
    obliquity: (cos(dec) sin(ra), sin(dec)) turns into (cos(lat) sin(lon), sin(lat)), so the
    obliquity is the difference of their polar angles. The conditioning is the length of the
    first pair, the sine of the distance from the equinox line.
    """
    a, d, lon, lat = (math.radians(x) for x in (right_ascension, declination, longitude, latitude))
    x, y = math.cos(d) * math.sin(a), math.sin(d)
    turn = math.atan2(y, x) - math.atan2(math.sin(lat), math.cos(lat) * math.sin(lon))
    return math.degrees((turn + math.pi) % (2 * math.pi) - math.pi), math.hypot(x, y)


def ascendant(sidereal_time: float, obliquity: float, latitude: float) -> float:
    """Tropical longitude of the rising ecliptic point (Meeus eq. 12.9, rising root)."""
    t, e, p = (math.radians(x) for x in (sidereal_time, obliquity, latitude))
    rising = math.atan2(math.cos(t), -(math.sin(t) * math.cos(e) + math.tan(p) * math.sin(e)))
    return math.degrees(rising) % 360


def local_sidereal_time(start: datetime, latitude: float, longitude: float) -> float:
    """Local apparent sidereal time at the site, degrees; Horizons applies UT1 itself."""
    text = horizons.observer(
        "10",
        start,
        "7",
        center="coord@399",
        extra={
            "COORD_TYPE": "'GEODETIC'",
            "SITE_COORD": f"'{longitude},{latitude},0'",
            "EXTRA_PREC": "'YES'",
        },
    )
    hours, minutes, seconds = (float(f) for f in horizons.first_row(text)[-3:])
    return (hours + minutes / 60 + seconds / 3600) * 15


@dataclass(frozen=True, slots=True)
class Sky:
    """What one Horizons pass gives at an instant."""

    tropical: dict[str, float]
    """Apparent ecliptic longitude of date per graha, degrees."""
    delta_t: float
    """TDB minus UT, seconds."""
    obliquity: float
    """True obliquity of date, degrees, from the best placed graha."""


def sky_at(start: datetime, time_scale: str = "UT") -> Sky:
    extra = {"TIME_TYPE": f"'{time_scale}'", "ANG_FORMAT": "'DEG'", "EXTRA_PREC": "'YES'"}
    tropical: dict[str, float] = {}
    obliquities: list[tuple[float, float]] = []
    delta_t = 0.0
    for graha, command in GRAHA_CODES.items():
        print(f"  {graha}", file=sys.stderr)
        text = horizons.observer(command, start, "2,30,31", extra=extra)
        # The row ends with right ascension, declination, TDB minus UT, longitude and latitude.
        ra, dec, delta_t, lon, lat = (float(f) for f in horizons.first_row(text)[-5:])
        tropical[graha] = lon
        obliquities.append(obliquity_from(ra, dec, lon, lat)[::-1])
    (_, best), (next_fit, second) = sorted(obliquities, reverse=True)[:2]
    if next_fit < MIN_CONDITIONING or abs(best - second) * 3600 > OBLIQUITY_AGREEMENT_ARCSEC:
        raise ValueError(f"{start}: the two best placed grahas disagree on the obliquity")
    return Sky(tropical, delta_t, best)


def inline_input(instant: datetime) -> dict[str, Any]:
    """An API body at a UT instant; the site does not move a geocentric graha."""
    return {
        "date": instant.strftime("%Y-%m-%d"),
        "time": instant.strftime("%H:%M:%S"),
        "latitude": 23.1765,
        "longitude": 75.7885,
        "timezone": 0,
    }


def sidereal_case(
    terms: list[NutationTerm],
    case: dict[str, Any],
    start: datetime,
    site: tuple[float, float] | None,
    time_scale: str = "UT",
) -> tuple[dict[str, Any], dict[str, float], float]:
    """Fill ``case`` with its expected values; return the sidereal points and TDB minus UT.

    ``site`` (latitude, longitude) adds the Lagna, except beyond the polar circles where part of
    the ecliptic never rises.
    """
    print(case["id"], file=sys.stderr)
    sky = sky_at(start, time_scale)
    ayanamsa = lahiri_ayanamsa(terms, julian_date(start.replace(tzinfo=UTC)))
    sidereal = {g: (lon - ayanamsa) % 360 for g, lon in sky.tropical.items()}
    if site is not None and abs(site[0]) < 90 - sky.obliquity:
        lagna = ascendant(local_sidereal_time(start, *site), sky.obliquity, site[0])
        sidereal["Lagna"] = (lagna - ayanamsa) % 360
    case["expected"] = expected_values(sidereal, ayanamsa)
    return case, sidereal, sky.delta_t


def pull() -> dict[str, Any]:
    terms = parse_nutation_table(get_text(IERS_NUTATION_URL))
    cases: list[dict[str, Any]] = []
    for chart in load_charts().values():
        start = chart.utc().replace(tzinfo=None)
        site = (chart.latitude, chart.longitude)
        cases.append(sidereal_case(terms, {"id": chart.id, "chart": chart.id}, start, site)[0])
    for case_id, (graha, instant) in BOUNDARY_CASES.items():
        body = inline_input(instant)
        site = (body["latitude"], body["longitude"])
        case, sidereal, _ = sidereal_case(terms, {"id": case_id, "input": body}, instant, site)
        if not 0 < sidereal[graha] % PADA_SPAN * 3600 < BOUNDARY_MARGIN_ARCSEC:
            raise ValueError(f"{case_id}: {graha} is no longer just past a pada boundary")
        cases.append(case)
    cross_checks: list[dict[str, Any]] = []
    for day in PAC_DATES:
        # The agency tabulates at 0h TT; the API is called at the UT second nearest to it, which
        # is not a whole minute, so these cases carry no Lagna.
        case_id = f"pac-{day}"
        midnight_tt = datetime.fromisoformat(day)
        case, _, delta_t = sidereal_case(terms, {"id": case_id}, midnight_tt, None, "TT")
        case["input"] = inline_input(midnight_tt - timedelta(seconds=round(delta_t)))
        cases.append(case)
        published = PAC_LONGITUDES[day].items()
        cross_checks.append(
            {
                "id": case_id,
                "source": "Positional Astronomy Centre, Kolkata",
                "input": case["input"],
                "expected": {
                    g: round(d + m / 60 + sec / 3600, LONGITUDE_DECIMALS)
                    for g, (d, m, sec) in published
                },
            }
        )
    return document(cases, cross_checks)


def document(cases: list[dict[str, Any]], cross_checks: list[dict[str, Any]]) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    grahas = tuple(GRAHA_CODES)
    points = (*grahas, "Lagna")
    longitudes = [*points, "ayanamsa"]
    discrete = [f"{p} {q}" for p in points for q in ("nakshatra", "pada", "navamsa")]
    quantities = list(dict.fromkeys(q for c in cases for q in c["expected"]))
    return {
        "format": 1,
        "domain": "vedic",
        "sources": [
            {
                "name": "NASA JPL Horizons",
                "url": horizons.URL,
                "command": "python -m benchmark pull vedic (OBSERVER tables: QUANTITIES 2, 30 "
                "and 31 of geocentric bodies; QUANTITIES 7 at the birthplace)",
                "retrieved": today,
                "licence": horizons.LICENCE,
                "method": "Apparent geocentric ecliptic longitude of date at the case instant, "
                "minus the Lahiri ayanamsa recomputed from its definition at the same instant. "
                "Sun to Mars by their own centres, Jupiter and Saturn by the system barycentres. "
                "The Lagna is the rising ecliptic point from the local apparent sidereal time "
                "at the birthplace and the true obliquity of date solved from the same graha "
                "rows (Jean Meeus, Astronomical Algorithms, first edition, 1991, eq. 12.1, 12.2 "
                "and 12.9), omitted beyond the polar circles and at instants off the minute.",
                "applies_to": longitudes,
            },
            {
                "name": "Lahiri ayanamsa, Calendar Reform Committee definition",
                "url": REPORT_URL,
                "citation": "Report of the Calendar Reform Committee, Government of India, Council "
                "of Scientific and Industrial Research, 1955: Recommendations for the religious "
                "calendar, item 7, pages 7 and 8; general precession, page 209",
                "retrieved": today,
                "licence": "Government of India publication; the definition is cited, no text "
                "is reproduced",
                "method": "23 deg 15 min on 21 March 1956, growing with the general precession "
                "in longitude. Held at 23 deg 15 min 00.658 sec at 0h TT as a true ayanamsa, the "
                "reading that reproduces the Positional Astronomy Centre tables, carried by IERS "
                "Conventions 2010 equation 5.44 and the IAU 2000A nutation in longitude.",
                "applies_to": longitudes,
            },
            {
                "name": "IERS Conventions 2010, Table 5.3a",
                "url": IERS_NUTATION_URL,
                "command": "python -m benchmark pull vedic (downloads the table on each pull)",
                "retrieved": today,
                "licence": "IERS Conventions (2010), IERS Technical Note 36; data cited",
                "method": "IAU 2000A nutation in longitude, all lunisolar and planetary terms, "
                "with the fundamental arguments of equations 5.43 and 5.44.",
                "applies_to": longitudes,
            },
            {
                "name": "Positional Astronomy Centre, Kolkata",
                "url": PAC_URL,
                "retrieved": today,
                "licence": "Government of India data, India Meteorological Department; values "
                "cited with attribution",
                "method": "Published nirayana longitudes of the Sun, Moon and planets at 0h TT, "
                "transcribed for three dates as cross checks the recomputation reproduces.",
                "applies_to": list(grahas),
            },
            {
                "name": "Brihat Parasara Hora Sastra",
                "url": BPHS_URL,
                "citation": "Brihat Parasara Hora Sastra, translated by R. Santhanam, Ranjan "
                "Publications: chapter 6 sloka 12 (volume 1 page 72) for navamsa, chapter 46 "
                "slokas 12 to 16 and notes (volume 2 pages 507 to 509) for nakshatra, pada and "
                "the Vimshottari dasha at birth",
                "retrieved": today,
                "licence": "Classical text; the rules are cited, no translation text is reproduced",
                "method": "Nakshatra and pada from the sidereal longitude in spans of 13 deg 20 "
                "min and 3 deg 20 min, navamsa from the movable, fixed and dual sign rule, "
                "dasha lord counted from Krittika, balance as the unexpired fraction of the Moon "
                "nakshatra times the lord years in Julian years of 365.25 days.",
                "applies_to": [*discrete, "dasha lord", "dasha balance"],
            },
        ],
        "families": [
            {
                "label": "Lahiri ayanamsa and sidereal longitudes",
                "quantities": [q for q in quantities if " " not in q],
            },
            {
                "label": "Nakshatra and pada",
                "quantities": [q for q in quantities if q.endswith((" nakshatra", " pada"))],
            },
            {
                "label": "Navamsa and Vimshottari",
                "quantities": [
                    q for q in quantities if q.endswith(" navamsa") or q.startswith("dasha")
                ],
            },
        ],
        "tolerances": [
            {
                "applies_to": ["Moon"],
                "value": MOON_BAND_ARCSEC,
                "unit": "arcsec",
                "why": "The Moon moves about 13 degrees a day, so this absorbs a couple of minutes "
                "of birth time interpretation. A vendor-neutral pass bar, as for the tropical "
                "Moon.",
            },
            {
                "applies_to": [g for g in grahas if g != "Moon"],
                "value": PLANET_BAND_ARCSEC,
                "unit": "arcsec",
                "why": "The tropical planet bar: wide enough for the arcsecond level disagreement "
                "between two good ephemeris implementations, tight enough to fail a geometric "
                "position or a wrong timezone. The frame is held separately by the ayanamsa bar.",
            },
            {
                "applies_to": ["Lagna"],
                "value": LAGNA_BAND_ARCSEC,
                "unit": "arcsec",
                "why": "The Ascendant turns a degree in about four minutes, so this is a couple of "
                "seconds of sidereal time: room for the UT1 handling of two good implementations, "
                "tight enough to fail sidereal time from UTC alone, a mean sidereal time or a "
                "wrong timezone.",
            },
            {
                "applies_to": ["ayanamsa"],
                "value": AYANAMSA_BAND_ARCSEC,
                "unit": "arcsec",
                "why": "Two faithful implementations of this definition differ by the precession "
                "model (under an arcsecond between the 1955 rate and the IAU rate over 1879 to "
                "2026) and the epoch rounding (0.658 arcseconds). A frame without the nutation "
                "term, up to 18 arcseconds off, or a different Lahiri revision fails.",
            },
            {
                "applies_to": ["dasha balance"],
                "value": BALANCE_BAND_DAYS,
                "unit": "days",
                "why": "A balance is commonly printed in whole days, and a year of 365.2422 days "
                "instead of 365.25 moves a 20 year balance by under a quarter of a day. One day "
                "is also about 7 arcseconds of the Moon on a Venus balance, so the bar keeps the "
                "frame honest.",
            },
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": "Nakshatra, pada, navamsa sign and dasha lord are discrete: a value is the "
                "definition applied to the sidereal longitude or it is not.",
            },
        ],
        "cases": cases,
        "cross_checks": cross_checks,
    }
