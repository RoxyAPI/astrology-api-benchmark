"""The entrance enumeration is the rim of the nine by nine plate, and the two translations agree."""

from __future__ import annotations

import pytest

from benchmark.domains import PULL_FILE, load_module
from benchmark.paths import DOMAINS_DIR

module = load_module(DOMAINS_DIR / "vastu", PULL_FILE)


def test_the_32_listed_squares_are_exactly_the_rim_of_the_plate() -> None:
    listed = [square for _, _, squares in module.SIDES for square in squares]
    rim = {
        module.square_at(column, row)
        for column in range(1, 10)
        for row in range(1, 10)
        if column in (1, 9) or row in (1, 9)
    }
    assert len(listed) == 32
    assert set(listed) == rim


@pytest.mark.parametrize(
    ("square", "pada"), [(1, 1), (8, 8), (9, 9), (72, 16), (81, 17), (74, 24), (73, 25), (10, 32)]
)
def test_corner_squares_belong_to_the_side_whose_list_opens_with_them(
    square: int, pada: int
) -> None:
    assert module.PADA_OF_SQUARE[square] == pada


def test_each_list_opens_at_a_corner_square() -> None:
    first = {side: squares[0] for side, _, squares in module.SIDES}
    assert first == {"East": 1, "South": 9, "West": 81, "North": 73}


@pytest.mark.parametrize(
    ("bearing", "side"), [(0, 3), (360, 3), (22.4, 3), (337.6, 3), (90, 0), (180, 1), (270, 2)]
)
def test_bearing_names_the_cardinal_side_it_looks_out_toward(bearing: float, side: int) -> None:
    assert module.side_of_bearing(bearing) == side


def test_an_intercardinal_bearing_names_no_side() -> None:
    with pytest.raises(ValueError, match="intercardinal"):
        module.side_of_bearing(45)


@pytest.mark.parametrize(
    ("fraction", "ordinal"), [(0.0, 1), (0.1249999, 1), (0.125, 2), (0.875, 8), (1.0, 8)]
)
def test_eighths_open_at_exact_multiples(fraction: float, ordinal: int) -> None:
    assert module.fraction_pada(90, fraction) == ordinal


def test_the_second_translation_reproduces_every_effect_word() -> None:
    crossed = module.cross_checks()
    assert len(crossed) == 31
    for check in crossed:
        pada = int(check["input"]["pada"])
        iyer = module.EFFECTS[pada - 1][2]
        kern = check["expected"]["effect_category"]
        assert iyer in (None, kern), pada


def test_only_the_two_disputed_padas_are_unclassified() -> None:
    unclassified = [n for n, (_, _, effect) in enumerate(module.EFFECTS, 1) if effect is None]
    assert unclassified == [12, 25]
    assert set(module.KERN_EFFECT) == set(unclassified)


def test_the_classification_counts_follow_the_reading() -> None:
    words = [effect for _, _, effect in module.EFFECTS]
    assert (words.count("gain"), words.count("mixed"), words.count("harm")) == (7, 1, 22)
