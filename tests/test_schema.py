from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from benchmark import Domain, Unit
from benchmark.schema import ALL, Chart, Endpoint, SchemaError, load_charts, parse_references

type Mutation = Callable[[dict[str, Any]], None]


def test_valid_document_parses(references_doc: dict[str, Any], charts: dict[str, Chart]) -> None:
    refs = parse_references(references_doc, "example", charts)
    assert refs.domain == "example"
    assert refs.sources[0].applies_to == ALL
    assert refs.tolerance_for("angle").unit is Unit.ARCSEC
    assert refs.tolerance_for("anything else").unit is Unit.EXACT
    assert refs.cases[0].input == {"date": "2000-01-01"}
    assert refs.cases[0].chart is None


def test_chart_case_resolves_the_corpus_row(
    references_doc: dict[str, Any], charts: dict[str, Chart]
) -> None:
    references_doc["cases"] = [{"id": "o", "chart": "obama", "expected": {"angle": 1.0}}]
    case = parse_references(references_doc, "example", charts).cases[0]
    assert case.chart is not None
    assert case.chart.request() == {
        "date": "1961-08-04",
        "time": "19:24:00",
        "latitude": 21.3,
        "longitude": -157.8667,
        "timezone": -10.0,
    }


def test_cross_checks_parse(references_doc: dict[str, Any], charts: dict[str, Chart]) -> None:
    references_doc["cross_checks"] = [
        {"source": "Definition", "id": "x", "input": {"d": 1}, "expected": {"label": "a"}}
    ]
    (cross,) = parse_references(references_doc, "example", charts).cross_checks
    assert (cross.source, cross.id, cross.expected) == ("Definition", "x", {"label": "a"})


DELETE = object()


def _set(path: str, value: Any) -> Mutation:
    """Set a dotted path such as ``cases.0.expected.angle``; ``value`` DELETE removes it."""

    def apply(doc: dict[str, Any]) -> None:
        *parents, last = path.split(".")
        node: Any = doc
        for key in parents:
            node = node[int(key)] if isinstance(node, list) else node[key]
        if isinstance(node, list):
            node[int(last)] = value
        elif value is DELETE:
            del node[last]
        else:
            node[last] = value

    return apply


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (_set("format", 2), "format must be 1"),
        (_set("domain", "other"), "domain must be"),
        (_set("extra", 1), "unknown extra"),
        (_set("sources", []), "non-empty list"),
        (_set("sources.0.licence", DELETE), "missing licence"),
        (_set("sources.0.url", DELETE), "url, a command or a citation"),
        (_set("sources.0.url", "http://example.org"), "https URL"),
        (_set("sources.0.retrieved", "2026-1-1"), "YYYY-MM-DD"),
        (_set("sources.0.retrieved", "2999-01-01"), "in the future"),
        (_set("sources.0.applies_to", ["other"]), "no source covers"),
        (_set("sources.0.surprise", "x"), "unknown surprise"),
        (_set("tolerances.0.unit", "degrees"), "unit: expected one of"),
        (_set("tolerances.0.value", -1), "non-negative"),
        (_set("tolerances.0.why", " "), "non-empty string"),
        (_set("tolerances.1.value", 1), "exact tolerance is 0"),
        (_set("tolerances.1.applies_to", ["angle"]), "angle named twice"),
        (_set("cases", []), "non-empty list"),
        (_set("cases.0.chart", "obama"), "not both or neither"),
        (_set("cases.0.input", DELETE), "not both or neither"),
        (_set("cases.0.input", {}), "non-empty object"),
        (_set("cases.0.expected", {}), "non-empty object"),
        (_set("cases.0.expected.angle", "1.5"), "number of degrees"),
        (_set("cases.0.expected.angle", True), "number of degrees"),
        (_set("cases.0.expected.label", 1.5), "exact value"),
    ],
)
def test_invalid_documents_are_rejected(
    references_doc: dict[str, Any], charts: dict[str, Chart], mutation: Mutation, message: str
) -> None:
    mutation(references_doc)
    with pytest.raises(SchemaError, match=message):
        parse_references(references_doc, "example", charts)


def test_unknown_chart_and_duplicate_ids_are_rejected(
    references_doc: dict[str, Any], charts: dict[str, Chart]
) -> None:
    references_doc["cases"] = [{"id": "x", "chart": "nobody", "expected": {"angle": 1.0}}]
    with pytest.raises(SchemaError, match=r"not in data/charts\.csv"):
        parse_references(references_doc, "example", charts)
    references_doc["cases"] = [{"id": "x", "input": {"a": 1}, "expected": {"angle": 1.0}}] * 2
    with pytest.raises(SchemaError, match="ids must be unique"):
        parse_references(references_doc, "example", charts)


def test_every_quantity_needs_a_tolerance(
    references_doc: dict[str, Any], charts: dict[str, Chart]
) -> None:
    references_doc["tolerances"].pop()
    references_doc["cases"][0]["expected"]["label"] = "a"
    with pytest.raises(SchemaError, match="no tolerance applies"):
        parse_references(references_doc, "example", charts)


def test_cross_check_must_name_a_source(
    references_doc: dict[str, Any], charts: dict[str, Chart]
) -> None:
    references_doc["cross_checks"] = [
        {"source": "Elsewhere", "id": "x", "input": {"d": 1}, "expected": {"label": "a"}}
    ]
    with pytest.raises(SchemaError, match="not a name in sources"):
        parse_references(references_doc, "example", charts)


@pytest.mark.parametrize(
    ("unit", "value"),
    [
        ("seconds", "2000-01-01T12:00:00"),
        ("seconds", 12),
        ("days", "21 December"),
        ("days", None),
    ],
)
def test_value_types_follow_the_unit(
    references_doc: dict[str, Any], charts: dict[str, Chart], unit: str, value: Any
) -> None:
    references_doc["tolerances"][0]["unit"] = unit
    references_doc["cases"][0]["expected"]["angle"] = value
    with pytest.raises(SchemaError):
        parse_references(references_doc, "example", charts)


@pytest.mark.parametrize(
    ("method", "path", "tag"),
    [("post", "/a", "T"), ("POST", "a", "T"), ("POST", "/a", " ")],
)
def test_endpoint_declaration_is_validated(method: str, path: str, tag: str) -> None:
    with pytest.raises(SchemaError):
        Endpoint(method, path, tag)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "Bad Id"},
        {"title": " "},
        {"authority": ""},
        {"endpoints": ()},
        {"endpoints": ("/astrology/natal-chart",)},
    ],
)
def test_domain_declaration_is_validated(kwargs: dict[str, Any]) -> None:
    fields: dict[str, Any] = {
        "id": "western-planets",
        "title": "Western planets",
        "authority": "NASA JPL Horizons",
        "endpoints": (Endpoint("POST", "/astrology/natal-chart", "Western Astrology"),),
        "order": 1,
    }
    with pytest.raises(SchemaError):
        Domain(**(fields | kwargs))


def test_charts_corpus_loads(charts: dict[str, Chart]) -> None:
    assert charts
    assert all(isinstance(c.timezone, float | str) for c in charts.values())


def test_charts_header_is_enforced(tmp_path: Path) -> None:
    path = tmp_path / "charts.csv"
    path.write_text("chart_id,name\nx,y\n", encoding="utf-8")
    with pytest.raises(SchemaError, match="header"):
        load_charts(path)
