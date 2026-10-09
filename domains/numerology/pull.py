"""Rebuild ``references.json`` from the published Pythagorean rules, with no network access.

Every expected value is recomputed from the rules below: the letter table (A to I are 1 to 9 and
the alphabet repeats), reduction by digit sum that stops at a single digit or at a master number
(11, 22, 33), and the part-by-part method. The second source is a practitioner who publishes
worked examples; their results were transcribed by hand into ``PRACTITIONER_VALUES`` and a test
asserts the recomputation reproduces them.

Conventions, stated because practitioners split on them:

* Life Path reduces the month, the day and the year each to a single digit or a master number,
  adds the three and reduces again, so a double digit step such as 16 or 29 is visible.
* A name number reduces each name part, adds the part results and reduces again. A name part is
  a run of letters between spaces; a hyphen or an apostrophe carries no value and does not split.
* A, E, I, O and U are the vowels. Y and W are consonants. Some practitioners read Y as a vowel
  by its sound, which needs a pronunciation judgement, so the reference does not.
"""

from __future__ import annotations

from typing import Any

MASTER_NUMBERS = (11, 22, 33)

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
LETTER_VALUE = {letter: index % 9 + 1 for index, letter in enumerate(LETTERS)}
"""The Pythagorean table: A to I are 1 to 9, J to R are 1 to 9, S to Z are 1 to 8."""

VOWELS = "AEIOU"

# (case id, full name, year, month, day, why the case is here)
CASES = (
    ("master-life-path", "Victor Lewis", 1990, 6, 22,
     "day 22 stays whole, the year goes 1990, 19, 10, 1 and the sum is 29, so the Life Path is 11"),
    ("through-19", "Thomas Cruise Mapother", 1990, 8, 12,
     "the year reduces through 19, and the name parts add to 22, 3 and 6"),
    ("parts-not-straight-sum", "Albert Einstein", 1879, 3, 14,
     "reduced by parts the Life Path is 6, a straight digit sum would give a false 33"),
    ("name-with-y", "Yvonne Lynn Taylor", 1998, 10, 15,
     "Y is a consonant, so the Soul Urge sums the vowels only; the date goes through 16"),
    ("hyphen-and-apostrophe", "Mary-Jane O'Neil Smith", 1983, 11, 22,
     "a hyphen and an apostrophe do not split a part; month 11 and day 22 both stay whole"),
    ("master-expression", "Ruth Adams", 1984, 3, 30,
     "the Expression adds to a master 33 across two parts"),
    ("master-soul-urge", "Maria Jones", 1977, 7, 7,
     "the vowels of the two parts add to a master 22"),
)  # fmt: skip

# Practitioner worked examples: (quantity, input, value, where it is printed)
PRACTITIONER_VALUES = (
    ("life_path", {"year": 1990, "month": 8, "day": 12}, 3, "Life Path, August 12, 1990"),
    ("life_path", {"year": 1983, "month": 11, "day": 22}, 9, "Life Path, November 22, 1983"),
    ("life_path", {"year": 1998, "month": 10, "day": 15}, 7, "Life Path, October 15, 1998"),
    ("expression", {"fullName": "Thomas Cruise Mapother"}, 4, "Expression, Tom Cruise"),
    ("soul_urge", {"fullName": "Thomas John Hancock"}, 2, "Soul Urge, Thomas John Hancock"),
)
"""Results as the practitioner prints them, with the page section that carries each."""


def reduce(value: int) -> int:
    """Digit sum repeated until a single digit or a master number is reached."""
    while value > 9 and value not in MASTER_NUMBERS:
        value = sum(int(digit) for digit in str(value))
    return value


def life_path(year: int, month: int, day: int) -> int:
    """Month, day and year each reduced, added, and reduced again."""
    return reduce(reduce(month) + reduce(day) + reduce(year))


def name_number(full_name: str, letters: str = LETTERS) -> int:
    """Each space separated part summed over ``letters`` and reduced, then the parts added."""
    parts = []
    for word in full_name.upper().split():
        parts.append(reduce(sum(LETTER_VALUE[c] for c in word if c in letters)))
    return reduce(sum(parts))


def expression(full_name: str) -> int:
    return name_number(full_name)


def soul_urge(full_name: str) -> int:
    return name_number(full_name, VOWELS)


def practitioner_recomputed(quantity: str, subject: dict[str, Any]) -> int:
    """The recomputation of one transcribed worked example."""
    if quantity == "life_path":
        return life_path(subject["year"], subject["month"], subject["day"])
    return (
        expression(subject["fullName"])
        if quantity == "expression"
        else soul_urge(subject["fullName"])
    )


def pull() -> dict[str, Any]:
    return {
        "format": 1,
        "domain": "numerology",
        "sources": [
            {
                "name": "Pythagorean numerology rules",
                "url": "https://www.worldnumerology.com/numerology-life-path/",
                "command": "python -m benchmark pull numerology",
                "retrieved": "2026-10-09",
                "licence": "Published rules, facts only; no text is copied",
                "method": (
                    "Recomputed from the rules: letters A to I, J to R and S to Z take 1 to 9, "
                    "a number reduces by digit sum and stops at a single digit or at 11, 22 or "
                    "33, the Life Path reduces the month, day and year each and then their sum, "
                    "and a name number reduces each name part and then the sum of the parts. "
                    "A, E, I, O and U are the vowels; Y and W are consonants."
                ),
                "notes": (
                    "Practitioners split on whether Y is a vowel by its sound and on whether a "
                    "name is summed whole or part by part. This reference follows the part by "
                    "part method and reads Y as a consonant."
                ),
            },
            {
                "name": "Hans Decoz worked examples",
                "url": "https://www.worldnumerology.com/numerology-expression/",
                "retrieved": "2026-10-09",
                "licence": "Published worked examples, results only",
                "method": (
                    "Life Path examples from the Life Path page, the Expression example for "
                    "Thomas Cruise Mapother from the Expression page and the Soul Urge example "
                    "for Thomas John Hancock from the Soul Urge page, transcribed by hand. The "
                    "recomputation above is asserted to reproduce every value."
                ),
                "applies_to": ["life_path", "expression", "soul_urge"],
            },
        ],
        "families": [
            {
                "label": "Life Path, Expression and Soul Urge",
                "quantities": ["life_path", "expression", "soul_urge"],
            },
        ],
        "tolerances": [
            {
                "applies_to": "*",
                "value": 0,
                "unit": "exact",
                "why": (
                    "A numerology number is a discrete value from fixed rules: "
                    "any other number is a different reading."
                ),
            },
        ],
        "cases": [
            {
                "id": case_id,
                "input": {"fullName": name, "year": year, "month": month, "day": day},
                "expected": {
                    "life_path": life_path(year, month, day),
                    "expression": expression(name),
                    "soul_urge": soul_urge(name),
                },
            }
            for case_id, name, year, month, day, _ in CASES
        ],
        "cross_checks": [
            {
                "id": f"{quantity}-{index}",
                "source": "Hans Decoz worked examples",
                "input": subject,
                "expected": {quantity: value},
            }
            for index, (quantity, subject, value, _) in enumerate(PRACTITIONER_VALUES)
        ],
    }
