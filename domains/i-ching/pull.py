"""Rebuild ``references.json`` from the King Wen sequence and the trigram table, offline.

The deterministic part of the I Ching is a lookup: six line values give a hexagram, and the
number of a hexagram is its place in the King Wen sequence. The sequence has no formula, so it is a
published table: for each of the 64 hexagrams, the trigram on the lower three lines and the trigram
on the upper three. A trigram is three lines read from the bottom, and its line pattern is
recomputed from the Unicode trigram block (code points in the traditional order, each named
for its trigram).

Cast values follow the three coin and yarrow stalk convention in Legge, The Yi King (Sacred Books of
the East vol. 16, Oxford, 1899), Appendix V chapter 2 note, p. 423: 9 is the old yang, 8 the young
yin, 7 the young yang and 6 the old yin. Old lines (6 and 9) are the changing lines, and the
relating hexagram is the primary with every changing line turned into its opposite.

Legge, whose lines are numbered from the lowest (Introduction chapter 2), is the second source: his
Great Symbolism (Appendix II) names the two trigrams of each hexagram, and a test asserts the table
agrees with every one he states.
"""

from __future__ import annotations

import unicodedata
from typing import Any

LOWER_UPPER: tuple[tuple[str, str], ...] = (
    ("Heaven", "Heaven"),  # 1
    ("Earth", "Earth"),  # 2
    ("Thunder", "Water"),  # 3
    ("Water", "Mountain"),  # 4
    ("Heaven", "Water"),  # 5
    ("Water", "Heaven"),  # 6
    ("Water", "Earth"),  # 7
    ("Earth", "Water"),  # 8
    ("Heaven", "Wind"),  # 9
    ("Lake", "Heaven"),  # 10
    ("Heaven", "Earth"),  # 11
    ("Earth", "Heaven"),  # 12
    ("Fire", "Heaven"),  # 13
    ("Heaven", "Fire"),  # 14
    ("Mountain", "Earth"),  # 15
    ("Earth", "Thunder"),  # 16
    ("Thunder", "Lake"),  # 17
    ("Wind", "Mountain"),  # 18
    ("Lake", "Earth"),  # 19
    ("Earth", "Wind"),  # 20
    ("Thunder", "Fire"),  # 21
    ("Fire", "Mountain"),  # 22
    ("Earth", "Mountain"),  # 23
    ("Thunder", "Earth"),  # 24
    ("Thunder", "Heaven"),  # 25
    ("Heaven", "Mountain"),  # 26
    ("Thunder", "Mountain"),  # 27
    ("Wind", "Lake"),  # 28
    ("Water", "Water"),  # 29
    ("Fire", "Fire"),  # 30
    ("Mountain", "Lake"),  # 31
    ("Wind", "Thunder"),  # 32
    ("Mountain", "Heaven"),  # 33
    ("Heaven", "Thunder"),  # 34
    ("Earth", "Fire"),  # 35
    ("Fire", "Earth"),  # 36
    ("Fire", "Wind"),  # 37
    ("Lake", "Fire"),  # 38
    ("Mountain", "Water"),  # 39
    ("Water", "Thunder"),  # 40
    ("Lake", "Mountain"),  # 41
    ("Thunder", "Wind"),  # 42
    ("Heaven", "Lake"),  # 43
    ("Wind", "Heaven"),  # 44
    ("Earth", "Lake"),  # 45
    ("Wind", "Earth"),  # 46
    ("Water", "Lake"),  # 47
    ("Wind", "Water"),  # 48
    ("Fire", "Lake"),  # 49
    ("Wind", "Fire"),  # 50
    ("Thunder", "Thunder"),  # 51
    ("Mountain", "Mountain"),  # 52
    ("Mountain", "Wind"),  # 53
    ("Lake", "Thunder"),  # 54
    ("Fire", "Thunder"),  # 55
    ("Mountain", "Fire"),  # 56
    ("Wind", "Wind"),  # 57
    ("Lake", "Lake"),  # 58
    ("Water", "Wind"),  # 59
    ("Lake", "Water"),  # 60
    ("Lake", "Wind"),  # 61
    ("Mountain", "Thunder"),  # 62
    ("Fire", "Water"),  # 63
    ("Water", "Fire"),  # 64
)
"""Lower and upper trigram of hexagram 1 to 64 in King Wen order, from the published list."""

LEGGE_PAIRS: dict[int, tuple[str, ...]] = {
    1: ("Heaven",),
    2: ("Earth",),
    3: ("Thunder", "Water"),
    4: ("Mountain", "Water"),
    5: ("Heaven", "Water"),
    6: ("Heaven", "Water"),
    7: ("Earth", "Water"),
    8: ("Earth", "Water"),
    9: ("Heaven", "Wind"),
    10: ("Heaven", "Lake"),
    11: ("Earth", "Heaven"),
    12: ("Earth", "Heaven"),
    13: ("Fire", "Heaven"),
    14: ("Fire", "Heaven"),
    15: ("Earth", "Mountain"),
    16: ("Earth", "Thunder"),
    17: ("Lake", "Thunder"),
    18: ("Mountain", "Wind"),
    19: ("Earth", "Lake"),
    20: ("Earth", "Wind"),
    21: ("Fire", "Thunder"),
    22: ("Fire", "Mountain"),
    23: ("Earth", "Mountain"),
    24: ("Earth", "Thunder"),
    25: ("Heaven", "Thunder"),
    26: ("Heaven", "Mountain"),
    27: ("Mountain", "Thunder"),
    28: ("Lake", "Wind"),
    29: ("Water",),
    30: ("Fire",),
    31: ("Lake", "Mountain"),
    32: ("Thunder", "Wind"),
    33: ("Heaven", "Mountain"),
    34: ("Heaven", "Thunder"),
    35: ("Earth", "Fire"),
    36: ("Earth", "Fire"),
    37: ("Fire", "Wind"),
    39: ("Mountain", "Water"),
    40: ("Thunder", "Water"),
    41: ("Lake", "Mountain"),
    42: ("Thunder", "Wind"),
    43: ("Heaven", "Lake"),
    44: ("Heaven", "Wind"),
    45: ("Earth", "Lake"),
    46: ("Earth", "Wind"),
    47: ("Lake", "Water"),
    48: ("Water", "Wind"),
    49: ("Fire", "Lake"),
    50: ("Fire", "Wind"),
    51: ("Thunder",),
    52: ("Mountain",),
    53: ("Mountain", "Wind"),
    54: ("Lake", "Thunder"),
    55: ("Fire", "Thunder"),
    56: ("Fire", "Mountain"),
    57: ("Wind",),
    58: ("Lake",),
    59: ("Water", "Wind"),
    60: ("Lake", "Water"),
    61: ("Lake", "Wind"),
    62: ("Mountain", "Thunder"),
    63: ("Fire", "Water"),
    64: ("Fire", "Water"),
}
"""The trigrams Legge names in the Great Symbolism of each hexagram, unordered; a single name is
a trigram doubled. Hexagram 38 is missing: its sentence is not legible in the scanned copy."""

UNICODE_TRIGRAM_FIRST = 0x2630
"""U+2630 TRIGRAM FOR HEAVEN; the eight trigram code points follow in the traditional order."""

UNICODE_HEXAGRAM_FIRST = 0x4DC0
"""U+4DC0, hexagram 1; the 64 hexagram code points follow in King Wen order."""

CHANGING = (6, 9)
YANG = (7, 9)
VALUES = (6, 7, 8, 9)


def trigram_patterns() -> dict[str, str]:
    """Trigram name to its three line pattern, bottom to top, 1 solid and 0 broken.

    The traditional order runs from three solid lines (111) counting down to three broken (000).
    """
    patterns = {}
    for i in range(8):
        name = unicodedata.name(chr(UNICODE_TRIGRAM_FIRST + i)).removeprefix("TRIGRAM FOR ")
        patterns[name.title()] = format(7 - i, "03b")
    return patterns


TRIGRAMS = trigram_patterns()


def hexagram_pattern(number: int) -> str:
    lower, upper = LOWER_UPPER[number - 1]
    return TRIGRAMS[lower] + TRIGRAMS[upper]


PATTERN_TO_NUMBER = {hexagram_pattern(n): n for n in range(1, 65)}


def pattern_of(values: tuple[int, ...], *, changed: bool) -> str:
    """Line pattern of a cast, bottom to top; ``changed`` flips every changing line."""
    bits = []
    for v in values:
        yang = v in YANG
        bits.append("1" if yang != (changed and v in CHANGING) else "0")
    return "".join(bits)


# (case id, line values from the bottom line to the top line, why the case is here)
CASTS = (
    ("hexagram-1", (7, 7, 7, 7, 7, 7), "six young yang lines, hexagram 1, nothing changes"),
    ("hexagram-2", (8, 8, 8, 8, 8, 8), "six young yin lines, hexagram 2, nothing changes"),
    ("all-lines-changing-yang", (9,) * 6, "six old yang lines turn hexagram 1 into hexagram 2"),
    ("all-lines-changing-yin", (6,) * 6, "six old yin lines turn hexagram 2 into hexagram 1"),
    ("peace", (7, 7, 7, 8, 8, 8), "heaven below earth is 11; the reverse order would read 12"),
    ("standstill", (8, 8, 8, 7, 7, 7), "earth below heaven is 12; the reverse order would read 11"),
    ("after-completion", (7, 8, 7, 8, 7, 8), "alternating lines, hexagram 63, nothing changes"),
    ("bottom-line-changing", (6, 8, 8, 8, 8, 8), "one changing line at the bottom, 2 into 24"),
    ("top-line-changing", (7, 7, 7, 7, 7, 9), "one changing line at the top, 1 into 43"),
    ("mixed-two-changing", (9, 8, 7, 8, 6, 7), "two changing lines, 22 into 53"),
    ("mixed-three-changing", (6, 7, 9, 8, 8, 6), "three changing lines, 46 into 41"),
    (
        "no-change-mixed",
        (8, 7, 8, 7, 8, 7),
        "an asymmetric cast with no changing line, hexagram 64",
    ),
)


def cast_case(case_id: str, values: tuple[int, ...]) -> dict[str, Any]:
    primary = pattern_of(values, changed=False)
    expected: dict[str, Any] = {
        "primary_hexagram": PATTERN_TO_NUMBER[primary],
        "primary_lower_trigram": next(n for n, p in TRIGRAMS.items() if p == primary[:3]),
        "primary_upper_trigram": next(n for n, p in TRIGRAMS.items() if p == primary[3:]),
    }
    case_input: dict[str, Any] = {"line_values": list(values), "primary_lines": primary}
    if any(v in CHANGING for v in values):
        relating = pattern_of(values, changed=True)
        expected["relating_hexagram"] = PATTERN_TO_NUMBER[relating]
        case_input["relating_lines"] = relating
    return {"id": case_id, "input": case_input, "expected": expected}


def trigram_case(name: str) -> dict[str, Any]:
    return {
        "id": f"trigram-{name.lower()}",
        "input": {"trigram": name},
        "expected": {"trigram_lines": TRIGRAMS[name]},
    }


def hexagram_case(number: int) -> dict[str, Any]:
    lower, upper = LOWER_UPPER[number - 1]
    return {
        "id": f"king-wen-{number}",
        "input": {"hexagram": number},
        "expected": {
            "hexagram_lines": hexagram_pattern(number),
            "hexagram_lower_trigram": lower,
            "hexagram_upper_trigram": upper,
            "hexagram_symbol": chr(UNICODE_HEXAGRAM_FIRST + number - 1),
        },
    }


def pull() -> dict[str, Any]:
    return {
        "format": 1,
        "domain": "i-ching",
        "sources": [
            {
                "name": "List of hexagrams of the I Ching",
                "url": "https://en.wikipedia.org/wiki/List_of_hexagrams_of_the_I_Ching",
                "command": "python -m benchmark pull i-ching",
                "retrieved": "2026-10-09",
                "licence": "King Wen sequence, facts only; the page is CC BY-SA",
                "method": (
                    "The lower and upper trigram of each of the 64 hexagrams in King Wen order "
                    "were transcribed from the list. The line pattern of a hexagram is its lower "
                    "trigram followed by its upper trigram, bottom line first, and its number is "
                    "its place in the list. The relating hexagram is the primary with each "
                    "changing line (6 or 9) turned into its opposite."
                ),
                "applies_to": [
                    "hexagram_lines",
                    "hexagram_lower_trigram",
                    "hexagram_upper_trigram",
                    "primary_hexagram",
                    "primary_lower_trigram",
                    "primary_upper_trigram",
                    "relating_hexagram",
                ],
                "notes": (
                    "The sequence is a published table with no formula. Only casts that give the "
                    "line values directly are measured: the casting endpoints draw their lines "
                    "from a seed, so their output has no independent reference."
                ),
            },
            {
                "name": "The Unicode Standard, trigram and hexagram blocks",
                "url": "https://www.unicode.org/charts/PDF/U4DC0.pdf",
                "retrieved": "2026-10-09",
                "licence": "Unicode character names and order, public specification",
                "method": (
                    "The eight trigram code points U+2630 to U+2637 are named for Heaven, Lake, "
                    "Fire, Thunder, Wind, Water, Mountain and Earth in the traditional order, "
                    "which counts down from three solid lines to three broken lines. The line "
                    "pattern of each trigram is recomputed from that order. The 64 hexagram "
                    "code points from U+4DC0 follow the King Wen sequence, so the symbol of "
                    "hexagram n is the code point U+4DC0 plus n minus 1."
                ),
                "applies_to": ["trigram_lines", "hexagram_symbol"],
            },
            {
                "name": "Legge, The Yi King, Sacred Books of the East vol. 16",
                "url": "https://archive.org/details/mlbd.sacredbooksofeas0000fmax.vol.16",
                "retrieved": "2026-10-09",
                "licence": "Public domain translation, Oxford, 1899; values only",
                "method": (
                    "The line values 9 old yang, 8 young yin, 7 young yang and 6 old yin follow "
                    "Appendix V chapter 2 note, p. 423. The trigrams of each hexagram are the "
                    "ones named in the Great Symbolism, Appendix II, and the recomputed table is "
                    "asserted to agree with every one the scanned copy states."
                ),
                "citation": (
                    "James Legge, The Yi King, Sacred Books of the East vol. 16, Oxford, 1899, "
                    "Appendix II and Appendix V"
                ),
                "applies_to": ["primary_hexagram", "relating_hexagram"],
            },
        ],
        "families": [
            {
                "label": "King Wen hexagrams and trigrams",
                "quantities": [
                    "primary_hexagram",
                    "primary_lower_trigram",
                    "primary_upper_trigram",
                    "relating_hexagram",
                    "trigram_lines",
                    "hexagram_lines",
                    "hexagram_lower_trigram",
                    "hexagram_upper_trigram",
                    "hexagram_symbol",
                ],
            },
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": (
                    "A hexagram number, a trigram and a line pattern are discrete: a transposed "
                    "pair of trigrams or a reversed line order names a different hexagram."
                ),
            }
        ],
        "cases": [cast_case(c, v) for c, v, _ in CASTS]
        + [trigram_case(n) for n in TRIGRAMS]
        + [hexagram_case(n) for n in range(1, 65)],
    }
