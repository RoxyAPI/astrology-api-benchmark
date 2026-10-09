from __future__ import annotations

import copy
from typing import Any

import pytest

from benchmark.claims import (
    amount,
    fmt_up,
    headline,
    quantity_line,
    quantity_reference,
    quantity_stats,
    subject,
    target_host,
    tier_figures,
    tier_sentences,
)
from benchmark.schema import Chart, parse_references

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
        "RoxyAPI returned 4 of 4 positions within 1 arcsec of NASA JPL Horizons in the Western "
        "planets domain."
    ]
    assert tier_figures(DOMAIN["summaries"][0]) == (
        "4 within 10 arcsec, 4 within 1 arcsec, 2 within 0.1 arcsec"
    )


def test_tier_sentences_is_per_domain_best_first_and_never_pooled() -> None:
    loose = copy.deepcopy(DOMAIN)
    loose["summaries"][0]["tiers"] = [{"limit": 10.0, "points": 3}, {"limit": 1.0, "points": 1}]
    other = {**copy.deepcopy(DOMAIN), "title": "Vedic", "authority": "Another"}
    assert tier_sentences(doc(loose, other)) == [
        "RoxyAPI returned 4 of 4 positions within 1 arcsec of Another in the Vedic domain.",
        "RoxyAPI returned 3 of 4 positions within 10 arcsec of NASA JPL Horizons in the Western "
        "planets domain.",
    ]
    assert headline(doc(loose, other))[0].endswith("of Another in the Vedic domain.")


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
        "values within tolerance across 1 domain, with a median angular deviation of 0.14 arcsec."
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
        "RoxyAPI Chiron: every one of 2 charts within 0.32 arcsec of Horizons small-body "
        "integration (median 0.26)."
    )
    assert chiron.worst_case == "obama"
    failing = copy.deepcopy(DOMAIN)
    failing["measurements"][1] = m("jobs", "Sun", 40.0, "FAIL")
    sun = quantity_stats(failing, refs)[0]
    assert quantity_line(sun, "RoxyAPI") == (
        "RoxyAPI Sun: 1 of 2 charts within the pass band of NASA JPL Horizons, largest "
        "deviation 40 arcsec (median 20)."
    )


def test_target_host_drops_scheme_and_path() -> None:
    assert target_host("https://roxyapi.com/api/v2") == "roxyapi.com"
    assert target_host("http://localhost:3000/api/v2") == "localhost:3000"
