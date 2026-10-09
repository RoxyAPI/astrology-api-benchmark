"""Human Design references: the wheel reproduces the published gate table, the cross check
reproduces the Rave New Year, and every derived value follows from the rules."""

from __future__ import annotations

import json
from datetime import timedelta
from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import REFERENCES_FILE, load_module
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import load_charts, parse_instant

FOLDER = DOMAINS_DIR / "human-design"
SIGNS = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
)  # fmt: skip

# The opening degree and minute of every gate as the published table prints them, in zodiac
# order from Aries (Human Design Gates by Zodiac Degrees, bonniesorsby.com). The table truncates
# to the minute: 7 deg 37 min 30 sec prints as 7 deg 37 min.
PUBLISHED_GATE_STARTS: tuple[tuple[int, str, int, int], ...] = (
    (17, "Aries", 3, 52), (21, "Aries", 9, 30), (51, "Aries", 15, 7),
    (42, "Aries", 20, 45), (3, "Aries", 26, 22), (27, "Taurus", 2, 0),
    (24, "Taurus", 7, 37), (2, "Taurus", 13, 15), (23, "Taurus", 18, 52),
    (8, "Taurus", 24, 30), (20, "Gemini", 0, 7), (16, "Gemini", 5, 45),
    (35, "Gemini", 11, 22), (45, "Gemini", 17, 0), (12, "Gemini", 22, 37),
    (15, "Gemini", 28, 15), (52, "Cancer", 3, 52), (39, "Cancer", 9, 30),
    (53, "Cancer", 15, 7), (62, "Cancer", 20, 45), (56, "Cancer", 26, 22),
    (31, "Leo", 2, 0), (33, "Leo", 7, 37), (7, "Leo", 13, 15),
    (4, "Leo", 18, 52), (29, "Leo", 24, 30), (59, "Virgo", 0, 7),
    (40, "Virgo", 5, 45), (64, "Virgo", 11, 22), (47, "Virgo", 17, 0),
    (6, "Virgo", 22, 37), (46, "Virgo", 28, 15), (18, "Libra", 3, 52),
    (48, "Libra", 9, 30), (57, "Libra", 15, 7), (32, "Libra", 20, 45),
    (50, "Libra", 26, 22), (28, "Scorpio", 2, 0), (44, "Scorpio", 7, 37),
    (1, "Scorpio", 13, 15), (43, "Scorpio", 18, 52), (14, "Scorpio", 24, 30),
    (34, "Sagittarius", 0, 7), (9, "Sagittarius", 5, 45), (5, "Sagittarius", 11, 22),
    (26, "Sagittarius", 17, 0), (11, "Sagittarius", 22, 37), (10, "Sagittarius", 28, 15),
    (58, "Capricorn", 3, 52), (38, "Capricorn", 9, 30), (54, "Capricorn", 15, 7),
    (61, "Capricorn", 20, 45), (60, "Capricorn", 26, 22), (41, "Aquarius", 2, 0),
    (19, "Aquarius", 7, 37), (13, "Aquarius", 13, 15), (49, "Aquarius", 18, 52),
    (30, "Aquarius", 24, 30), (55, "Pisces", 0, 7), (37, "Pisces", 5, 45),
    (63, "Pisces", 11, 22), (22, "Pisces", 17, 0), (36, "Pisces", 22, 37),
    (25, "Pisces", 28, 15),
)  # fmt: skip
DESIGN_LEAD_DAYS = (86.5, 92.5)
"""The 88 degree arc takes between these many days, slowest near aphelion."""


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    """The pull module itself, for its definitions; nothing here contacts a source."""
    return load_module(FOLDER, "pull.py")


@pytest.fixture(scope="module")
def references() -> dict[str, Any]:
    document: dict[str, Any] = json.loads((FOLDER / REFERENCES_FILE).read_text(encoding="utf-8"))
    return document


def test_wheel_reproduces_the_published_gate_table(pull: ModuleType) -> None:
    assert sorted(pull.WHEEL) == list(range(1, 65))
    assert len(PUBLISHED_GATE_STARTS) == 64
    for gate, sign, degree, minute in PUBLISHED_GATE_STARTS:
        start = (pull.WHEEL_START + pull.WHEEL.index(gate) * pull.GATE_SPAN) % 360
        assert int(start // 30) == SIGNS.index(sign), gate
        assert (int(start % 30), int(start % 1 * 60 + 1e-9)) == (degree, minute), gate
        assert pull.gate_line(start + 1e-9) == (gate, 1)


def test_cross_check_reproduces_the_rave_new_year(references: dict[str, Any]) -> None:
    cases = {c["id"]: c for c in references["cases"]}
    (cross,) = references["cross_checks"]
    case = cases[cross["id"]]
    assert case["input"] == cross["input"]
    for quantity, published in cross["expected"].items():
        assert case["expected"][quantity] == published


def test_derived_values_follow_from_the_rules(pull: ModuleType, references: dict[str, Any]) -> None:
    for case in references["cases"]:
        expected = case["expected"]
        for side in ("personality", "design"):
            sun = pull.WHEEL.index(expected[f"{side} Sun gate"])
            assert pull.WHEEL[(sun + 32) % 64] == expected[f"{side} Earth gate"], case["id"]
            assert expected[f"{side} Earth line"] == expected[f"{side} Sun line"], case["id"]
        lines = (expected["personality Sun line"], expected["design Sun line"])
        assert expected["profile"] == "{}/{}".format(*lines)


def test_design_instant_sits_about_three_months_before_birth(
    references: dict[str, Any],
) -> None:
    charts = load_charts()
    for case in references["cases"]:
        body = case.get("input")
        birth = (
            parse_instant(f"{body['date']}T{body['time']}+00:00")
            if body
            else charts[case["chart"]].utc()
        )
        design = parse_instant(case["expected"]["design instant"])
        assert birth is not None and design is not None
        lead = birth - design
        assert timedelta(days=DESIGN_LEAD_DAYS[0]) < lead < timedelta(days=DESIGN_LEAD_DAYS[1])
