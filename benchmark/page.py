"""The report page body as HTML text, rendered at build time from the page model of ``site.py``.

Every sentence, figure, table and domain card is real text in the delivered file, so the page
reads in full without JavaScript and a crawler that runs none sees all of it. The page script only
draws the charts and the coverage diagram and fills the measurement tables on demand. Every value
is escaped here; the wording comes from ``claims`` and the references, never retyped.
"""

from __future__ import annotations

import html
from collections.abc import Mapping, Sequence
from typing import Any

from benchmark.claims import CASES, combined, fmt, fmt_up, measured_deviation
from benchmark.schema import ALL, Unit

type Model = Mapping[str, Any]
"""The page model: a results document whose domains carry sources, tolerances and lines."""

UNIT_EXPLAIN: Mapping[Unit, str] = {
    Unit.ARCSEC: "Angles are decimal degrees; the deviation is the shortest angular distance "
    "in arcseconds.",
    Unit.SECONDS: "Instants carry a UTC offset; the deviation is the difference in seconds.",
    Unit.DAYS: "Calendar counts are whole days from a fixed epoch; the deviation is in days.",
    Unit.EXACT: "Discrete values such as a day sign or a calendar label: the deviation is 0 on a "
    "match and 1 otherwise, and the pass band is 0.",
}

METHOD = (
    "Each domain holds reference values from a named source, pulled from that source or "
    "recomputed from its published definition by a script in the open repository. The runner "
    "sends every case to the API under test, reads the returned value and compares it with the "
    "reference.",
    "A value passes when its deviation is within the pass band set for that quantity. Every pass "
    "band is vendor neutral: it states why it has its size, and none is sized to any one API. A "
    "value the API did not return is counted as missing, and a missing value fails the run.",
    "Read the largest deviation per quantity, not only the pass count. A pass band is a floor, so "
    "a drift that stays inside the band still passes; it shows first in the per quantity maxima.",
)
"""The method as plain sentences, shown on the page and stated as the measurement technique."""

RERUN = (
    "Anyone can rerun the benchmark: clone the repository, set an API key and run "
    '<code class="whitespace-nowrap">python -m benchmark run</code>. Point '
    '<code class="whitespace-nowrap">--target</code> at another API and adapt a domain check to '
    "compare it against the same references."
)

ICON_PASS = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" '
    'aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><path d="M5 8.2l2 2 4-4.2" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
ICON_FAIL = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" '
    'aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 '
    '4.4" stroke-linecap="round"/></svg>'
)
ICON_DOWN = (
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.8" '
    'aria-hidden="true"><path d="M8 2.5v8M4.5 7.5L8 11l3.5-3.5M3 13.5h10" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)

DOWNLOADS = (
    ("pdf", "PDF report", "application/pdf"),
    ("json", "JSON", "application/json"),
    ("csv", "CSV", "text/csv"),
)
"""Each download: its key in the links, its button label and its media type."""


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def bare(url: str) -> str:
    """A URL as shown in print: without the scheme."""
    return url.removeprefix("https://")


def sections(model: Model) -> dict[str, str]:
    """Every generated fragment of the page, keyed by its template slot name."""
    run, links = model["run"], model["links"]
    return {
        "HEADLINE": esc(model["headline"]),
        "CASES": esc(CASES),
        "RUN_DATE": esc(run["date"]),
        "TARGET": esc(model["target_host"]),
        "LOGO": esc(model["logo"]),
        "PAGE_LINK": f'<a href="{esc(links["page"])}">{esc(bare(links["page"]))}</a>',
        "DOWNLOADS": downloads(links),
        "TILES": tiles(model["domains"]),
        "SCORECARD": scorecard(model["domains"]),
        "CHECKED": checked(model["domains"]),
        "COVERAGE_TABLE": coverage_table(model["domains"]),
        "METHOD": method(model["domains"]),
        "METHOD_DOMAINS": method_domains(model["domains"]),
        "DOMAINS": "".join(
            domain_card(d, i, len(model["domains"]), links) for i, d in enumerate(model["domains"])
        ),
        "SOURCES": sources(model["domains"]),
    }


def downloads(links: Mapping[str, str]) -> str:
    return "".join(
        f'<a class="btn" href="{esc(links[key])}" download>{ICON_DOWN}{name}</a>'
        for key, name, _ in DOWNLOADS
    )


def status(summary: Mapping[str, Any]) -> str:
    counts = f"{summary['passed']:,} of {summary['points']:,}"
    if not summary["failed"] and not summary["missing"]:
        return f'<span class="status pass">{ICON_PASS}{counts}</span>'
    misses = ", ".join(
        f"{summary[key]:,} {word}"
        for key, word in (("failed", "fail"), ("missing", "missing"))
        if summary[key]
    )
    return f'<span class="status fail">{ICON_FAIL}{counts}, {misses}</span>'


def tiles(domains: Sequence[Model]) -> str:
    summaries = [s for d in domains for s in d["summaries"]]
    points = sum(s["points"] for s in summaries)
    passed = sum(s["passed"] for s in summaries)
    within = (
        "Within tolerance, every one"
        if passed == points
        else f"Within tolerance, {points - passed:,} not"
    )
    return "".join(
        f'<div class="panel tile p-4 sm:p-5"><div class="value">{value}</div>'
        f'<div class="label mt-1">{name}</div></div>'
        for value, name in (
            (f"{len(domains):,}", "Domain checked" if len(domains) == 1 else "Domains checked"),
            (f"{points:,}", "Values compared with a reference"),
            (f"{passed:,}", within),
        )
    )


def endpoints(domain: Model) -> str:
    return " ".join(
        f'<a href="{esc(e["url"])}"><code>{esc(e["label"])}</code></a>'
        for e in domain["endpoint_links"]
    )


def scorecard(domains: Sequence[Model]) -> str:
    rows = []
    for d in domains:
        total = combined(d["summaries"])
        title = (
            f'<a href="#domain-{esc(d["id"])}" style="color: var(--ink); font-weight: 600;">'
            f"{esc(d['title'])}</a>"
        )
        rows.append(
            f'<tr><td>{title}</td><td class="ink-2">{esc(d["authority"])}</td>'
            f'<td class="r">{total["points"]:,}</td><td>{status(total)}</td>'
            f'<td class="ink-2">{esc(measured_deviation(d["summaries"]))}</td></tr>'
        )
    return "".join(rows)


def checked(domains: Sequence[Model]) -> str:
    return "".join(
        f'<li class="flex flex-col sm:flex-row sm:gap-3">'
        f'<span class="font-semibold sm:w-56 shrink-0">{esc(d["title"])}</span>'
        f'<span class="ink-2">against {esc(d["authority"])}, through {endpoints(d)}</span></li>'
        for d in domains
    )


def coverage_table(domains: Sequence[Model]) -> str:
    rows = "".join(
        f"<tr><td><strong>{esc(d['title'])}</strong></td>"
        f"<td>{'; '.join(esc(s['name']) for s in d['sources'])}</td>"
        f"<td>{'; '.join(esc(c) for c in d['covers'])}</td></tr>"
        for d in domains
    )
    return (
        '<table class="data dense"><thead><tr><th>Domain</th><th>Reference authorities</th>'
        f"<th>Covers</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def method(domains: Sequence[Model]) -> str:
    used = dict.fromkeys(Unit(s["unit"]) for d in domains for s in d["summaries"])
    units = "".join(
        f'<li><span class="font-semibold" style="color: var(--ink);">{esc(u)}.</span> '
        f"{esc(UNIT_EXPLAIN[u])}</li>"
        for u in used
    )
    paragraphs = "".join(f"<p>{esc(p)}</p>" for p in METHOD)
    return f'{paragraphs}<ul class="space-y-1">{units}</ul><p>{RERUN}</p>'


def bands(domain: Model) -> list[tuple[str, str, str]]:
    """Each pass band of a domain as (who it applies to, size with unit, why)."""
    several = len(domain["tolerances"]) > 1
    out = []
    for t in domain["tolerances"]:
        if t["applies_to"] == ALL:
            who = "Every other quantity" if several else "Every quantity"
        else:
            who = ", ".join(t["applies_to"])
        out.append((who, f"{fmt(t['value'])} {t['unit']}", t["why"]))
    return out


def method_domains(domains: Sequence[Model]) -> str:
    out = []
    for d in domains:
        methods = "".join(
            f'<p><span class="font-semibold" style="color: var(--ink);">{esc(s["name"])}.</span> '
            f"{esc(s['method'])}</p>"
            for s in d["sources"]
        )
        rows = "".join(
            f'<tr><td>{esc(who)}</td><td class="r">{esc(size)}</td>'
            f'<td class="ink-2">{esc(why)}</td></tr>'
            for who, size, why in bands(d)
        )
        out.append(
            f'<div class="avoid-break"><h3>{esc(d["title"])}</h3>'
            f'<div class="mt-2 space-y-2 ink-2">{methods}</div>'
            f'<div class="panel mt-3 overflow-x-auto"><table class="data"><thead><tr>'
            f'<th>Applies to</th><th class="r">Pass band</th><th>Why this size</th></tr></thead>'
            f"<tbody>{rows}</tbody></table></div></div>"
        )
    return "".join(out)


def summary_block(summary: Mapping[str, Any], di: int, si: int) -> str:
    """The largest deviation per quantity: a chart over a fallback table, or the exact match line.

    The table is the canvas fallback content, so a reader without scripts and a crawler see the
    figures the chart draws.
    """
    unit = esc(summary["unit"])
    worst: Sequence[Mapping[str, Any]] = summary["per_quantity_max"]
    if not any(w["deviation"] > 0 for w in worst):
        return (
            f'<div class="rule pt-4"><p class="eyebrow">{unit}</p><p class="mt-2 ink-2">'
            f'<span class="status pass">{ICON_PASS}</span> All {summary["points"]:,} values match '
            "the reference exactly, a deviation of 0 on every case.</p></div>"
        )
    rows = "".join(
        f'<tr><td>{esc(w["quantity"])}</td><td class="r">{fmt_up(w["deviation"])}</td>'
        f"<td>{esc(w['case'])}</td></tr>"
        for w in worst
    )
    return (
        f'<div class="rule pt-4 avoid-break"><p class="eyebrow">Largest deviation per quantity, '
        f'{unit}</p><p class="mt-1 text-sm muted">Worst case across every subject. Median '
        f"{fmt(summary['median'])}, p95 {fmt(summary['p95'])}, max {fmt_up(summary['max'])} {unit}."
        f'</p><div class="chart-box mt-3" style="height: {len(worst) * 26 + 44}px;">'
        f'<canvas id="chart-{di}-{si}" data-chart="{di} {si}" role="img" '
        f'aria-label="Largest deviation per quantity in {unit}"><table class="data dense">'
        f'<thead><tr><th>Quantity</th><th class="r">Largest deviation, {unit}</th><th>Case</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></canvas></div></div>"
    )


def domain_card(d: Model, di: int, count: int, links: Mapping[str, str]) -> str:
    slug = esc(d["id"])
    chips = " ".join(
        f'<span class="chip">{esc(who)}: {esc(size)}</span>' for who, size, _ in bands(d)
    )
    items = "".join(f"<li>{esc(line)}</li>" for line in d["quantity_lines"])
    lines = (
        '<div class="rule pt-4 avoid-break"><p class="eyebrow">Per quantity</p>'
        f'<ul class="mt-2 space-y-1 ink-2">{items}</ul></div>'
        if items
        else ""
    )
    blocks = "".join(summary_block(s, di, si) for si, s in enumerate(d["summaries"]))
    points = len(d["measurements"])
    files = " and ".join(
        f'<a href="{esc(links[k])}">{esc(bare(links[k]))}</a>' for k in ("csv", "json")
    )
    return (
        f'<section id="domain-{slug}" class="page" aria-labelledby="domain-{slug}-title">'
        f'<p class="eyebrow print-only">Domain {di + 1} of {count}</p>'
        '<div class="panel p-5 sm:p-6 space-y-4">'
        '<div class="flex flex-wrap items-start justify-between gap-3"><div>'
        f'<h2 id="domain-{slug}-title">{esc(d["title"])}</h2>'
        f'<p class="mt-1 ink-2">Authority: {esc(d["authority"])}</p>'
        f'<p class="mt-1 ink-2">Covers: {esc("; ".join(d["covers"]))}</p>'
        f'<p class="mt-1 text-sm muted">{endpoints(d)}</p></div>'
        f'<div class="flex flex-col items-end gap-1">{"".join(status(s) for s in d["summaries"])}'
        f'</div></div><div class="flex flex-wrap gap-2">{chips}</div>{lines}{blocks}'
        '<div class="rule pt-4">'
        f'<button type="button" class="btn screen-only" aria-expanded="false" '
        f'aria-controls="measurements-{di}" data-toggle="{di}">Show all {points:,} measurements'
        "</button>"
        f'<p class="files ink-2 mt-2 print:mt-0">All {points:,} measurements of this domain, '
        f"case by case, are in {files}.</p>"
        f'<div id="measurements-{di}" class="measurements mt-3 overflow-x-auto" hidden>'
        '<table class="data dense"><thead><tr><th>Case</th><th>Quantity</th>'
        '<th class="r">Expected</th><th class="r">Returned</th><th class="r">Deviation</th>'
        '<th class="r">Band</th><th>Unit</th><th>Status</th></tr></thead><tbody></tbody>'
        "</table></div></div></div></section>"
    )


def sources(domains: Sequence[Model]) -> str:
    out = []
    for d in domains:
        cards = "".join(source_card(s) for s in d["sources"])
        out.append(
            f'<div class="avoid-break"><h3>{esc(d["title"])}</h3>'
            f'<div class="mt-3 space-y-3">{cards}</div></div>'
        )
    return "".join(out)


def source_card(s: Mapping[str, Any]) -> str:
    url = s.get("url")
    name = f'<a href="{esc(url)}">{esc(s["name"])}</a>' if url else esc(s["name"])
    shown = (
        f'<p class="text-sm muted mono" style="overflow-wrap: anywhere;">{esc(url)}</p>'
        if url
        else ""
    )
    fields = [
        ("Licence", f'<dd class="ink-2">{esc(s["licence"])}</dd>'),
        ("Retrieved", f'<dd class="ink-2 num">{esc(s["retrieved"])}</dd>'),
    ]
    if s.get("citation"):
        fields.append(("Citation", f'<dd class="ink-2">{esc(s["citation"])}</dd>'))
    if s.get("command"):
        fields.append(("Regenerate", f"<dd><code>{esc(s['command'])}</code></dd>"))
    if s.get("notes"):
        fields.append(("Notes", f'<dd class="ink-2">{esc(s["notes"])}</dd>'))
    if s["applies_to"] != ALL:
        fields.append(("Covers", f'<dd class="ink-2">{esc(", ".join(s["applies_to"]))}</dd>'))
    rows = "".join(f'<dt class="muted">{term}</dt>{value}' for term, value in fields)
    return (
        f'<div class="panel p-4 sm:p-5"><p class="font-semibold">{name}</p>{shown}'
        '<dl class="mt-2 grid grid-cols-1 sm:grid-cols-[9rem_1fr] gap-x-4 gap-y-1 text-sm">'
        f"{rows}</dl></div>"
    )
