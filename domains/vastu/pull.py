"""Rebuild ``references.json`` from the entrance enumeration of the Brihat Samhita, offline.

The ground of a house is divided into nine by nine squares, numbered in the printed plate, and the
32 squares of its rim are the entrance padas. Chapter 53 of the Brihat Samhita names them in order
(verses 43 to 45 in the Iyer numbering: the eight eastern squares 1 to 8, the southern 9, 18, 27,
36, 45, 54, 63 and 72, the western 81 down to 74, the northern 73, 64, 55, 46, 37, 28, 19 and 10)
and gives the effect of a door on each (verses 72 to 75). Each list opens at a corner the verse
states: the north-east for the east side, the south-east for the south, the south-west for the west
and the north-west for the north. A corner square belongs to exactly one side, the side whose
list opens with it. Pada n of a side is the n-th square of its list and pada numbers run
1 to 8 east, 9 to 16 south, 17 to 24 west, 25 to 32 north, in the order the verses give the sides.

A door fraction runs 0 to 1 along a side from the corner its list opens at, so the side is cut
into eight equal parts and the part number is floor(fraction * 8) + 1, capped at 8 for the far end.
A bearing names a side when it lies within 22.5 degrees of a cardinal bearing: facing 0 looks out
north, 90 east, 180 south and 270 west. Bearings are kept clear of the 22.5 degree boundary
because no printed text divides the compass there.

The effect of each pada is read as one of three words: gain when the verse names a gain, harm when
it names a loss or a vice, mixed when it names both or an outcome that is neither. Two padas are
left unclassified because the two translations disagree on what the verse says, and a case that
lands on one checks its position and not its effect.
"""

from __future__ import annotations

from typing import Any

SIDES: tuple[tuple[str, str, tuple[int, ...]], ...] = (
    ("East", "Northeast", (1, 2, 3, 4, 5, 6, 7, 8)),
    ("South", "Southeast", (9, 18, 27, 36, 45, 54, 63, 72)),
    ("West", "Southwest", (81, 80, 79, 78, 77, 76, 75, 74)),
    ("North", "Northwest", (73, 64, 55, 46, 37, 28, 19, 10)),
)
"""Side, the corner its list opens at, and its eight squares in the order of verses 43 to 45."""

GRID = 9
"""Squares along one side of the plate: 81 in all."""

# Pada 1 to 32: Iyer 1884 phrase, Kern 1913 phrase (None where his text has no item), the
# effect word (None where the translations disagree).
EFFECTS: tuple[tuple[str, str | None, str | None], ...] = (
    ("injury from fire", "danger from fire", "harm"),
    ("birth of daughters", "birth of a girl", "mixed"),
    ("gain of immense wealth", "abundant wealth", "gain"),
    ("the friendship of the king", "favour with the monarch", "gain"),
    ("increase of anger", "wrathfulness", "harm"),
    ("the vice of lie", "falsehood", "harm"),
    ("that of cruelty", None, "harm"),
    ("that of theft", "thievishness", "harm"),
    ("few sons", "few sons", "harm"),
    ("servitude", "servitude", "harm"),
    ("becoming a chandala", "lowness", "harm"),
    (
        "excessive eating and drinking with an increase of sons",
        "increase of food, drink and progeny",
        None,
    ),
    ("anger", "cruelty", "harm"),
    ("ingratitude", "ungratefulness", "harm"),
    ("poverty", "poverty", "harm"),
    ("the loss of sons and of valor", "loss of children and strength", "harm"),
    ("suffering of sons", "suffering of a son", "harm"),
    ("the increase of the enemy", "increase of enemies", "harm"),
    ("the want of wealth and sons", "no acquisition of wealth or sons", "harm"),
    (
        "the increase of sons, of wealth and of strength",
        "happy possession of sons, wealth and power",
        "gain",
    ),
    ("opulence", "riches", "gain"),
    ("fear from kings", "danger from the king", "harm"),
    ("loss of wealth", "loss of wealth", "harm"),
    ("disease", "sickness", "harm"),
    ("increase of cruelty and kinsmen", "death or captivity", None),
    ("increase of the enemy", "increase of enemies", "harm"),
    ("gain of wealth and sons", "acquisition of wealth and sons", "gain"),
    ("the possession of all virtues", "happy possession of all good things", "gain"),
    ("the acquisition of sons and wealth", "getting sons and wealth", "gain"),
    ("hatred of sons", "enmity with one's own son", "harm"),
    ("the loss of character of women", "faults in the wife", "harm"),
    ("the loss of wealth", "poverty", "harm"),
)

KERN_EFFECT: dict[int, str] = {
    12: "gain",
    25: "harm",
}
"""The effect word the Kern rendering gives where it parts from Iyer: its increase of food, drink
and progeny names only gains, and its death or captivity names only harms."""

PADA_OF_SQUARE = {
    square: 8 * s + i + 1
    for s, (_, _, squares) in enumerate(SIDES)
    for i, square in enumerate(squares)
}
"""Rim square of the nine by nine plate to pada number."""


def side_of_bearing(bearing: float) -> int:
    """Index in ``SIDES`` of the cardinal side a facing bearing looks out toward."""
    sector = int(((bearing + 22.5) % 360) // 45)
    if sector % 2:
        raise ValueError(f"bearing {bearing} is an intercardinal facing and names no single side")
    return {0: 3, 2: 0, 4: 1, 6: 2}[sector]


def square_at(column_from_west: int, row_from_north: int) -> int:
    """Square number in the plate: 1 north-east, 9 south-east, 73 north-west, 81 south-west."""
    return (GRID - column_from_west) * GRID + row_from_north


def fraction_pada(bearing: float, fraction: float) -> int:
    side = side_of_bearing(bearing)
    ordinal = min(8, int(fraction * 8) + 1)
    return 8 * side + ordinal


def expected(pada: int) -> dict[str, Any]:
    side, _, squares = SIDES[(pada - 1) // 8]
    ordinal = (pada - 1) % 8 + 1
    values: dict[str, Any] = {
        "side": side,
        "ordinal_on_side": ordinal,
        "pada": pada,
        "square": squares[ordinal - 1],
    }
    effect = EFFECTS[pada - 1][2]
    if effect is not None:
        values["effect_category"] = effect
    return values


# (case id, facing bearing, fraction along the side from its opening corner, why the case is here)
FRACTION_CASES = (
    ("east-start-corner", 90, 0.0, "the opening corner of the east list is pada 1"),
    ("east-boundary-before", 90, 0.1249999, "just short of one eighth, still pada 1"),
    ("east-boundary-on", 90, 0.125, "exactly one eighth opens pada 2"),
    ("east-boundary-past", 90, 0.1250001, "just past one eighth, pada 2"),
    ("south-boundary-before", 180, 0.4999999, "just short of the middle, pada 12"),
    ("south-boundary-on", 180, 0.5, "the middle of the south side opens pada 13"),
    ("south-boundary-past", 180, 0.5000001, "just past the middle, pada 13"),
    ("south-mid-pada", 195, 0.6875, "a bearing 15 degrees past south, the middle of pada 14"),
    ("west-boundary-before", 270, 0.8749999, "just short of seven eighths, pada 23"),
    ("west-boundary-on", 270, 0.875, "exactly seven eighths opens the last west pada, 24"),
    ("west-far-end", 270, 1.0, "the far corner of the west list is still pada 24"),
    ("west-edge-of-sector", 247.6, 0.0, "a bearing just inside the west sector, pada 17"),
    (
        "north-boundary-before",
        360,
        0.2499999,
        "facing 360 is north; just short of a quarter, pada 26",
    ),
    ("north-boundary-on", 0, 0.25, "exactly a quarter opens pada 27"),
    (
        "north-boundary-past",
        15,
        0.2500001,
        "just past a quarter, 15 degrees east of north, pada 27",
    ),
    ("north-edge-of-sector", 337.6, 0.9999999, "a bearing just inside the north sector, pada 32"),
)

# (case id, facing bearing, door x east, door y north, why the case is here), plot 90 by 90 feet
DOOR_CASES = (
    (
        "door-northeast-corner-square",
        90,
        89,
        89,
        "the north-east corner square is square 1, pada 1",
    ),
    (
        "door-corner-square-belongs-south",
        90,
        89,
        5,
        "a door on the east edge in the south-east corner square reads South: verse 44 opens the "
        "south list with square 9",
    ),
    (
        "door-corner-square-belongs-west",
        180,
        5,
        1,
        "a door on the south edge in the south-west corner square reads West: verse 45 opens the "
        "west list with square 81",
    ),
    (
        "door-corner-square-belongs-north",
        270,
        1,
        89,
        "a door on the west edge in the north-west corner square reads North: verse 45 opens the "
        "north list with square 73",
    ),
    ("door-east-fourth-square", 90, 90, 55, "the fourth square down the east edge, pada 4"),
    ("door-south-middle-square", 180, 45, 0, "the middle of the south edge is square 45, pada 13"),
    (
        "door-north-last-square",
        0,
        75,
        90,
        "the eighth square of the north list sits second from the east end of the north edge",
    ),
    (
        "door-decides-the-side",
        40,
        45,
        1,
        "a bearing that names no single side with the door on the south edge: the door decides",
    ),
)


def door_pada(x: float, y: float) -> int:
    """Pada of a door on the rim of the 90 foot plate, by the printed squares."""
    column = min(GRID - 1, int(x // 10)) + 1
    row = GRID - min(GRID - 1, int(y // 10))
    return PADA_OF_SQUARE[square_at(column, row)]


def fraction_case(case_id: str, bearing: float, fraction: float) -> dict[str, Any]:
    return {
        "id": case_id,
        "input": {"facing_degrees": bearing, "door_position": fraction},
        "expected": expected(fraction_pada(bearing, fraction)),
    }


def door_case(case_id: str, bearing: float, x: float, y: float) -> dict[str, Any]:
    return {
        "id": case_id,
        "input": {"facing_degrees": bearing, "door_x": x, "door_y": y},
        "expected": expected(door_pada(x, y)),
    }


def cross_checks() -> list[dict[str, Any]]:
    """The effect word of every pada as the Kern rendering gives it, for the test to reproduce."""
    return [
        {
            "id": f"pada-{pada}-kern",
            "source": "Kern, Verspreide Geschriften vol. 2",
            "input": {"pada": pada},
            "expected": {"effect_category": KERN_EFFECT.get(pada, EFFECTS[pada - 1][2])},
        }
        for pada in range(1, 33)
        if EFFECTS[pada - 1][1] is not None
    ]


def pull() -> dict[str, Any]:
    return {
        "format": 1,
        "domain": "vastu",
        "sources": [
            {
                "name": "Varahamihira, Brihat Samhita, translated by N. Chidambaram Iyer",
                "url": "https://archive.org/details/b29353130",
                "command": "python -m benchmark pull vastu",
                "retrieved": "2026-10-09",
                "licence": "Public domain translation, Madura, 1884; values only",
                "citation": (
                    "Varahamihira, The Brihat Samhita, translated into English by N. Chidambaram "
                    "Iyer, Madura, South Indian Press, 1884, chapter 53 (the sixth chapter of the "
                    "volume part on architecture), verses 42 to 45 for the squares and 71 to 75 "
                    "for the effects"
                ),
                "method": (
                    "The nine by nine plate and the squares of its rim were transcribed from "
                    "verses 42 to 45, the effect of a door on each rim square from verses 72 to "
                    "75. Each list opens at the corner its verse names, and a corner square "
                    "belongs to the side whose list opens with it. A side is cut into eight equal "
                    "parts counted from that corner, and a facing bearing names the cardinal "
                    "side it looks out toward within 22.5 degrees."
                ),
                "applies_to": ["side", "ordinal_on_side", "pada", "square", "effect_category"],
                "notes": (
                    "The effect word is a reading of the verse: gain, harm, or mixed where the "
                    "verse names both or neither. It is asserted only where the Iyer and Kern "
                    "translations agree on it."
                ),
            },
            {
                "name": "Kern, Verspreide Geschriften vol. 2",
                "url": "https://archive.org/details/in.gov.ignca.10715",
                "retrieved": "2026-10-09",
                "licence": "Public domain translation, The Hague, 1913; values only",
                "citation": (
                    "Hendrik Kern, translation of the Brhat Sanhita of Varahamihira, in Verspreide "
                    "Geschriften vol. 2, The Hague, 1913, chapter 53, verses 71 to 75"
                ),
                "method": (
                    "The effect words of verses 72 to 75 were read in a second, independent "
                    "translation and classified by the same rule as the first. Where it renders "
                    "an effect with different words that name the same kind of outcome, the "
                    "classification agrees. Where it differs, the pada is left unclassified."
                ),
                "applies_to": ["effect_category"],
            },
        ],
        "families": [
            {
                "label": "Entrance side and pada from facing bearing and door position",
                "quantities": ["side", "ordinal_on_side", "pada"],
            },
            {"label": "Square of the nine by nine plan", "quantities": ["square"]},
            {"label": "Classical effect of the entrance pada", "quantities": ["effect_category"]},
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": (
                    "A pada, a side, a square and an effect word are discrete: one square off "
                    "names a different deity and a different verdict."
                ),
            }
        ],
        "cases": [fraction_case(c, b, f) for c, b, f, _ in FRACTION_CASES]
        + [door_case(c, b, x, y) for c, b, x, y, _ in DOOR_CASES],
        "cross_checks": cross_checks(),
    }
