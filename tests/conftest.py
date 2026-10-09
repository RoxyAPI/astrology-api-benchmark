"""Shared test helpers. No test reaches the network: the API is a fake or a loopback server."""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from benchmark import ApiClient
from benchmark.schema import Chart, load_charts

FIXTURE_DOMAINS = Path(__file__).parent / "fixtures" / "domains"

VALID_REFERENCES: dict[str, Any] = {
    "format": 1,
    "domain": "example",
    "sources": [
        {
            "name": "Definition",
            "url": "https://example.org/definition",
            "retrieved": "2026-01-01",
            "licence": "Public domain",
            "method": "Recomputed from the definition",
        }
    ],
    "tolerances": [
        {"applies_to": ["angle"], "value": 36, "unit": "arcsec", "why": "Angle band"},
        {"applies_to": "*", "value": 0, "unit": "exact", "why": "Discrete values"},
    ],
    "cases": [{"id": "one", "input": {"date": "2000-01-01"}, "expected": {"angle": 1.5}}],
}


type Respond = Callable[[str, str, Mapping[str, Any] | None], Any]
"""``respond(method, path, body)``: the JSON a fake API returns."""


class FakeApi(ApiClient):
    """Answers every request through ``respond`` and records the calls."""

    def __init__(self, respond: Respond) -> None:
        super().__init__("https://api.invalid", "test-key")
        self.respond = respond
        self.calls: list[tuple[str, str, Mapping[str, Any] | None]] = []

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        self.calls.append((method, path, body))
        return self.respond(method, path, body)


@pytest.fixture(scope="session")
def charts() -> dict[str, Chart]:
    return load_charts()


@pytest.fixture
def references_doc() -> dict[str, Any]:
    """A fresh, valid references document each test may mutate."""
    return copy.deepcopy(VALID_REFERENCES)
