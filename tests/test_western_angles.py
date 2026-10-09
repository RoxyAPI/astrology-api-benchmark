"""The chart angle formulas reproduce the printed example and the Placidus definition, offline."""

from __future__ import annotations

import importlib.util
import math
from collections.abc import Mapping
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import load
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import Chart, Status
from tests.conftest import FakeApi

FOLDER = DOMAINS_DIR / "western-angles"
OBLIQUITY = 23.44
SIDEREAL_ANGLES = (0.0, 75.0, 151.3, 222.2, 300.0)
LATITUDES = (-60.0, -33.9, 0.0, 21.3, 51.0, 64.1)


def _module(filename: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"western_angles_{filename}", FOLDER / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    return _module("pull.py")


def _gap(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _right_ascension(longitude: float) -> float:
    """Right ascension of an ecliptic point, Meeus eq. 12.3 with zero latitude."""
    lam, e = math.radians(longitude), math.radians(OBLIQUITY)
    return math.degrees(math.atan2(math.sin(lam) * math.cos(e), math.cos(lam)))


def test_ascendant_reproduces_the_printed_example(pull: ModuleType) -> None:
    # Meeus, Astronomical Algorithms (1991), example 12.c: obliquity 23.44, latitude +51,
    # sidereal time 5h = 75 degrees puts the horizon points at 169 deg 21 min and 349 deg 21 min;
    # the rising one, east of a meridian near 76 degrees, is 169 deg 21 min.
    assert _gap(pull.ascendant(75.0, OBLIQUITY, 51.0), 169 + 21 / 60) < 1 / 60


@pytest.mark.parametrize("sidereal", SIDEREAL_ANGLES)
@pytest.mark.parametrize("latitude", LATITUDES)
def test_angles_lie_on_their_great_circles(
    pull: ModuleType, sidereal: float, latitude: float
) -> None:
    values = pull.angles(sidereal, OBLIQUITY, latitude)
    e, p, t = (math.radians(x) for x in (OBLIQUITY, latitude, sidereal))
    # The Midheaven has the sidereal angle as its right ascension.
    assert _gap(_right_ascension(values["Midheaven"]), sidereal) < 1e-9
    # The Ascendant has zero altitude and lies east of the meridian.
    asc = math.radians(values["Ascendant"])
    dec = math.asin(math.sin(e) * math.sin(asc))
    hour = t - math.radians(_right_ascension(values["Ascendant"]))
    altitude = math.sin(p) * math.sin(dec) + math.cos(p) * math.cos(dec) * math.cos(hour)
    assert abs(altitude) < 1e-12
    assert math.sin(hour) < 0


@pytest.mark.parametrize("sidereal", SIDEREAL_ANGLES)
@pytest.mark.parametrize("latitude", LATITUDES)
def test_cusps_trisect_their_own_semi_arcs(
    pull: ModuleType, sidereal: float, latitude: float
) -> None:
    values = pull.angles(sidereal, OBLIQUITY, latitude)
    # Right ascension east of the upper meridian as a share of the diurnal semi arc (cusps 11,
    # 12), and west of the lower meridian as a share of the nocturnal semi arc (cusps 3, 2).
    shares: list[tuple[str, bool, float]] = [("Cusp 11", True, 1 / 3), ("Cusp 12", True, 2 / 3)]
    shares += [("Cusp 3", False, 1 / 3), ("Cusp 2", False, 2 / 3)]
    for name, upper, share in shares:
        lon = values[name]
        ra = _right_ascension(lon)
        dsa = pull.diurnal_semi_arc(pull.declination_of(lon, OBLIQUITY), latitude)
        east = (ra - sidereal) % 360.0 if upper else (180.0 - (ra - sidereal)) % 360.0
        arc = dsa if upper else 180.0 - dsa
        assert abs(east - share * arc) < 1e-8, name
    for cusp, pair in pull.OPPOSITE.items():
        assert _gap(values[f"Cusp {cusp}"], values[f"Cusp {pair}"] + 180.0) < 1e-9


def test_cusps_at_the_equator_split_right_ascension_evenly(pull: ModuleType) -> None:
    values = pull.angles(75.0, OBLIQUITY, 0.0)
    for name, step in (("Cusp 11", 30), ("Cusp 12", 60), ("Cusp 2", 120), ("Cusp 3", 150)):
        assert _gap(values[name], pull.ecliptic_longitude_of(75.0 + step, OBLIQUITY)) < 1e-9


def test_obliquity_is_recovered_from_one_direction_in_both_frames(pull: ModuleType) -> None:
    for lon, lat in ((132.5, -0.0002), (63.4, 4.9), (300.9, -1.2), (215.0, 2.0)):
        e, lam, beta = (math.radians(x) for x in (OBLIQUITY, lon, lat))
        # Meeus eq. 12.3 and 12.4: ecliptic to equatorial.
        ra = math.atan2(math.sin(lam) * math.cos(e) - math.tan(beta) * math.sin(e), math.cos(lam))
        dec = math.asin(math.sin(beta) * math.cos(e) + math.cos(beta) * math.sin(e) * math.sin(lam))
        recovered, conditioning = pull.obliquity_from(math.degrees(ra), math.degrees(dec), lon, lat)
        assert abs(recovered - OBLIQUITY) < 1e-10
        assert conditioning > pull.MIN_CONDITIONING


def test_placidus_is_refused_beyond_the_polar_circle(pull: ModuleType) -> None:
    with pytest.raises(pull.PlacidusUndefinedError):
        pull.angles(75.0, OBLIQUITY, 69.65)


def test_references_skip_only_charts_beyond_the_polar_circle(
    pull: ModuleType, charts: dict[str, Chart]
) -> None:
    refs = load(FOLDER, charts).references
    limit = pull.polar_limit(OBLIQUITY)
    assert {c.id for c in refs.cases} == {c.id for c in charts.values() if abs(c.latitude) < limit}
    for case in refs.cases:
        assert set(case.expected) == set(pull.QUANTITIES)


def _chart_response(expected: Mapping[str, Any], system: str) -> dict[str, Any]:
    houses = [{"number": n, "longitude": expected[f"Cusp {n}"]} for n in (2, 3, 5, 6, 8, 9, 11, 12)]
    return {
        "houseSystem": system,
        "ascendant": {"longitude": expected["Ascendant"]},
        "midheaven": {"longitude": expected["Midheaven"]},
        "houses": houses,
    }


@pytest.mark.parametrize(
    ("system", "status"), [("placidus", Status.PASS), ("whole-sign", Status.MISSING)]
)
def test_check_asks_for_placidus_and_refuses_another_system(
    charts: dict[str, Chart], system: str, status: Status
) -> None:
    loaded = load(FOLDER, charts)
    by_chart = {c.chart.id: c.expected for c in loaded.references.cases if c.chart is not None}

    def answer(method: str, path: str, body: Mapping[str, Any] | None) -> Any:
        assert method == "POST" and body is not None and body["houseSystem"] == "placidus"
        chart = next(
            c for c in charts.values() if c.date == body["date"] and c.time == body["time"]
        )
        return _chart_response(by_chart[chart.id], system)

    measurements = loaded.check(FakeApi(answer), loaded.references)
    assert {m.status for m in measurements} == {status}
    assert len(measurements) == len(loaded.references.cases) * len(by_chart[next(iter(by_chart))])
