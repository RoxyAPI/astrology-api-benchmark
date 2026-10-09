"""The King Wen table agrees with the second source, and the cast rule behaves as defined."""

from __future__ import annotations

import pytest

from benchmark.domains import PULL_FILE, load_module
from benchmark.paths import DOMAINS_DIR

module = load_module(DOMAINS_DIR / "i-ching", PULL_FILE)


def test_sequence_has_64_distinct_hexagrams_and_each_pair_of_trigrams_once() -> None:
    assert len(set(module.LOWER_UPPER)) == 64
    assert len(module.PATTERN_TO_NUMBER) == 64


def test_table_names_the_same_trigrams_as_every_hexagram_legge_states() -> None:
    legge = module.LEGGE_PAIRS
    assert len(legge) == 63
    for number, names in legge.items():
        assert set(module.LOWER_UPPER[number - 1]) == set(names), number


def test_trigram_patterns_come_from_the_unicode_block() -> None:
    assert module.TRIGRAMS == {
        "Heaven": "111",
        "Lake": "110",
        "Fire": "101",
        "Thunder": "100",
        "Wind": "011",
        "Water": "010",
        "Mountain": "001",
        "Earth": "000",
    }


@pytest.mark.parametrize(
    ("number", "pair"),
    [(1, ("Heaven", "Heaven")), (2, ("Earth", "Earth")), (11, ("Heaven", "Earth"))],
)
def test_anchor_hexagrams(number: int, pair: tuple[str, str]) -> None:
    assert module.LOWER_UPPER[number - 1] == pair


def test_king_wen_pairs_are_reversals_or_inversions() -> None:
    for odd in range(1, 64, 2):
        first, second = module.hexagram_pattern(odd), module.hexagram_pattern(odd + 1)
        reversed_first = first[::-1]
        inverted_first = "".join("1" if bit == "0" else "0" for bit in first)
        assert second in (reversed_first, inverted_first), odd


def test_relating_hexagram_flips_only_old_lines() -> None:
    pattern_of = module.pattern_of
    assert pattern_of((9, 8, 7, 6, 8, 7), changed=False) == "101001"
    assert pattern_of((9, 8, 7, 6, 8, 7), changed=True) == "001101"
    assert pattern_of((7, 8, 7, 8, 7, 8), changed=True) == pattern_of(
        (7, 8, 7, 8, 7, 8), changed=False
    )
