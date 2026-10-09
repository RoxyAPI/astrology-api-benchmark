"""The citable sentences, generated from a results document and shared by the README and the page.

One module writes every claim so the README, the report page and the PDF can never say different
things. Each function reads the results JSON shape and treats ``tiers`` as optional, because
results written before tiers existed carry none.
"""

from __future__ import annotations

import math
import urllib.parse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from benchmark.api import DEFAULT_TARGET
from benchmark.schema import References, Status, Unit
from benchmark.stats import median

type ResultsDoc = Mapping[str, Any]
"""A results document: ``run`` and ``domains``."""

type DomainDoc = Mapping[str, Any]
"""One entry of ``domains`` in a results document."""

CONTINUOUS = (Unit.ARCSEC, Unit.SECONDS)
"""Units whose deviation is a measured distance, so tiers and per quantity lines apply."""

TIER_NOUNS: Mapping[Unit, str] = {Unit.ARCSEC: "positions", Unit.SECONDS: "instants"}


def fmt(value: float | None) -> str:
    """Two significant digits below 10, else one decimal: the same rule as the report page."""
    if value is None:
        return "n/a"
    if value == 0:
        return "0"
    if abs(value) < 10:
        return f"{float(f'{value:.2g}'):g}"
    return f"{value:,.1f}".removesuffix(".0")


def fmt_up(value: float) -> str:
    """``fmt`` rounded up, never down, so "within X" stays true of the value it bounds."""
    if value <= 0:
        return "0"
    places = 1 if value >= 10 else 1 - math.floor(math.log10(value))
    scale = 10.0**places
    return fmt(math.ceil(round(value * scale, 9)) / scale)


def degrees(arcsec: float) -> str:
    """Arcseconds as decimal degrees to two significant figures, e.g. ``0.000013``."""
    deg = arcsec / 3600
    if deg <= 0:
        return "0"
    return f"{deg:.{max(0, 1 - math.floor(math.log10(deg)))}f}"


def amount(value: float | None, unit: str, *, up: bool = False, deg: bool = False) -> str:
    """A figure with its unit, singular when the shown figure is 1 ("1 second", "10 seconds").

    ``deg`` adds the same arcsec figure in decimal degrees in brackets, for prose claims.
    """
    shown = fmt_up(value) if up and value is not None else fmt(value)
    text = f"{shown} {unit.removesuffix('s') if shown == '1' else unit}"
    if deg and unit == Unit.ARCSEC and value is not None and shown != "n/a":
        text += f" ({degrees(float(shown.replace(',', '')))}°)"
    return text


type Labels = Mapping[tuple[str, Unit], str]
"""Reader label per domain id and unit, from the families of each domain."""


def labels(refs: Mapping[str, References]) -> dict[tuple[str, Unit], str]:
    """The family labels covering the quantities of one unit in each domain, joined as prose."""
    out: dict[tuple[str, Unit], str] = {}
    for domain_id, ref in refs.items():
        by_unit: dict[Unit, list[str]] = {}
        for family in ref.families:
            unit = Unit(ref.tolerance_for(family.quantities[0]).unit)
            by_unit.setdefault(unit, []).append(family.label)
        for unit, names in by_unit.items():
            out[(domain_id, unit)] = _join(names)
    return out


def target_host(target: str) -> str:
    """The host of a target base URL, the only form of it shown to readers."""
    return urllib.parse.urlsplit(target).netloc


def subject(results: ResultsDoc) -> str:
    """Who returned the values: RoxyAPI for its own API, else the host of the target."""
    target = str(results["run"]["target"])
    return "RoxyAPI" if target == DEFAULT_TARGET else target_host(target)


def headline(results: ResultsDoc, names: Labels | None = None) -> list[str]:
    """The claim as sentences: the strongest precision tier of any domain, then the totals.

    Each names who returned the values and against what, so it stands alone when lifted.
    """
    tiers = tier_sentences(results, names)
    totals = totals_sentence(results)
    return [tiers[0], totals] if tiers else [totals]


def totals_sentence(results: ResultsDoc) -> str:
    domains = results["domains"]
    summaries = [s for d in domains for s in d["summaries"]]
    points = sum(s["points"] for s in summaries)
    passed = sum(s["passed"] for s in summaries)
    angles = deviations(domains, Unit.ARCSEC)
    count = len(domains)
    return (
        f"In the open accuracy benchmark run of {results['run']['date']}, {subject(results)} "
        f"returned {passed:,} of {points:,} values within tolerance across {count} "
        f"{'domain' if count == 1 else 'domains'}"
        + (
            f", with a median angular deviation of {amount(median(angles), Unit.ARCSEC, deg=True)}."
            if angles
            else "."
        )
    )


def tier_sentences(results: ResultsDoc, names: Labels | None = None) -> list[str]:
    """One sentence per domain and unit with its strongest true tier, best first.

    A domain with every point measured is bounded by its worst deviation, rounded up; otherwise
    it falls back to its tightest full tier, else its loosest tier with the count. Points are
    never pooled across domains, whose references differ. Angles
    lead instants; within a unit a full tier beats a partial one and a tighter limit a looser
    one. Empty when no summary carries tiers.
    """
    ranked = []
    for d in results["domains"]:
        for s in d["summaries"]:
            unit = Unit(s["unit"])
            tiers = s.get("tiers") or ()
            if unit not in CONTINUOUS or not tiers:
                continue
            bound = all_within(s)
            full = [t["limit"] for t in tiers if t["points"] == s["points"]]
            if bound is not None:
                limit, reached, shown = bound, s["points"], amount(bound, unit, up=True, deg=True)
            else:
                limit = min(full) if full else max(t["limit"] for t in tiers)
                reached = next(t["points"] for t in tiers if t["limit"] == limit)
                shown = amount(limit, unit, deg=True)
            label = (names or {}).get((d["id"], unit))
            what = f"the {label}" if label else d["title"]
            sentence = (
                f"For {what}, {subject(results)} returned {reached:,} of {s['points']:,} "
                f"{TIER_NOUNS[unit]} within {shown} of {d['authority']}."
            )
            ranked.append(((bound is None and not full, CONTINUOUS.index(unit), limit), sentence))
    return [sentence for _, sentence in sorted(ranked, key=lambda r: r[0])]


def _join(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def tier_figures(summary: Mapping[str, Any]) -> str:
    """``231 within 10 arcsec, 231 within 1 arcsec, ...`` or empty when the summary has none."""
    unit = summary["unit"]
    return ", ".join(
        f"{t['points']:,} within {amount(t['limit'], unit)}" for t in summary.get("tiers") or ()
    )


@dataclass(frozen=True, slots=True)
class QuantityStat:
    """One angle or instant quantity of a domain across every case of the run."""

    quantity: str
    unit: str
    reference: str
    noun: str
    """``charts`` when every case is a chart of the corpus, else ``cases``."""
    values: int
    passed: int
    median: float | None
    max: float | None
    worst_case: str | None


def quantity_stats(domain: DomainDoc, refs: References) -> list[QuantityStat]:
    """Per quantity figures for the angle and instant quantities, in measurement order."""
    by_quantity: dict[str, list[Mapping[str, Any]]] = {}
    for m in domain["measurements"]:
        if m["unit"] in CONTINUOUS:
            by_quantity.setdefault(m["quantity"], []).append(m)
    charted = {c.id for c in refs.cases if c.chart is not None}
    stats = []
    for quantity, rows in by_quantity.items():
        measured = [m for m in rows if m["deviation"] is not None]
        worst = max(measured, key=lambda m: float(m["deviation"]), default=None)
        stats.append(
            QuantityStat(
                quantity=quantity,
                unit=rows[0]["unit"],
                reference=quantity_reference(domain, refs, quantity),
                noun="charts" if all(m["case"] in charted for m in rows) else "cases",
                values=len(rows),
                passed=sum(m["status"] == Status.PASS for m in rows),
                median=median([float(m["deviation"]) for m in measured]) if measured else None,
                max=float(worst["deviation"]) if worst else None,
                worst_case=worst["case"] if worst else None,
            )
        )
    return stats


def quantity_lines(results: ResultsDoc, domain: DomainDoc, refs: References) -> list[str]:
    """One liftable sentence per angle or instant quantity."""
    who = subject(results)
    return [quantity_line(q, who) for q in quantity_stats(domain, refs)]


def quantity_line(q: QuantityStat, who: str) -> str:
    spread = f" (median {fmt(q.median)})" if q.median is not None else ""
    if q.max is not None and q.passed == q.values:
        return (
            f"{who} {q.quantity}: every one of {q.values:,} {q.noun} within "
            f"{amount(q.max, q.unit, up=True, deg=True)} of {q.reference}{spread}."
        )
    worst = (
        f", largest deviation {amount(q.max, q.unit, up=True, deg=True)}"
        if q.max is not None
        else ""
    )
    return (
        f"{who} {q.quantity}: {q.passed:,} of {q.values:,} {q.noun} within the pass band of "
        f"{q.reference}{worst}{spread}."
    )


def quantity_reference(domain: DomainDoc, refs: References, quantity: str) -> str:
    """A source dedicated to this one quantity names its reference, else the domain authority."""
    for s in refs.sources:
        if s.applies_to == (quantity,):
            return s.name
    return str(domain["authority"])


def deviations(domains: Sequence[DomainDoc], unit: Unit) -> list[float]:
    return [
        float(m["deviation"])
        for d in domains
        for m in d["measurements"]
        if m["unit"] == unit and m["deviation"] is not None
    ]


def all_within(summary: Mapping[str, Any]) -> float | None:
    """The bound every point sits within: the worst deviation when all points were measured.

    Rounded up where it is shown, so "within X" is true by construction and as tight as the run
    allows; the fixed tiers stay the fallback for a summary with a missing value.
    """
    if summary.get("missing") or summary.get("max") is None:
        return None
    return float(summary["max"])
