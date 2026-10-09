"""Rewrite the generated blocks of ``README.md`` from the committed results and the references.

Each block sits between two marker comments. Everything outside them is hand-written; everything
inside is rebuilt on every run, so no count, median or credit in the README can drift from
``results/latest.json`` and the ``references.json`` files. ``--check`` rebuilds in memory and
reports drift instead of writing.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmark.claims import (
    TIER_NOUNS,
    DomainDoc,
    QuantityStat,
    amount,
    deviations,
    fmt,
    headline,
    labels,
    quantity_stats,
    subject,
    target_host,
)
from benchmark.diagram import coverage_map, family_labels
from benchmark.domains import references_for
from benchmark.paths import DOMAINS_DIR, README_PATH, RESULTS_DIR
from benchmark.results import JSON_FILE, read_results
from benchmark.schema import (
    ALL,
    Case,
    Chart,
    Endpoint,
    References,
    Unit,
    is_number,
    load_charts,
)
from benchmark.spec import label, reference_url
from benchmark.stats import median

BLOCKS = ("claim", "scorecard", "coverage", "domains", "credits")
"""The generated blocks, in the order they appear in the README."""

SAMPLE_ROWS = 5
"""Measurements shown per domain: the worst per unit first, then one per further case."""

UNIT_NOUNS: Mapping[Unit, str] = {
    **TIER_NOUNS,
    Unit.DAYS: "calendar counts",
    Unit.EXACT: "discrete values",
}


class ReadmeError(Exception):
    """The README cannot take the generated blocks."""


def begin_marker(name: str) -> str:
    return f"<!-- generated:{name}:begin python -m benchmark readme, do not edit -->"


def end_marker(name: str) -> str:
    return f"<!-- generated:{name}:end -->"


def render_blocks(results: Mapping[str, Any], refs: Mapping[str, References]) -> dict[str, str]:
    """Every block body, keyed by block name, from a results document and its references."""
    domains: list[dict[str, Any]] = list(results["domains"])
    return {
        "claim": _claim(results, refs),
        "scorecard": _scorecard(domains),
        "coverage": _coverage(results, refs),
        "domains": "\n\n".join(_domain(d, refs[d["id"]], subject(results)) for d in domains),
        "credits": _credits(domains, refs),
    }


def replace_blocks(text: str, blocks: Mapping[str, str]) -> str:
    """Put each block body between its markers. Refuses a missing, repeated or reversed pair."""
    for name in BLOCKS:
        begin, end = begin_marker(name), end_marker(name)
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ReadmeError(f"README.md must hold the {name} markers exactly once each")
        start, stop = text.index(begin) + len(begin), text.index(end)
        if stop < start:
            raise ReadmeError(f"README.md: the {name} end marker comes before its begin marker")
        text = f"{text[:start]}\n{blocks[name]}\n{text[stop:]}"
    return text


def update(
    readme: Path = README_PATH,
    results_path: Path = RESULTS_DIR / JSON_FILE,
    domains_dir: Path = DOMAINS_DIR,
    *,
    check: bool = False,
) -> bool:
    """Rebuild the blocks. True when the file changed, or with ``check``, when it would change.

    Refuses a results format this version does not read.
    """
    results = read_results(results_path)
    refs = references_for((d["id"] for d in results["domains"]), load_charts(), domains_dir)
    current = readme.read_text(encoding="utf-8")
    rendered = replace_blocks(current, render_blocks(results, refs))
    if rendered == current:
        return False
    if not check:
        readme.write_text(rendered, encoding="utf-8")
    return True


def _claim(results: Mapping[str, Any], refs: Mapping[str, References]) -> str:
    domains, run = results["domains"], results["run"]
    first, *rest = headline(results, labels(refs))
    by_unit = "; ".join(_unit_figure(unit, domains) for unit in Unit if _has_unit(domains, unit))
    return (
        f"> **{first}**{''.join(f' {r}' for r in rest)}\n>\n"
        f"> By unit: {by_unit}. Target `{target_host(run['target'])}`, "
        f"generated from [`results/{JSON_FILE}`](results/{JSON_FILE})."
    )


def _coverage(results: Mapping[str, Any], refs: Mapping[str, References]) -> str:
    return (
        f"The {subject(results)} coverage map: each reference authority, the domain it checks and "
        "the quantities compared, generated from the references of every domain in the run.\n\n"
        f"```mermaid\n{coverage_map(results['domains'], refs)}\n```"
    )


def _unit_figure(unit: Unit, domains: Sequence[DomainDoc]) -> str:
    devs = deviations(domains, unit)
    noun = UNIT_NOUNS[unit]
    if unit is Unit.EXACT:
        return f"{noun} {sum(d == 0 for d in devs):,} of {len(devs):,} exact"
    return (
        f"{noun} median {amount(median(devs) if devs else None, unit, deg=True)} over {len(devs):,}"
    )


def _has_unit(domains: Sequence[DomainDoc], unit: Unit) -> bool:
    return any(s["unit"] == unit for d in domains for s in d["summaries"])


def _scorecard(domains: Sequence[DomainDoc]) -> str:
    rows = [
        "| Domain | Authority | Values | Within band | Median | p95 | Max | Unit |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for d in domains:
        for i, s in enumerate(d["summaries"]):
            rows.append(
                _row(
                    f"[{d['title']}](#{_anchor(d['title'])})" if i == 0 else "",
                    d["authority"] if i == 0 else "",
                    f"{s['points']:,}",
                    _within(s),
                    fmt(s["median"]),
                    fmt(s["p95"]),
                    fmt(s["max"]),
                    s["unit"],
                )
            )
    return "\n".join(rows)


def _within(summary: Mapping[str, Any]) -> str:
    text = f"{summary['passed']:,} of {summary['points']:,}"
    misses = [f"{summary[key]:,} {key}" for key in ("failed", "missing") if summary[key]]
    return f"{text}, {', '.join(misses)}" if misses else text


def _domain(d: Mapping[str, Any], refs: References, who: str) -> str:
    endpoints = ", ".join(
        f"[`{label(e)}`]({reference_url(e)})" for e in (Endpoint(**e) for e in d["endpoints"])
    )
    parts = [
        f"### {d['title']}",
        f"**Authority:** {d['authority']}. **Covers:** {'; '.join(family_labels(refs))}. "
        f"**Endpoints:** {endpoints}.",
        "**Quantities and pass bands**",
        _tolerances(refs),
        "**How the reference is obtained**",
        _sources(refs),
        "**Sample checks from the run**",
        _samples(d, refs),
    ]
    stats = quantity_stats(d, refs)
    if stats:
        parts += ["**Per quantity**", _per_quantity(stats)]
    return "\n\n".join(parts)


def _tolerances(refs: References) -> str:
    quantities = list(dict.fromkeys(q for c in refs.cases for q in c.expected))
    rows = ["| Quantities | Pass band | Why |", "|---|---|---|"]
    for t in sorted(refs.tolerances, key=lambda t: t.applies_to == ALL):
        covered = [q for q in quantities if refs.tolerance_for(q) is t]
        if not covered:
            continue
        band = "exact match" if t.unit is Unit.EXACT else amount(t.value, t.unit)
        rows.append(_row(", ".join(covered), band, t.why))
    return "\n".join(rows)


def _sources(refs: References) -> str:
    lines = []
    for s in refs.sources:
        name = f"[{s.name}]({s.url})" if s.url else s.name
        text = f"- {name}: {s.method}"
        if s.notes:
            text += f" {s.notes}"
        if s.citation:
            text += f" Cited: {s.citation}."
        if s.command:
            command, _, detail = s.command.partition(" (")
            text += f" Regenerated by `{command}`" + (f" ({detail}." if detail else ".")
        crossed = sum(c.source == s.name for c in refs.cross_checks)
        if crossed:
            text += (
                f" {crossed} {'subject' if crossed == 1 else 'subjects'} transcribed from this "
                "source are reproduced by the recomputation in the test suite."
            )
        lines.append(text)
    return "\n".join(lines)


def _samples(d: Mapping[str, Any], refs: References) -> str:
    measurements: list[Mapping[str, Any]] = d["measurements"]
    wanted: list[tuple[str, str]] = [
        (s["worst_case"]["case"], s["worst_case"]["quantity"])
        for s in d["summaries"]
        if s["worst_case"] is not None
    ]
    seen_cases = {case for case, _ in wanted}
    for m in measurements:
        if len(wanted) >= SAMPLE_ROWS:
            break
        if m["case"] not in seen_cases:
            seen_cases.add(m["case"])
            wanted.append((m["case"], m["quantity"]))
    by_key = {(m["case"], m["quantity"]): m for m in measurements}
    cases = {c.id: c for c in refs.cases}
    rows = [
        "| Case | Subject | Quantity | Reference | API | Deviation | Result |",
        "|---|---|---|---|---|---:|---|",
    ]
    for key in dict.fromkeys(wanted):
        m = by_key[key]
        unit = Unit(m["unit"])
        rows.append(
            _row(
                f"`{m['case']}`",
                _subject(cases.get(m["case"])),
                m["quantity"],
                _value(m["expected"], unit),
                _value(m["actual"], unit),
                amount(m["deviation"], unit) if m["deviation"] is not None else "n/a",
                m["status"],
            )
        )
    return "\n".join(rows)


def _per_quantity(stats: Sequence[QuantityStat]) -> str:
    rows = [
        _row(
            q.quantity,
            q.reference,
            amount(q.median, q.unit),
            amount(q.max, q.unit, up=True),
            f"`{q.worst_case}`" if q.worst_case else "",
        )
        for q in sorted(stats, key=lambda q: -(q.max or 0))
    ]
    return "\n".join(
        ["| Quantity | Reference | Median | Max | Worst case |", "|---|---|---:|---:|---|", *rows]
    )


def _credits(domains: Sequence[Mapping[str, Any]], refs: Mapping[str, References]) -> str:
    merged: dict[tuple[str, str | None], dict[str, Any]] = {}
    for d in domains:
        for s in refs[d["id"]].sources:
            entry = merged.setdefault(
                (s.name, s.url),
                {"source": s, "retrieved": s.retrieved, "domains": []},
            )
            entry["retrieved"] = max(entry["retrieved"], s.retrieved)
            entry["domains"].append(d["title"])
    rows = ["| Source | Licence | Retrieved | Used for |", "|---|---|---|---|"]
    for entry in merged.values():
        s = entry["source"]
        name = f"[{s.name}]({s.url})" if s.url else s.name
        if s.citation:
            name += f". {s.citation}"
        rows.append(_row(name, s.licence, entry["retrieved"], ", ".join(entry["domains"])))
    return "\n".join(rows)


def _subject(case: Case | None) -> str:
    if case is None:
        return ""
    if case.chart is not None:
        return _chart(case.chart)
    scalars = {k: v for k, v in (case.input or {}).items() if isinstance(v, str | int | float)}
    return f"`{json.dumps(scalars, ensure_ascii=False)}`"


def _chart(chart: Chart) -> str:
    return f"{chart.name}, {chart.date} {chart.time[:5]}"


def _value(value: object, unit: Unit) -> str:
    if value is None:
        return "n/a"
    if unit is Unit.ARCSEC and is_number(value):
        return f"{value:.7f}"
    return f"`{value}`"


def _row(*cells: str) -> str:
    return "| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |"


def _anchor(title: str) -> str:
    """The id GitHub gives a heading: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
