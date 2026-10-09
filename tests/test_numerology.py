"""The numerology recomputation reproduces the published worked examples, value for value."""

from __future__ import annotations

from types import ModuleType
from typing import Any

import pytest

from benchmark.domains import PULL_FILE, load_module
from benchmark.paths import DOMAINS_DIR

FOLDER = DOMAINS_DIR / "numerology"


@pytest.fixture(scope="module")
def pull() -> ModuleType:
    return load_module(FOLDER, PULL_FILE)


@pytest.fixture(scope="module")
def document(pull: ModuleType) -> dict[str, Any]:
    return pull.pull()  # type: ignore[no-any-return]


def test_recomputation_reproduces_every_practitioner_example(
    pull: ModuleType, document: dict[str, Any]
) -> None:
    assert len(document["cross_checks"]) >= 5
    for cross in document["cross_checks"]:
        ((quantity, value),) = cross["expected"].items()
        assert pull.practitioner_recomputed(quantity, cross["input"]) == value, cross["id"]


def test_reduction_keeps_master_numbers_and_the_letter_table_wraps(pull: ModuleType) -> None:
    assert [pull.reduce(n) for n in (29, 38, 19, 33, 44)] == [11, 11, 1, 33, 8]
    assert [pull.LETTER_VALUE[c] for c in "AIJRSZ"] == [1, 9, 1, 9, 1, 8]


def test_cases_cover_a_master_life_path_a_y_name_and_a_hyphenated_name(
    document: dict[str, Any],
) -> None:
    cases = {c["id"]: c for c in document["cases"]}
    assert cases["master-life-path"]["expected"]["life_path"] == 11
    assert "Y" in cases["name-with-y"]["input"]["fullName"].upper()
    assert "-" in cases["hyphen-and-apostrophe"]["input"]["fullName"]
    assert cases["parts-not-straight-sum"]["expected"]["life_path"] == 6
