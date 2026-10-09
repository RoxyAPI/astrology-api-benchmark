"""Rebuild ``references.json``: Ayurvedic season edges from NASA JPL Horizons and the day clock.

A season (ritu) is a pair of solar months, and a solar month is the interval the Sun spends in one
sign (Surya Siddhanta, chapter 1 verse 13, Burgess translation, Journal of the American Oriental
Society, volume 6, 1860). Sushruta Samhita, Sutrasthana chapter VI (Bhishagratna translation,
Calcutta 1907, volume 1, pages 43 and 44) divides the twelve months from Magha into six seasons of
two months: Magha and Phalguna the cold season (sisira), Chaitra and Vaishakha spring (vasanta),
Jyaishtha and Ashadha summer (grisma), Shravana and Bhadra the rains (varsa), Ashvina and Kartika
autumn (sarad), Agrahayana and Pausha the early winter (hemanta). Charaka Samhita Sutrasthana 6.4
puts the same six names in one order, with the three from sisira to grisma on the Sun northward
course and the three from varsa to hemanta on its southward course.

The convention the API documents, and which this reference states rather than proves, is that the
solar month of Makara carries the month Magha. Sisira then opens when the Sun enters Capricorn
and the season edges are the Sun at 270, 330, 30, 90, 150 and 210 degrees, so the two courses open
on the two solstices. Sayana reads those degrees in the tropical zodiac, which is what a season
follows; nirayana reads them in the Lahiri sidereal zodiac, about 24 degrees later.

Every boundary is a root of the apparent geocentric ecliptic longitude of the Sun of date that
Horizons prints (OBSERVER table, QUANTITIES 31, times in UT), found in one table of hourly rows
around a guess from the mean motion: the root of the cubic through the four rows around the
crossing (Lagrange interpolation, Meeus, Astronomical Algorithms, 2nd edition, chapter 3), by
bisection to a millisecond. A sidereal longitude is that longitude minus the Lahiri ayanamsa at the
row, recomputed from its definition as the vedic and panchang domains do: 23 deg 15 min 00.658 sec
at 0h TT on 21 March 1956 (Report of the Calendar Reform Committee, Government of India, 1955),
made mean, carried by the IERS Conventions 2010 general precession in longitude and made true
again with the IAU 2000A nutation in longitude of the instant.

A date is read at midday UT, because a season boundary is an instant and a day has to be reduced to
one; the season named is the one the Sun is in at that instant. Each boundary is declared with a
date just before and a date just after it, which includes the day a boundary falls late in, whose
midday still reads the outgoing season. The southern reading rotates the six names by three places,
the half year, a modern almanac convention that no classical text states.

The day clock is the Ashtanga Hridaya, Sutrasthana 1.8 (Sanskrit, with two commentaries, read in
the archive.org copy): the three humours
rule the end, the middle and the beginning of age, of the day and night and of digestion, so kapha
holds the first third, pitta the second and vata the last of the day from sunrise to sunset, and the
same order holds for the night from sunset to the next sunrise. A muhurta is a thirtieth of the
24 hour day, 48 minutes (Sushruta Samhita, Sutrasthana chapter VI, page 43: thirty muhurtas make a
day and night). The brahma muhurta of Sutrasthana 2.1 is read as the window two muhurtas to one
muhurta before sunrise, 96 to 48 minutes, the fixed reading of the commentary rather than a share of
the night; that offset is the convention the API documents and is not independently proven here.
Sunrise and sunset come from the USNO Astronomical Applications API.

Every event is in the past, where Horizons applies measured delta T.

Run it with ``uv run python -m benchmark pull ayurveda``; nothing else in the repo contacts a
source.
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from benchmark import horizons
from benchmark.fetch import get_text

IERS_NUTATION_URL = "https://iers-conventions.obspm.fr/content/chapter5/additional_info/tab5.3a.txt"
REPORT_URL = "https://archive.org/details/calendar_reform_comittee_report"
PAC_URL = "https://packolkata.imd.gov.in/download/nirlon/nlongitude.htm"
SUSHRUTA_URL = "https://archive.org/details/india.history.resource.92776"
SURYA_SIDDHANTA_URL = "https://archive.org/details/TranslationOfTheSuryaSiddhanta"
CHARAKA_URL = "https://archive.org/details/GabrielVanLoonCharakaSamhitaVol1Eng"
HRIDAYA_URL = "https://archive.org/details/Ashtanga.Hridaya.of.Vagbhata"
USNO_URL = "https://aa.usno.navy.mil/api/rstt/oneday"
USNO_SEASONS_URL = "https://aa.usno.navy.mil/api/seasons"
USNO_DOC_URL = "https://aa.usno.navy.mil/data/api"
USNO_DEFINITION_URL = "https://aa.usno.navy.mil/faq/RST_defs"

SUN = "10"
ARCSEC_PER_RADIAN = 180 * 3600 / math.pi
J2000 = 2451545.0
UNIX_EPOCH_JD = 2440587.5
EPOCH_JD = 2435553.5
"""1956 March 21, 0h TT, the Lahiri epoch."""
EPOCH_AYANAMSA_ARCSEC = 23 * 3600 + 15 * 60 + 0.658
"""23 deg 15 min 00.658 sec, the true ayanamsa at the epoch."""

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

RITUS = ("sisira", "vasanta", "grisma", "varsa", "sarad", "hemanta")
"""In order from the Sun at 270 degrees: the first two solar months are Makara and Kumbha."""
SEASON_DEGREES = 60.0
FIRST_EDGE = 270.0
SOUTHERN_ROTATION = 3
DOSHA_ORDER = ("kapha", "pitta", "vata", "kapha", "pitta", "vata")
"""Day thirds then night thirds, Ashtanga Hridaya Sutrasthana 1.8."""

MEAN_DEGREES_PER_DAY = 0.9856
SEARCH_DAYS = 4
"""The hourly table spans the guessed boundary plus or minus this many days: the Sun rate is
between 0.953 and 1.019 degrees a day, so a mean-motion guess over 60 degrees is off by under 4."""
MIN_MARGIN = timedelta(minutes=30)
"""A date read at midday sits at least this far from an edge, so the reading is never marginal."""
BISECTION_SECONDS = 0.001
HOURLY = timedelta(hours=1)
MUHURTA = timedelta(minutes=48)
BRAHMA_START = 2 * MUHURTA
BRAHMA_END = MUHURTA

# Positional Astronomy Centre, Kolkata, nirayana (Lahiri) longitude of the Sun at 0h TT as its table
# prints it (degrees, minutes, seconds), transcribed from the PDF linked at PAC_URL: the rows either
# side of the two sidereal season edges the cases cover.
PAC_SUN: dict[str, tuple[int, int, float]] = {
    "2026-01-14": (269, 35, 26.5878),
    "2026-01-15": (270, 36, 34.2678),
    "2026-03-14": (329, 11, 12.5494),
    "2026-03-15": (330, 11, 2.4979),
}
PAC_CROSS_CHECKS = (
    ("sidereal-sisira-opens", "2026-01-14", "2026-01-15", FIRST_EDGE),
    ("sidereal-sisira-closes", "2026-03-14", "2026-03-15", FIRST_EDGE + SEASON_DEGREES),
)
"""Case id, the PAC rows either side of the crossing, and the sidereal degrees crossed."""

# Instants in the past, in the order cases are written. Each is (id, edge in degrees, UT date the
# season edge falls in), expanded into a case just before and a case just after.
TROPICAL_EDGES: tuple[tuple[str, float, str], ...] = (
    ("hemanta-sisira", 270.0, "2025-12-21"),
    ("sisira-vasanta", 330.0, "2026-02-18"),
    ("vasanta-grisma", 30.0, "2026-04-20"),
    ("grisma-varsa", 90.0, "2026-06-21"),
    ("sarad-hemanta", 210.0, "2025-10-23"),
    ("varsa-sarad", 150.0, "2025-08-23"),
)
SIDEREAL_EDGES: tuple[tuple[str, float, str], ...] = (
    ("sidereal-sisira-opens", 270.0, "2026-01-14"),
    ("sidereal-sisira-closes", 330.0, "2026-03-14"),
)
DIVERGENCE_DATE = "2026-03-01"
"""A date whose tropical and sidereal readings differ: spring by the Sun, still the cold season by
the stars."""
SOUTHERN_DATE = "2026-03-01"

# (id, local date, latitude, longitude, UTC offset in hours, why the case is here).
DAY_CASES: tuple[tuple[str, str, float, float, float, str], ...] = (
    ("london-midsummer", "2026-06-21", 51.5074, -0.1278, 1, "the longest day, thirds of 5.5 hours"),
    ("reykjavik-midwinter", "2025-12-21", 64.1466, -21.9426, 0, "a four hour day, uneven thirds"),
    ("sydney-midsummer", "2025-12-21", -33.8688, 151.2093, 11, "south latitude, east longitude"),
    ("mumbai-equinox", "2026-03-20", 19.076, 72.8777, 5.5, "a half hour offset"),
    ("quito-equinox", "2026-03-20", -0.1807, -78.4678, -5, "on the equator, day near night"),
)  # fmt: skip

SOLAR_BAND_SECONDS = 60
SIDEREAL_BAND_SECONDS = 120
SUNRISE_BAND_SECONDS = 90

type NutationTerm = tuple[float, float, tuple[int, ...], bool]
"""In phase and out of phase amplitudes in microarcseconds, argument multipliers, times t."""
type Sample = tuple[datetime, float]


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
    return instant.timestamp() / 86400 + UNIX_EPOCH_JD


def ritu_index(longitude: float) -> int:
    """0 for sisira to 5 for hemanta, from the Sun longitude in the frame the zodiac is read in."""
    return int(((longitude - FIRST_EDGE) % 360.0) // SEASON_DEGREES)


def signed_offset(longitude: float, edge: float) -> float:
    """Degrees past ``edge``, between minus 180 and 180."""
    return (longitude - edge + 180.0) % 360.0 - 180.0


def lagrange(samples: Sequence[Sample], when: datetime) -> float:
    origin = samples[0][0]
    x = (when - origin).total_seconds()
    xs = [(t - origin).total_seconds() for t, _ in samples]
    total = 0.0
    for j, (_, y) in enumerate(samples):
        term = y
        for k, xk in enumerate(xs):
            if k != j:
                term *= (x - xk) / (xs[j] - xk)
        total += term
    return total


def bisect_rising(f: Callable[[datetime], float], low: datetime, high: datetime) -> datetime:
    """Root of an increasing ``f`` between ``low`` and ``high``, to a millisecond."""
    while (high - low).total_seconds() > BISECTION_SECONDS:
        mid = low + (high - low) / 2
        if f(mid) > 0:
            high = mid
        else:
            low = mid
    return low + (high - low) / 2


def as_utc(fields: Sequence[str]) -> datetime:
    return datetime.strptime(f"{fields[0]} {fields[1][:5]}", "%Y-%b-%d %H:%M").replace(tzinfo=UTC)


class Sky:
    """Sun longitudes from Horizons in the tropical or the Lahiri sidereal frame, with caching."""

    def __init__(self, terms: list[NutationTerm]) -> None:
        self.terms = terms
        self.roots: dict[tuple[bool, float], list[datetime]] = {}

    def frame(self, sidereal: bool, when: datetime, longitude: float) -> float:
        if not sidereal:
            return longitude
        return (longitude - lahiri_ayanamsa(self.terms, julian_date(when))) % 360.0

    def at(self, sidereal: bool, when: datetime) -> float:
        row = horizons.first_row(horizons.observer(SUN, when, "31"))
        return self.frame(sidereal, when, float(row[-2]))

    def hourly(self, sidereal: bool, start: datetime, stop: datetime) -> list[Sample]:
        text = horizons.observer(SUN, whole_hour(start), "31", stop=whole_hour(stop), step="1h")
        return [
            (as_utc(f), self.frame(sidereal, as_utc(f), float(f[-2]))) for f in horizons.rows(text)
        ]

    def crossing(self, sidereal: bool, edge: float, guess: datetime) -> datetime:
        """The instant the Sun reaches ``edge`` degrees, found within a few days of ``guess``."""
        known = self.roots.setdefault((sidereal, edge), [])
        for root in known:
            if abs(root - guess) < timedelta(days=SEARCH_DAYS):
                return root
        span = timedelta(days=SEARCH_DAYS)
        rows = self.hourly(sidereal, guess - span, guess + span)
        offsets = [(t, signed_offset(lon, edge)) for t, lon in rows]
        found = [i for i in range(len(offsets) - 1) if offsets[i][1] < 0 <= offsets[i + 1][1]]
        if len(found) != 1:
            raise ValueError(f"edge {edge} near {guess}: {len(found)} crossings in the table")
        i = found[0]
        window = offsets[max(i - 1, 0) : i + 3]
        root = bisect_rising(lambda t: lagrange(window, t), offsets[i][0], offsets[i + 1][0])
        known.append(root)
        return root


def whole_hour(when: datetime) -> datetime:
    """Horizons prints seconds in every row when the start has them; whole hours keep rows short."""
    return when.replace(minute=0, second=0, microsecond=0)


def iso(when: datetime) -> str:
    return when.astimezone(UTC).isoformat(timespec="milliseconds")


def season_case(
    sky: Sky, case_id: str, day: str, *, sidereal: bool = False, southern: bool = False
) -> dict[str, Any]:
    """One request for ``day`` and the season the Sun is in at its midday UT."""
    noon = datetime.fromisoformat(day).replace(hour=12, tzinfo=UTC)
    longitude = sky.at(sidereal, noon)
    k = ritu_index(longitude)
    body: dict[str, Any] = {"date": day}
    if sidereal:
        body["rituZodiac"] = "nirayana"
    prefix = "sidereal " if sidereal else ""
    if southern:
        body["hemisphere"] = "southern"
        expected: dict[str, Any] = {"southern ritu": RITUS[(k + SOUTHERN_ROTATION) % 6]}
        return {"id": case_id, "input": {"ritucharya": body}, "expected": expected}
    edges = (FIRST_EDGE + SEASON_DEGREES * k, FIRST_EDGE + SEASON_DEGREES * (k + 1))
    behind = (longitude - edges[0]) % 360.0
    ahead = (edges[1] - longitude) % 360.0
    opens = sky.crossing(
        sidereal, edges[0] % 360.0, noon - timedelta(days=behind / MEAN_DEGREES_PER_DAY)
    )
    closes = sky.crossing(
        sidereal, edges[1] % 360.0, noon + timedelta(days=ahead / MEAN_DEGREES_PER_DAY)
    )
    if min(noon - opens, closes - noon) < MIN_MARGIN:
        raise ValueError(f"{case_id}: midday is within {MIN_MARGIN} of a season edge")
    expected = {
        f"{prefix}ritu": RITUS[k],
        f"{prefix}ritu start": iso(opens),
        f"{prefix}ritu end": iso(closes),
    }
    return {"id": case_id, "input": {"ritucharya": body}, "expected": expected}


def edge_days(when: datetime) -> tuple[str, str]:
    """The last UT date whose midday is before ``when`` and the first whose midday is after."""
    day = when.date()
    if when >= datetime(day.year, day.month, day.day, 12, tzinfo=UTC):
        return day.isoformat(), (day + timedelta(days=1)).isoformat()
    return (day - timedelta(days=1)).isoformat(), day.isoformat()


def season_cases(sky: Sky) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for sidereal, edges in ((False, TROPICAL_EDGES), (True, SIDEREAL_EDGES)):
        for name, edge, day in edges:
            guess = datetime.fromisoformat(day).replace(hour=12, tzinfo=UTC)
            when = sky.crossing(sidereal, edge, guess)
            before, after = edge_days(when)
            print(f"{name}: {edge} at {iso(when)}", file=sys.stderr)
            cases.append(season_case(sky, f"{name}-before", before, sidereal=sidereal))
            cases.append(season_case(sky, f"{name}-after", after, sidereal=sidereal))
    cases.append(season_case(sky, "divergence-sidereal", DIVERGENCE_DATE, sidereal=True))
    cases.append(season_case(sky, "divergence-tropical", DIVERGENCE_DATE))
    cases.append(season_case(sky, "southern-march", SOUTHERN_DATE, southern=True))
    return cases


def usno_local(day: str, latitude: float, longitude: float, offset: float, phen: str) -> datetime:
    """The USNO one day Sun rise or set time of the local ``day``, as a UTC instant."""
    text = get_text(
        USNO_URL,
        {"date": day, "coords": f"{latitude},{longitude}", "tz": f"{offset:g}"},
    )
    entries = json.loads(text)["properties"]["data"]["sundata"]
    clock = next((e["time"] for e in entries if e["phen"] == phen), None)
    if clock is None:
        raise ValueError(f"USNO prints no {phen} for {day} at {latitude}, {longitude}")
    hour, minute = (int(part) for part in clock.split(":"))
    local = datetime.fromisoformat(day).replace(hour=hour, minute=minute)
    return (local - timedelta(hours=offset)).replace(tzinfo=UTC)


def day_case(
    case_id: str, day: str, latitude: float, longitude: float, offset: float
) -> dict[str, Any]:
    rise = usno_local(day, latitude, longitude, offset, "Rise")
    sunset = usno_local(day, latitude, longitude, offset, "Set")
    following = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    next_rise = usno_local(following, latitude, longitude, offset, "Rise")
    daytime, night = (sunset - rise) / 3, (next_rise - sunset) / 3
    expected: dict[str, Any] = {
        "sunrise": iso(rise),
        "sunset": iso(sunset),
        "next sunrise": iso(next_rise),
        "brahma muhurta start": iso(rise - BRAHMA_START),
        "brahma muhurta end": iso(rise - BRAHMA_END),
        "day pitta start": iso(rise + daytime),
        "day vata start": iso(rise + 2 * daytime),
        "night pitta start": iso(sunset + night),
        "night vata start": iso(sunset + 2 * night),
        "dosha order": " ".join(DOSHA_ORDER),
    }
    body = {"date": day, "latitude": latitude, "longitude": longitude, "timezone": offset}
    return {"id": case_id, "input": {"dinacharya": body}, "expected": expected}


def usno_solstice(year: int, phenomenon: str, month: int) -> datetime:
    """The USNO seasons table time of one solstice, UT to the minute as published."""
    doc = json.loads(get_text(USNO_SEASONS_URL, {"year": str(year)}))
    (row,) = [r for r in doc["data"] if r["phenom"] == phenomenon and r["month"] == month]
    hour, minute = (int(part) for part in row["time"].split(":"))
    return datetime(year, month, row["day"], hour, minute, tzinfo=UTC)


def pac_degrees(row: tuple[int, int, float]) -> float:
    degrees, minutes, seconds = row
    return degrees + minutes / 60 + seconds / 3600


def pac_crossing(sky: Sky, day_a: str, day_b: str, edge: float) -> datetime:
    """The instant the PAC Sun reaches ``edge``: linear in the two 0h TT rows, then TT to UT.

    The Sun rate changes by under 0.0005 degrees a day squared, so a straight line over one day
    is off by under 0.2 arcseconds, 5 seconds of time.
    """
    a, b = pac_degrees(PAC_SUN[day_a]), pac_degrees(PAC_SUN[day_b])
    midnight = datetime.fromisoformat(day_a).replace(tzinfo=UTC)
    row = horizons.first_row(horizons.observer(SUN, midnight, "30", extra={"TIME_TYPE": "'UT'"}))
    delta_t = float(row[-1])
    return midnight + timedelta(days=(edge - a) / (b - a)) - timedelta(seconds=delta_t)


def pull() -> dict[str, Any]:
    sky = Sky(parse_nutation_table(get_text(IERS_NUTATION_URL)))
    cases = season_cases(sky)
    cases += [day_case(*case[:5]) for case in DAY_CASES]
    by_id = {c["id"]: c for c in cases}
    cross_checks: list[dict[str, Any]] = []
    solstices = (
        ("hemanta-sisira-after", "Solstice", 2025, 12, "ritu start"),
        ("grisma-varsa-after", "Solstice", 2026, 6, "ritu start"),
    )
    for case_id, phenomenon, year, month, quantity in solstices:
        case = by_id[case_id]
        cross_checks.append(
            {
                "source": "US Naval Observatory seasons",
                "id": case_id,
                "input": case["input"],
                "expected": {quantity: iso(usno_solstice(year, phenomenon, month))},
            }
        )
    for case_id, day_a, day_b, edge in PAC_CROSS_CHECKS:
        quantity = "sidereal ritu start" if case_id.endswith("opens") else "sidereal ritu end"
        suffix = "after" if quantity.endswith("start") else "before"
        case = by_id[f"{case_id}-{suffix}"]
        cross_checks.append(
            {
                "source": "Positional Astronomy Centre, Kolkata",
                "id": case["id"],
                "input": case["input"],
                "expected": {quantity: iso(pac_crossing(sky, day_a, day_b, edge))},
            }
        )
    today = datetime.now(UTC).date().isoformat()
    return {
        "format": 1,
        "domain": "ayurveda",
        "sources": sources(today),
        "tolerances": TOLERANCES,
        "cases": cases,
        "families": FAMILIES,
        "cross_checks": cross_checks,
    }


SEASON_NAMES = ["ritu", "sidereal ritu", "southern ritu"]
BOUNDARIES = ["ritu start", "ritu end", "sidereal ritu start", "sidereal ritu end"]
SUN_TIMES = ["sunrise", "sunset", "next sunrise"]
BRAHMA = ["brahma muhurta start", "brahma muhurta end"]
DOSHA = [
    "day pitta start",
    "day vata start",
    "night pitta start",
    "night vata start",
    "dosha order",
]
FAMILIES: list[dict[str, Any]] = [
    {"label": "Season at a date, both zodiacs and both hemispheres", "quantities": SEASON_NAMES},
    {"label": "Season opening and closing instants", "quantities": BOUNDARIES},
    {"label": "Sunrise and sunset", "quantities": SUN_TIMES},
    {"label": "Brahma muhurta window", "quantities": BRAHMA},
    {"label": "Dosha periods of the day and night", "quantities": DOSHA},
]

TOLERANCES: list[dict[str, Any]] = [
    {
        "applies_to": ["ritu start", "ritu end"],
        "value": SOLAR_BAND_SECONDS,
        "unit": "seconds",
        "why": "A vendor-neutral pass bar, not sized to any one API. The Sun moves about 2.5 "
        "arcseconds a minute at a season edge, so a minute is the arcsecond level disagreement "
        "between two good ephemerides: wide enough for that, tight enough to fail an edge read "
        "off a daily table, a mean Sun, a longitude in the wrong frame or a coarse sampling of "
        "the ingress, each of which is minutes to hours.",
    },
    {
        "applies_to": ["sidereal ritu start", "sidereal ritu end"],
        "value": SIDEREAL_BAND_SECONDS,
        "unit": "seconds",
        "why": "The tropical bar plus the ayanamsa. Two published recomputations of the Lahiri "
        "definition differ by an arcsecond or two once nutation is treated as the definition "
        "allows, which is up to a minute of Sun motion, so the band is twice the tropical one. A "
        "different ayanamsa revision is 20 arcseconds or more, over eight minutes, and fails.",
    },
    {
        "applies_to": [*SUN_TIMES, *BRAHMA, *DOSHA[:-1]],
        "value": SUNRISE_BAND_SECONDS,
        "unit": "seconds",
        "why": "The reference prints whole minutes, so two exact values differ by up to a minute "
        "through rounding alone; the half minute beyond covers the difference between two good "
        "implementations of the same upper limb and 34 arcminute refraction definition. A "
        "different limb (about 4 minutes at mid latitudes) or no refraction (about 2 to 3) fails. "
        "A third of the day or night and a fixed offset from sunrise inherit the same bar, since "
        "each is a weighted mean of the sunrise and sunset errors.",
    },
    {
        "applies_to": [*SEASON_NAMES, "dosha order"],
        "value": 0,
        "unit": "exact",
        "why": "Discrete names: the season is a machine identifier of the six, and the order of "
        "the six dosha periods is a fixed sequence, so either is right or wrong.",
    },
]


def sources(today: str) -> list[dict[str, Any]]:
    return [
        {
            "name": "NASA JPL Horizons",
            "url": horizons.URL,
            "command": "python -m benchmark pull ayurveda (OBSERVER table of the Sun, CENTER "
            "500@399, QUANTITIES 31, hourly step around each season edge, root by bisection)",
            "retrieved": today,
            "licence": horizons.LICENCE,
            "method": "Apparent geocentric ecliptic longitude of the Sun of date, hourly around "
            "each season edge. The edge is the instant the longitude reaches a multiple of 60 "
            "degrees from 270 (sayana), or the same longitude less the Lahiri ayanamsa "
            "(nirayana), by bisection on the cubic through the four rows around the crossing, "
            "Meeus, Astronomical Algorithms, 2nd edition, chapter 3. The season of a date is "
            "the one the Sun is in at midday UT.",
            "notes": "Times are UT to the millisecond the search resolves. Every instant is in "
            "the past, where Horizons applies measured delta T.",
            "applies_to": [*SEASON_NAMES, *BOUNDARIES],
        },
        {
            "name": "Sushruta Samhita, Bhishagratna translation",
            "url": SUSHRUTA_URL,
            "citation": "An English Translation of the Sushruta Samhita, Kaviraj Kunja Lal "
            "Bhishagratna, Calcutta 1907, volume 1, Sutrasthana chapter VI (pages 43 and 44): "
            "the twelve months from Magha in six seasons of two, and thirty muhurtas to the "
            "day and night",
            "retrieved": today,
            "licence": "Classical text in an openly digitised 1907 translation; the rules are "
            "cited, no text is reproduced",
            "method": "Sisira is Magha and Phalguna, vasanta Chaitra and Vaishakha, and so on "
            "to hemanta. A solar month carries the month named for it (Makara for Magha), which "
            "puts every edge on a multiple of 30 degrees of solar longitude and the two courses "
            "on the two solstices. A muhurta is a thirtieth of a day, 48 minutes.",
            "applies_to": [*SEASON_NAMES, *BOUNDARIES, *BRAHMA],
        },
        {
            "name": "Charaka Samhita, Sutrasthana 6",
            "url": CHARAKA_URL,
            "citation": "Charaka Samhita, Handbook on Ayurveda Volume I, edited by Gabriel Van "
            "Loon, 2002 to 2003, after P. V. Sharma: Sutrasthana 6.3 and 6.4, the six seasons "
            "and the northward course from sisira to grisma against the southward course from "
            "varsa to hemanta",
            "retrieved": today,
            "licence": "Cited for the rule only; no text is reproduced",
            "method": "The second witness to the six season names and to their order against "
            "the Sun course: sisira opens the northward half, which a tropical Sun does at the "
            "December solstice.",
            "applies_to": [*SEASON_NAMES, *BOUNDARIES],
        },
        {
            "name": "Surya Siddhanta, Burgess translation",
            "url": SURYA_SIDDHANTA_URL,
            "citation": "Translation of the Surya-Siddhanta, a Text-Book of Hindu Astronomy, by "
            "Ebenezer Burgess, Journal of the American Oriental Society, volume 6, 1860: "
            "chapter 1 verse 13, a solar month is determined by the entrance of the Sun into a "
            "sign of the zodiac",
            "retrieved": today,
            "licence": "Classical text in an openly digitised 1860 translation; the rule is "
            "cited, no text is reproduced",
            "method": "A season of two solar months opens at a Sun ingress into a sign.",
            "applies_to": [*BOUNDARIES],
        },
        {
            "name": "Lahiri ayanamsa, Calendar Reform Committee definition",
            "url": REPORT_URL,
            "citation": "Report of the Calendar Reform Committee, Government of India, 1955, "
            "recommendations for the religious calendar, item 7, pages 7 and 8",
            "retrieved": today,
            "licence": "Government of India publication; the definition is cited, no text is "
            "reproduced",
            "method": "23 deg 15 min 00.658 sec at 0h TT on 21 March 1956 as a true ayanamsa, "
            "made mean, carried by the IERS Conventions 2010 general precession in longitude "
            "and made true again with the IAU 2000A nutation in longitude of the instant. The "
            "frame of every sidereal season edge.",
            "applies_to": ["sidereal ritu", "sidereal ritu start", "sidereal ritu end"],
        },
        {
            "name": "Positional Astronomy Centre, Kolkata",
            "url": PAC_URL,
            "retrieved": today,
            "licence": "Government of India data, India Meteorological Department; values "
            "cited with attribution",
            "method": "Published nirayana longitude of the Sun at 0h TT, transcribed for the "
            "four days around the two sidereal season edges as cross checks: the instant the "
            "published longitude reaches the edge must equal the recomputed one.",
            "applies_to": ["sidereal ritu start", "sidereal ritu end"],
        },
        {
            "name": "US Naval Observatory seasons",
            "url": USNO_DOC_URL,
            "retrieved": today,
            "licence": "US Naval Observatory data, public domain US government work",
            "method": "The December and June solstice instants in UT to the minute as "
            "published. A tropical season edge at 270 and 90 degrees is the same event, so the "
            "two values are cross checks of the Horizons recomputation, not references.",
            "applies_to": ["ritu start", "ritu end"],
        },
        {
            "name": "Ashtanga Hridaya, Sutrasthana 1.8",
            "url": HRIDAYA_URL,
            "citation": "Ashtanga Hridaya of Vagbhata, Sanskrit with two "
            "commentaries, as digitised: Sutrasthana 1.8, the humours "
            "hold the end, the middle and the beginning of the day, the night and digestion; "
            "Sutrasthana 2.1, rising in the brahma muhurta",
            "retrieved": today,
            "licence": "Classical text in an openly digitised edition; the rule is cited, no "
            "text is reproduced",
            "method": "Kapha holds the first third, pitta the middle third and vata the last "
            "third of the day, and the same order the night. The brahma muhurta is read as the "
            "window 96 to 48 minutes before sunrise, the fixed reading the commentary settles "
            "on; that offset is a stated convention, checked here as arithmetic from sunrise.",
            "applies_to": [*BRAHMA, *DOSHA],
        },
        {
            "name": "US Naval Observatory Astronomical Applications API",
            "url": USNO_DOC_URL,
            "citation": f"Complete Sun and Moon Data for One Day; rise and set defined at "
            f"{USNO_DEFINITION_URL}",
            "command": "python -m benchmark pull ayurveda (GET rstt/oneday with date, coords and "
            "tz in hours)",
            "retrieved": today,
            "licence": "US Government data, public domain; cite USNO",
            "method": "The Rise and Set entries of the Sun data, in the local zone given, and "
            "the Rise of the next local day. Sunrise is the upper limb of the Sun on a level "
            "sea horizon under 34 arcminutes of refraction. The service prints whole minutes. "
            "The thirds of the day and night and the brahma muhurta are computed from them.",
            "applies_to": [*SUN_TIMES, *BRAHMA, *DOSHA[:-1]],
        },
    ]
