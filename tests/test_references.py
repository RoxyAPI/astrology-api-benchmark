"""Every real domain loads, carries well formed and sourced references, and type checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from mypy import api as mypy_api

from benchmark.domains import PULL_FILE, discover
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import Chart, SchemaError, parse_references

DOMAIN_FOLDERS = sorted(p for p in DOMAINS_DIR.glob("*/") if any(p.glob("*.py")))


def test_every_domain_loads_with_valid_references(charts: dict[str, Chart]) -> None:
    """Discovery parses each references.json strictly: sources, tolerances, value types."""
    orders = [d.domain.order for d in discover(charts, DOMAINS_DIR)]
    assert len(set(orders)) == len(orders), "two domains share an order"


@pytest.mark.parametrize("folder", DOMAIN_FOLDERS, ids=lambda p: p.name)
def test_domain_ships_a_pull_script(folder: Path) -> None:
    assert (folder / PULL_FILE).is_file()


@pytest.mark.parametrize("folder", DOMAIN_FOLDERS, ids=lambda p: p.name)
def test_domain_type_checks_strictly(folder: Path) -> None:
    """Domain modules share file names, so each folder is checked on its own."""
    out, err, status = mypy_api.run([str(folder)])
    assert status == 0, out + err


def _families_doc(families: list[dict[str, Any]]) -> dict[str, Any]:
    doc = json.loads((DOMAINS_DIR / "numerology" / "references.json").read_text(encoding="utf-8"))
    return {**doc, "families": families}


@pytest.mark.parametrize(
    "families",
    [
        [{"label": "Life Path", "quantities": ["life_path", "nope"]}],
        [{"label": "A", "quantities": ["life_path", "expression", "soul_urge"]}] * 2,
        [{"label": "Life Path", "quantities": ["life_path"]}],
        [{"label": "It's all", "quantities": ["life_path", "expression", "soul_urge"]}],
        [{"label": "Life Path, 3 - 4", "quantities": ["life_path", "expression", "soul_urge"]}],
    ],
)
def test_bad_families_are_refused(families: list[dict[str, Any]], charts: dict[str, Chart]) -> None:
    with pytest.raises(SchemaError):
        parse_references(_families_doc(families), "numerology", charts)
