from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from benchmark.__main__ import main
from benchmark.claims import amount, fmt, quantity_stats
from benchmark.domains import discover, references_for
from benchmark.paths import RESULTS_DIR
from benchmark.readme import (
    BLOCKS,
    ReadmeError,
    begin_marker,
    end_marker,
    render_blocks,
    replace_blocks,
    update,
)
from benchmark.results import JSON_FILE, DomainResult, ResultsError, document, read_results
from benchmark.schema import Chart, load_charts
from benchmark.stats import measure, summarize
from tests.test_public_content import _markdown, violations

SKELETON = "\n\n".join(f"{begin_marker(n)}\nstale {n}\n{end_marker(n)}" for n in BLOCKS) + "\n"


def committed_blocks() -> dict[str, str]:
    results = read_results(RESULTS_DIR / JSON_FILE)
    refs = references_for((d["id"] for d in results["domains"]), load_charts())
    return render_blocks(results, refs)


def copy_inputs(tmp_path: Path, readme: str = SKELETON) -> tuple[Path, Path]:
    results = tmp_path / JSON_FILE
    shutil.copyfile(RESULTS_DIR / JSON_FILE, results)
    path = tmp_path / "README.md"
    path.write_text(readme, encoding="utf-8")
    return path, results


def test_update_round_trips_and_is_idempotent(tmp_path: Path) -> None:
    readme, results = copy_inputs(tmp_path, f"# Title\n\n{SKELETON}\nHand written tail.\n")
    assert update(readme, results, check=True)
    assert "stale" in readme.read_text(encoding="utf-8")
    assert update(readme, results)
    first = readme.read_text(encoding="utf-8")
    assert not update(readme, results)
    assert readme.read_text(encoding="utf-8") == first
    assert first.startswith("# Title\n") and first.endswith("Hand written tail.\n")
    assert "stale" not in first
    for name, body in committed_blocks().items():
        assert f"{begin_marker(name)}\n{body}\n{end_marker(name)}" in first


def test_check_command_exits_one_on_drift_and_zero_when_current(tmp_path: Path) -> None:
    readme, results = copy_inputs(tmp_path)
    args = ["readme", "--readme", str(readme), "--results", str(results)]
    assert main([*args, "--check"]) == 1
    assert "stale" in readme.read_text(encoding="utf-8")
    assert main(args) == 0
    assert main([*args, "--check"]) == 0


@pytest.mark.parametrize("name", BLOCKS)
def test_a_missing_marker_is_refused(tmp_path: Path, name: str) -> None:
    readme, results = copy_inputs(tmp_path, SKELETON.replace(end_marker(name), ""))
    with pytest.raises(ReadmeError):
        update(readme, results)
    assert main(["readme", "--readme", str(readme), "--results", str(results)]) == 2


def test_a_repeated_or_reversed_pair_is_refused() -> None:
    blocks = dict.fromkeys(BLOCKS, "x")
    with pytest.raises(ReadmeError):
        replace_blocks(SKELETON + begin_marker("claim"), blocks)
    swapped = SKELETON.replace(begin_marker("claim"), "@").replace(end_marker("claim"), "#")
    reversed_pair = swapped.replace("@", end_marker("claim")).replace("#", begin_marker("claim"))
    with pytest.raises(ReadmeError):
        replace_blocks(reversed_pair, blocks)


def test_an_unknown_results_format_is_refused(tmp_path: Path) -> None:
    readme, results = copy_inputs(tmp_path)
    doc = json.loads(results.read_text(encoding="utf-8"))
    results.write_text(json.dumps({**doc, "format": 999}), encoding="utf-8")
    with pytest.raises(ResultsError):
        update(readme, results)
    assert readme.read_text(encoding="utf-8") == SKELETON


def test_claim_carries_the_generated_totals_and_angle_median() -> None:
    results = read_results(RESULTS_DIR / JSON_FILE)
    summaries = [s for d in results["domains"] for s in d["summaries"]]
    claim = committed_blocks()["claim"]
    passed, points = sum(s["passed"] for s in summaries), sum(s["points"] for s in summaries)
    assert f"{passed:,} of {points:,} values within tolerance" in claim
    assert results["run"]["date"] in claim


@pytest.mark.parametrize(
    ("value", "shown"),
    [(None, "n/a"), (0.0, "0"), (0.048414, "0.048"), (0.31, "0.31"), (9.96, "10"), (36.0, "36")],
)
def test_fmt_matches_the_report_page_rule(value: float | None, shown: str) -> None:
    assert fmt(value) == shown


def test_every_domain_renders_public_prose(charts: dict[str, Chart]) -> None:
    """Every discovered domain, run or not, renders README text the public guard accepts."""
    loaded = discover(charts)
    results = []
    for d in loaded:
        refs = d.references
        ms = tuple(
            measure(refs, case, q, case.expected[q]) for case in refs.cases for q in case.expected
        )
        results.append(DomainResult(d.domain, ms, summarize(d.domain.id, ms)))
    doc: dict[str, Any] = json.loads(
        json.dumps(document("2026-01-01", "https://x.invalid", results))
    )
    text = replace_blocks(SKELETON, render_blocks(doc, {d.domain.id: d.references for d in loaded}))
    assert not violations(list(_markdown(text)))
    for d in loaded:
        assert f"### {d.domain.title}" in text


def test_results_without_tiers_still_render(tmp_path: Path) -> None:
    readme, results = copy_inputs(tmp_path)
    doc = json.loads(results.read_text(encoding="utf-8"))
    for domain in doc["domains"]:
        for summary in domain["summaries"]:
            summary.pop("tiers", None)
    results.write_text(json.dumps(doc), encoding="utf-8")
    assert update(readme, results)
    text = readme.read_text(encoding="utf-8")
    assert "values within tolerance" in text


def test_scorecard_lists_each_domain_once_and_drops_precision() -> None:
    rows = committed_blocks()["scorecard"].splitlines()
    assert "Precision" not in rows[0]
    links = [r.split(" | ")[0] for r in rows[2:] if not r.startswith("|  |")]
    assert len(links) == len(set(links))
    assert any(r.startswith("|  |  | ") for r in rows[2:])


def test_per_quantity_max_rounds_up_like_the_claim_sentences() -> None:
    results = read_results(RESULTS_DIR / JSON_FILE)
    refs = references_for((d["id"] for d in results["domains"]), load_charts())
    domain = next(d for d in results["domains"] if d["id"] == "western-planets")
    top = max(quantity_stats(domain, refs[domain["id"]]), key=lambda q: q.max or 0)
    text = committed_blocks()["domains"]
    assert amount(top.max, top.unit, up=True) in text
    assert "**Precision tiers**" not in text


def test_scorecard_max_rounds_up_and_domains_link_the_report_card() -> None:
    blocks = committed_blocks()
    assert "| 0.32 | arcsec |" in blocks["scorecard"]
    assert (
        "(https://roxyapi.github.io/astrology-api-benchmark/#domain-western-planets)"
        in (blocks["domains"])
    )
