from __future__ import annotations

import copy
import re
from typing import Any

import pytest

from benchmark.claims import (
    EVERYDAY_CHARTS,
    amount,
    control_sentence,
    fmt_up,
    headline,
    measured_deviation,
    quantity_line,
    quantity_reference,
    quantity_stats,
    subject,
    target_host,
    tier_sentences,
)
from benchmark.paths import RESULTS_DIR
from benchmark.results import JSON_FILE, read_results
from benchmark.schema import Chart, Unit, parse_references

REFS: dict[str, Any] = {
    "format": 1,
    "domain": "d",
    "sources": [
        {
            "name": "Horizons",
            "url": "https://x.invalid",
            "retrieved": "2026-01-01",
            "licence": "Public domain",
            "method": "Pulled",
        },
        {
            "name": "Horizons small-body integration",
            "url": "https://x.invalid",
            "retrieved": "2026-01-01",
            "licence": "Public domain",
            "method": "Pulled",
            "applies_to": ["Chiron"],
        },
    ],
    "tolerances": [{"applies_to": "*", "value": 36, "unit": "arcsec", "why": "Band"}],
    "cases": [
        {"id": "obama", "chart": "obama", "expected": {"Sun": 1.0, "Chiron": 2.0}},
        {"id": "jobs", "chart": "jobs", "expected": {"Sun": 1.0, "Chiron": 2.0}},
    ],
}


def m(case: str, quantity: str, dev: float | None, status: str = "PASS") -> dict[str, Any]:
    return {
        "case": case,
        "quantity": quantity,
        "unit": "arcsec",
        "deviation": dev,
        "status": status,
    }


DOMAIN: dict[str, Any] = {
    "id": "d",
    "title": "Western planets",
    "authority": "NASA JPL Horizons",
    "summaries": [
        {
            "unit": "arcsec",
            "points": 4,
            "passed": 4,
            "tiers": [
                {"limit": 10.0, "points": 4},
                {"limit": 1.0, "points": 4},
                {"limit": 0.1, "points": 2},
            ],
        },
    ],
    "measurements": [
        m("obama", "Sun", 0.04),
        m("jobs", "Sun", 0.08),
        m("obama", "Chiron", 0.31434),
        m("jobs", "Chiron", 0.2),
    ],
}


def doc(*domains: dict[str, Any], target: str = "https://roxyapi.com/api/v2") -> dict[str, Any]:
    return {"run": {"date": "2026-01-01", "target": target}, "domains": list(domains)}


def test_everyday_split_names_existing_charts_and_documents_every_edge(
    charts: dict[str, Chart],
) -> None:
    assert len(set(EVERYDAY_CHARTS)) == len(EVERYDAY_CHARTS)
    assert set(EVERYDAY_CHARTS) <= charts.keys()
    assert charts["einstein"].date.startswith("1879-")
    for chart in charts.values():
        if chart.id in EVERYDAY_CHARTS:
            assert 1950 <= int(chart.date[:4]) <= 2010
            continue
        assert re.search(
            r"pre-\d{4}|early \d{4}s|near-polar|high latitude|equator|"
            r"spring-forward|fall-back|midnight sun|rollover|skipped",
            chart.description,
            re.IGNORECASE,
        ), f"{chart.id} must describe the edge it tests"


def test_control_sentence_computes_both_maxima_from_the_committed_run(
    charts: dict[str, Chart],
) -> None:
    results = read_results(RESULTS_DIR / JSON_FILE)
    planets = next(d for d in results["domains"] if d["id"] == "western-planets")
    rows = [
        m for m in planets["measurements"] if m["unit"] == "arcsec" and m["deviation"] is not None
    ]
    everyday = [m for m in rows if m["case"] in EVERYDAY_CHARTS]
    everyday_max = max(m["deviation"] for m in everyday)
    full_max = max(m["deviation"] for m in rows)
    hardest = max(rows, key=lambda m: m["deviation"])["case"]
    suffix = f", with the {charts[hardest].date[:4]} chart the hardest"
    count = len({m["case"] for m in everyday})
    assert control_sentence(results) == (
        f"Picked from everyday modern charts alone, the {count} births from 1950 to 2010 at "
        f"ordinary latitudes, the planet maximum would read "
        f"{amount(everyday_max, Unit.ARCSEC, up=True, deg=True)}; the published "
        f"{amount(full_max, Unit.ARCSEC, up=True, deg=True)} comes from the edge cases{suffix}."
    )
    assert amount(full_max, Unit.ARCSEC, up=True, deg=True) in tier_sentences(results)[0]


@pytest.mark.parametrize("worst_case", ["einstein", "boston_1900"])
def test_control_sentence_tracks_changed_values_counts_and_worst_case(worst_case: str) -> None:
    everyday_max, full_max = 0.12345, 0.56789
    planets = {
        "id": "western-planets",
        "measurements": [
            m("jobs", "Sun", everyday_max),
            m("jobs", "Moon", everyday_max / 2),
            m("obama", "Sun", everyday_max / 3),
            m("beyonce", "Sun", None, "MISSING"),
            m(worst_case, "Sun", full_max),
            {**m("jobs", "instant", full_max * 10), "unit": "seconds"},
        ],
    }
    unrelated = {"id": "other", "measurements": [m("jobs", "Sun", full_max * 100)]}
    sentence = control_sentence(doc(unrelated, planets))
    assert "the 2 births" in sentence
    assert f"would read {amount(everyday_max, Unit.ARCSEC, up=True, deg=True)};" in sentence
    assert f"the published {amount(full_max, Unit.ARCSEC, up=True, deg=True)} comes" in sentence
    year = {"einstein": "1879", "boston_1900": "1900"}[worst_case]
    assert f"with the {year} chart the hardest" in sentence


def test_control_sentence_omits_an_unmeasured_or_absent_subset() -> None:
    assert control_sentence(doc(DOMAIN)) == ""
    for rows in ([], [m("einstein", "Sun", 1)], [m("jobs", "Sun", None, "MISSING")]):
        assert control_sentence(doc({"id": "western-planets", "measurements": rows})) == ""


@pytest.mark.parametrize(
    ("value", "shown"),
    [(0.31434, "0.32"), (0.3, "0.3"), (0.04, "0.04"), (9.91, "10"), (12.01, "12.1"), (0, "0")],
)
def test_fmt_up_never_rounds_down(value: float, shown: str) -> None:
    assert fmt_up(value) == shown
    assert float(shown.replace(",", "")) >= value


def test_tier_sentences_takes_the_tightest_tier_every_point_reaches() -> None:
    assert tier_sentences(doc(DOMAIN)) == [
        "For Western planets, RoxyAPI returned 4 of 4 positions within 1 arcsec (0.00028°) of "
        "NASA JPL Horizons."
    ]


def test_tier_sentences_is_per_domain_best_first_and_never_pooled() -> None:
    loose = copy.deepcopy(DOMAIN)
    loose["summaries"][0]["tiers"] = [{"limit": 10.0, "points": 3}, {"limit": 1.0, "points": 1}]
    other = {**copy.deepcopy(DOMAIN), "title": "Vedic", "authority": "Another"}
    assert tier_sentences(doc(loose, other)) == [
        "For Vedic, RoxyAPI returned 4 of 4 positions within 1 arcsec (0.00028°) of Another.",
        "For Western planets, RoxyAPI returned 3 of 4 positions within 10 arcsec (0.0028°) of "
        "NASA JPL Horizons.",
    ]
    assert headline(doc(loose, other))[0].startswith("For Vedic, RoxyAPI returned 4 of 4")


def test_a_fully_measured_summary_is_bounded_by_its_worst_value_with_labels() -> None:
    bounded = copy.deepcopy(DOMAIN)
    bounded["summaries"][0] |= {"max": 0.314, "missing": 0}
    names = {(bounded["id"], Unit.ARCSEC): "Sun, Moon, planets and Chiron"}
    assert tier_sentences(doc(bounded), names) == [
        "For the Sun, Moon, planets and Chiron, RoxyAPI returned 4 of 4 positions within "
        "0.32 arcsec (0.000089°) of NASA JPL Horizons."
    ]


def test_units_are_singular_for_one() -> None:
    assert amount(1.0, "seconds") == "1 second"
    assert amount(10.0, "seconds") == "10 seconds"
    assert amount(0.0, "days") == "0 days"
    assert amount(1.0, "arcsec") == "1 arcsec"
    assert amount(1.0, "days", up=True) == "1 day"


def test_headline_without_tiers_is_the_totals_alone() -> None:
    old = copy.deepcopy(DOMAIN)
    del old["summaries"][0]["tiers"]
    assert tier_sentences(doc(old)) == []
    assert headline(doc(old, target="https://api.example.com/v1")) == [
        "In the open accuracy benchmark run of 2026-01-01, api.example.com returned 4 of 4 "
        "values within tolerance across 1 domain, with a median angular deviation of 0.14 arcsec "
        "(0.000039°)."
    ]


def test_subject_is_roxyapi_only_for_its_own_api() -> None:
    assert subject(doc()) == "RoxyAPI"
    assert subject(doc(target="http://localhost:3000/api/v2")) == "localhost:3000"


def test_quantity_lines_bound_the_max_and_name_a_dedicated_source(
    charts: dict[str, Chart],
) -> None:
    refs = parse_references(REFS, "d", charts)
    assert quantity_reference(DOMAIN, refs, "Sun") == "NASA JPL Horizons"
    _, chiron = quantity_stats(DOMAIN, refs)
    assert quantity_line(chiron, "RoxyAPI") == (
        "RoxyAPI Chiron: every one of 2 charts within 0.32 arcsec (0.000089°) of Horizons "
        "small-body integration (median 0.26)."
    )
    assert chiron.worst_case == "obama"
    failing = copy.deepcopy(DOMAIN)
    failing["measurements"][1] = m("jobs", "Sun", 40.0, "FAIL")
    sun = quantity_stats(failing, refs)[0]
    assert quantity_line(sun, "RoxyAPI") == (
        "RoxyAPI Sun: 1 of 2 charts within the pass band of NASA JPL Horizons, largest "
        "deviation 40 arcsec (0.011°) (median 20)."
    )


def test_target_host_drops_scheme_and_path() -> None:
    assert target_host("https://roxyapi.com/api/v2") == "roxyapi.com"
    assert target_host("http://localhost:3000/api/v2") == "localhost:3000"


def _summary(
    unit: str, points: int, median: float, top: float, passed: int | None = None
) -> dict[str, Any]:
    return {
        "unit": unit,
        "points": points,
        "passed": points if passed is None else passed,
        "median": median,
        "max": top,
    }


def test_measured_deviation_names_each_unit_in_canonical_order() -> None:
    mixed = [
        _summary("exact", 638, 0, 0),
        _summary("days", 26, 0.2, 0.486),
        _summary("arcsec", 230, 0.0394, 1.4819),
    ]
    assert measured_deviation(mixed) == (
        "positions median 0.039, max 1.5 arcsec; days max 0.49; 638 exact"
    )


def test_measured_deviation_of_a_single_unit_drops_the_noun() -> None:
    assert measured_deviation([_summary("arcsec", 231, 0.0483, 0.3143)]) == (
        "median 0.048, max 0.32 arcsec"
    )
    assert measured_deviation([_summary("exact", 118, 0, 0)]) == "all exact"
    assert measured_deviation([_summary("days", 11, 0, 0)]) == "11 exact days"
    assert measured_deviation([_summary("seconds", 13, 0, 0)]) == "13 exact instants"
    assert measured_deviation([_summary("days", 11, 0.1, 0.3)]) == "max 0.3 days"


def test_measured_deviation_counts_exact_misses() -> None:
    assert measured_deviation([_summary("exact", 10, 0, 1, passed=9)]) == "9 of 10 exact"
