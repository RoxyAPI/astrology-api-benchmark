from __future__ import annotations

import copy
from typing import Any

import pytest

from benchmark.claims import (
    amount,
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
    assert measured_deviation([_summary("days", 11, 0.1, 0.3)]) == "max 0.3 days"


def test_measured_deviation_counts_exact_misses() -> None:
    assert measured_deviation([_summary("exact", 10, 0, 1, passed=9)]) == "9 of 10 exact"
