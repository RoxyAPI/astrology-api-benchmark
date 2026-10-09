"""The colored console run: header, a line per domain, failing values, a boxed scorecard.

Standard library only. Color is on for a terminal, off when ``NO_COLOR`` is set or the output is
a pipe, and forced on by ``FORCE_COLOR`` (screen recordings). Off means plain ASCII text, so CI
logs and pipes stay clean.
"""

from __future__ import annotations

import os
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any, TextIO

from benchmark.claims import amount, best_tier, fmt, headline
from benchmark.results import DomainResult
from benchmark.schema import Measurement, Status, Summary, Unit

MAX_FAILURES = 5
"""Failing values listed per domain; the rest are counted and live in the CSV."""

BOX_WIDTH = 74
"""Inner width of the scorecard box in columns."""

_SGR = {"bold": "1", "dim": "2", "green": "32", "red": "31", "cyan": "36"}
_RESET = "\x1b[0m"
_CLEAR_LINE = "\r\x1b[2K"


def use_color(stream: TextIO, environ: Mapping[str, str] = os.environ) -> bool:
    """``FORCE_COLOR`` wins, then ``NO_COLOR``, else whether the stream is a terminal."""
    if environ.get("FORCE_COLOR"):
        return True
    if environ.get("NO_COLOR"):
        return False
    return stream.isatty()


class Console:
    """Writes the run to one stream; ``color`` also selects box drawing and check marks."""

    def __init__(self, stream: TextIO, color: bool) -> None:
        self.stream = stream
        self.color = color

    def paint(self, text: str, *styles: str) -> str:
        if not self.color:
            return text
        return "".join(f"\x1b[{_SGR[s]}m" for s in styles) + text + _RESET

    def _print(self, text: str = "") -> None:
        print(text, file=self.stream)

    def header(self, target: str, run_date: str) -> None:
        brand = self.paint("Roxy", "bold") + self.paint("API", "dim")
        self._print()
        self._print(f"  {brand}  {self.paint('Open Accuracy Benchmark', 'bold')}")
        self._print(f"  {self.paint('target', 'dim')}  {target}")
        self._print(f"  {self.paint('run   ', 'dim')}  {run_date}")
        self._print()

    def start(self, title: str) -> None:
        """A transient progress line, only where a terminal can overwrite it."""
        if self.color:
            self.stream.write(f"  {self.paint('...', 'dim')} {title}")
            self.stream.flush()

    def domain(self, result: DomainResult, width: int) -> None:
        if self.color:
            self.stream.write(_CLEAR_LINE)
        for line in domain_lines(result, width, self):
            self._print(line)

    def scorecard(self, results: Sequence[DomainResult], doc: Mapping[str, Any]) -> None:
        self._print()
        for line in scorecard_lines(results, doc, self):
            self._print(line)

    def mark(self, ok: bool) -> str:
        if self.color:
            return self.paint("✓", "green", "bold") if ok else self.paint("✗", "red", "bold")
        return "PASS" if ok else "FAIL"


def domain_lines(result: DomainResult, width: int, console: Console) -> list[str]:
    """One line per unit of the domain, then one per failing or missing value."""
    ok = all(s.failed == 0 and s.missing == 0 for s in result.summaries)
    lines = []
    for i, s in enumerate(result.summaries):
        title = result.domain.title if i == 0 else ""
        counts = f"{s.passed:,}/{s.points:,}"
        head = f"  {console.mark(ok) if i == 0 else ' ' * (1 if console.color else 4)}"
        lines.append(
            f"{head} {console.paint(title.ljust(width), 'bold')}  "
            f"{console.paint(counts.rjust(9), 'green' if s.passed == s.points else 'red')}  "
            f"{_spread(s, console)}"
        )
    failing = [m for m in result.measurements if m.status != Status.PASS]
    lines += [_failure(m, console) for m in failing[:MAX_FAILURES]]
    if len(failing) > MAX_FAILURES:
        more = f"    and {len(failing) - MAX_FAILURES:,} more, all in results/latest.csv"
        lines.append(console.paint(more, "red"))
    return lines


def _spread(s: Summary, console: Console) -> str:
    if s.unit == Unit.EXACT:
        return console.paint("exact match", "dim")
    if s.median is None or s.max is None:
        return console.paint("nothing measured", "red")
    text = f"median {fmt(s.median)}  max {amount(s.max, s.unit)}"
    tier = best_tier(asdict(s))
    return text + (f"  {console.paint(tier, 'cyan')}" if tier else "")


def _failure(m: Measurement, console: Console) -> str:
    detail = (
        m.note
        if m.deviation is None
        else f"expected {m.expected} got {m.actual}, deviation {amount(m.deviation, m.unit)}"
    )
    text = f"    {m.status.value} {m.case} {m.quantity}: {detail}"
    return console.paint(text, "red")


def scorecard_lines(
    results: Sequence[DomainResult], doc: Mapping[str, Any], console: Console
) -> list[str]:
    summaries = [s for r in results for s in r.summaries]
    points = sum(s.points for s in summaries)
    passed = sum(s.passed for s in summaries)
    ok = passed == points
    verdict = console.paint("PASS" if ok else "FAIL", "green" if ok else "red", "bold")
    rows = [
        f"{console.paint('Scorecard', 'bold')}  {verdict}",
        "",
        f"{len(results)} domains, {passed:,} of {points:,} values within tolerance",
    ]
    claim = headline(doc)
    if len(claim) > 1:
        rows += ["", *textwrap.wrap(claim[0], BOX_WIDTH - 2)]
    return _box(rows, console)


def _box(rows: Sequence[str], console: Console) -> list[str]:
    tl, tr, bl, br, h, v = "┌┐└┘─│" if console.color else "++++-|"
    edge = console.paint
    lines = [edge(f"  {tl}{h * (BOX_WIDTH + 2)}{tr}", "dim")]
    for row in rows:
        pad = " " * (BOX_WIDTH - _visible(row))
        lines.append(f"  {edge(v, 'dim')} {row}{pad} {edge(v, 'dim')}")
    lines.append(edge(f"  {bl}{h * (BOX_WIDTH + 2)}{br}", "dim"))
    return lines


def _visible(text: str) -> int:
    """Length of ``text`` without ANSI escapes."""
    length, i = 0, 0
    while i < len(text):
        if text[i] == "\x1b":
            i = text.index("m", i) + 1
        else:
            length += 1
            i += 1
    return length
