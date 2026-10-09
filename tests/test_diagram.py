from __future__ import annotations

import re
from typing import Any

import pytest

from benchmark.diagram import coverage_map, escape, quantity_families
from benchmark.domains import LoadedDomain, load
from benchmark.paths import DOMAINS_DIR
from benchmark.readme import _coverage
from benchmark.schema import Chart

NODE = re.compile(r'^  (\w+)(?:\("([^"]*)"\)|\["([^"]*)"\])$')
EDGE = re.compile(r"^  (\w+) --> (\w+)$")


def loaded(charts: dict[str, Chart]) -> list[LoadedDomain]:
    return [load(DOMAINS_DIR / name, charts) for name in ("western-planets", "western-angles")]


def entries(domains: list[LoadedDomain]) -> list[dict[str, str]]:
    return [{"id": d.domain.id, "title": d.domain.title} for d in domains]


def assert_parses(source: str) -> tuple[set[str], list[tuple[str, str]]]:
    """Structure the renderer needs: a header, quoted node lines, edges between declared nodes."""
    header, *body = source.splitlines()
    assert header == "flowchart LR"
    nodes: set[str] = set()
    edges: list[tuple[str, str]] = []
    for line in body:
        if node := NODE.match(line):
            assert node.group(1) not in nodes
            nodes.add(node.group(1))
        elif edge := EDGE.match(line):
            edges.append((edge.group(1), edge.group(2)))
        else:
            pytest.fail(f"not a node or an edge: {line!r}")
    assert all(a in nodes and b in nodes for a, b in edges)
    return nodes, edges


def test_every_domain_reaches_its_authorities_and_quantities(charts: dict[str, Chart]) -> None:
    domains = loaded(charts)
    source = coverage_map(entries(domains), {d.domain.id: d.references for d in domains})
    nodes, edges = assert_parses(source)
    for i, d in enumerate(domains):
        assert f'd{i}("{d.domain.title}")' in source
        assert {a for a, b in edges if b == f"d{i}"}, d.domain.id
        assert any(a == f"d{i}" for a, _ in edges)
        for s in d.references.sources:
            assert f'["{escape(s.name)}"]' in source
    assert "Chiron" in source or "Sun, Moon" in source
    assert len(nodes) > len(domains)


def test_a_shared_authority_is_one_node(charts: dict[str, Chart]) -> None:
    domains = loaded(charts)
    source = coverage_map(entries(domains), {d.domain.id: d.references for d in domains})
    assert source.count('["NASA JPL Horizons"]') == 1


def test_map_is_deterministic(charts: dict[str, Chart]) -> None:
    domains = loaded(charts)
    refs = {d.domain.id: d.references for d in domains}
    assert coverage_map(entries(domains), refs) == coverage_map(entries(domains), refs)


def test_labels_are_escaped() -> None:
    label = 'a "quoted" <b>x</b> (p) / q & #1 `c` \\'
    out = escape(label)
    assert not set('"<>`\\') & set(out)
    assert out.startswith("a #quot;quoted#quot;")
    assert "(p) / q" in out


def test_quantity_families_collapse_by_stem_suffix_and_length() -> None:
    names = ["Ascendant", "Midheaven", "Cusp 2", "Cusp 3", "Sun", "Sun pada", "Moon", "Moon pada"]
    assert quantity_families(names) == [
        "Ascendant, Midheaven, Sun, Moon",
        "2 Cusp values",
        "2 pada values",
    ]
    assert quantity_families(["a", "b", "c", "d", "e"]) == ["a, b, c and 2 more"]
    assert quantity_families(["a", "b", "c", "d"]) == ["a, b, c, d"]


def test_readme_coverage_block_is_a_fenced_map_for_every_domain(charts: dict[str, Chart]) -> None:
    domains = loaded(charts)
    doc: dict[str, Any] = {
        "run": {"date": "2026-01-01", "target": "https://roxyapi.com/api/v2"},
        "domains": [
            {**e, "summaries": [], "endpoints": [], "authority": "", "order": 0}
            for e in entries(domains)
        ],
    }

    block = _coverage(doc, {d.domain.id: d.references for d in domains})
    assert block.count("```mermaid\nflowchart LR") == 1 and block.endswith("\n```")
    assert all(d.domain.title in block for d in domains)


def test_declared_families_label_the_map(charts: dict[str, Chart]) -> None:
    domains = loaded(charts)
    for d in domains:
        assert d.references.families, d.domain.id
    source = coverage_map(entries(domains), {d.domain.id: d.references for d in domains})
    assert "Ascendant, Midheaven and Placidus cusps" in source
    assert "and 8 more" not in source
