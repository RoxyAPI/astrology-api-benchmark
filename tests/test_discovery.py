"""Discovery end to end on the fixture domain: load, run against a fake API, write, read back."""

from __future__ import annotations

import csv
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from benchmark import Status, Unit
from benchmark.__main__ import main
from benchmark.domains import DomainError, discover, load_pull, write_references
from benchmark.results import (
    CSV_COLUMNS,
    ResultsError,
    document,
    exit_code,
    read_results,
    run_domain,
    write_results,
)
from benchmark.schema import RESULT_FORMAT, Chart
from tests.conftest import FIXTURE_DOMAINS, VALID_REFERENCES, FakeApi, Respond

ANSWERS: dict[str, dict[str, Any]] = {
    "2000-01-01": {
        "angle": 0.004,
        "instant": "2000-01-01T12:00:30Z",
        "count": 10,
        "day": "2000-01-02",
        "label": "a",
    },
    "1961-08-04": {"angle": 10.0},
}


def _responder(answers: Mapping[str, Any]) -> Respond:
    def respond(method: str, path: str, body: Mapping[str, Any] | None) -> Any:
        assert (method, path) == ("POST", "/example")
        assert body is not None
        return {"values": answers[body["date"]]}

    return respond


def test_fixture_domain_runs_end_to_end(charts: dict[str, Chart], tmp_path: Path) -> None:
    (loaded,) = discover(charts, FIXTURE_DOMAINS)
    assert loaded.domain.id == "example"
    api = FakeApi(_responder(ANSWERS))
    result = run_domain(loaded, api)

    status = {(m.case, m.quantity): m.status for m in result.measurements}
    assert status == {
        ("inline", "angle"): Status.PASS,
        ("inline", "instant"): Status.PASS,
        ("inline", "count"): Status.PASS,
        ("inline", "day"): Status.FAIL,
        ("inline", "label"): Status.PASS,
        ("charted", "angle"): Status.PASS,
        ("charted", "label"): Status.MISSING,
    }
    assert api.calls[1][2] == charts["obama"].request()
    assert [s.unit for s in result.summaries] == [Unit.ARCSEC, Unit.SECONDS, Unit.DAYS, Unit.EXACT]
    assert exit_code([result]) == 1

    json_path, csv_path = write_results(tmp_path, document("2026-01-02", "https://t", [result]))
    doc = read_results(json_path)
    assert doc["format"] == RESULT_FORMAT
    assert doc["run"] == {"date": "2026-01-02", "target": "https://t"}
    (domain,) = doc["domains"]
    assert domain["id"] == "example"
    assert domain["endpoints"] == [{"method": "POST", "path": "/example", "tag": "Example"}]
    assert len(domain["measurements"]) == 7
    assert domain["summaries"][0]["worst_case"]["quantity"] == "angle"
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 7
    assert rows[-1]["status"] == "MISSING"
    assert rows[-1]["deviation"] == ""


def test_all_pass_exits_zero(charts: dict[str, Chart]) -> None:
    (loaded,) = discover(charts, FIXTURE_DOMAINS)
    answers = {
        "2000-01-01": {**ANSWERS["2000-01-01"], "day": "2000-01-01"},
        "1961-08-04": {"angle": 10.0, "label": "b"},
    }
    result = run_domain(loaded, FakeApi(_responder(answers)))
    assert exit_code([result]) == 0


def test_unknown_results_format_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    path.write_text(json.dumps({"format": RESULT_FORMAT + 1}), encoding="utf-8")
    with pytest.raises(ResultsError):
        read_results(path)


def _domain(root: Path, name: str, check: str | None, refs: dict[str, Any] | None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    if check is not None:
        (folder / "check.py").write_text(check, encoding="utf-8")
    if refs is not None:
        (folder / "references.json").write_text(json.dumps(refs), encoding="utf-8")
    return folder


CHECK_SOURCE = """
from benchmark import Domain, Endpoint
DOMAIN = Domain(
    id="{id}", title="T", authority="A", endpoints=(Endpoint("GET", "/x", "X"),), order={order}
)
def check(api, refs):
    return []
"""


def _refs(domain: str) -> dict[str, Any]:
    return {**VALID_REFERENCES, "domain": domain}


def test_discovery_orders_by_order_then_id(charts: dict[str, Chart], tmp_path: Path) -> None:
    for name, order in (("b-two", 2), ("a-two", 2), ("z-one", 1)):
        _domain(tmp_path, name, CHECK_SOURCE.format(id=name, order=order), _refs(name))
    (tmp_path / "empty").mkdir()
    assert [d.domain.id for d in discover(charts, tmp_path)] == ["z-one", "a-two", "b-two"]


@pytest.mark.parametrize(
    ("check", "refs", "message"),
    [
        (None, _refs("bad"), "needs check.py"),
        ("X = 1\n", _refs("bad"), "must export DOMAIN"),
        (CHECK_SOURCE.format(id="other", order=0), _refs("bad"), "must equal the folder name"),
        (CHECK_SOURCE.format(id="bad", order=0), None, "references.json is missing"),
        (CHECK_SOURCE.format(id="bad", order=0), {"format": 1}, "missing cases"),
    ],
)
def test_broken_domain_folders_fail_loudly(
    charts: dict[str, Chart],
    tmp_path: Path,
    check: str | None,
    refs: dict[str, Any] | None,
    message: str,
) -> None:
    _domain(tmp_path, "bad", check, refs)
    with pytest.raises(DomainError, match=message):
        discover(charts, tmp_path)


def test_pull_output_is_validated_then_written(charts: dict[str, Chart], tmp_path: Path) -> None:
    folder = _domain(tmp_path, "example", None, None)
    (folder / "pull.py").write_text(
        f"def pull():\n    return {_refs('example')!r}\n", encoding="utf-8"
    )
    path = write_references(folder, load_pull(folder)(), charts)
    assert json.loads(path.read_text(encoding="utf-8")) == _refs("example")
    assert path.read_text(encoding="utf-8").endswith("}\n")
    with pytest.raises(DomainError, match="pulled references are invalid"):
        write_references(folder, {"format": 1}, charts)


def test_pull_needs_a_pull_function(tmp_path: Path) -> None:
    folder = _domain(tmp_path, "example", None, None)
    (folder / "pull.py").write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(DomainError, match="must export pull"):
        load_pull(folder)


def test_cli_run_without_a_key_is_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    domains = tmp_path / "domains"
    shutil.copytree(FIXTURE_DOMAINS, domains)
    monkeypatch.setattr("benchmark.__main__.DOMAINS_DIR", domains)
    monkeypatch.delenv("BENCHMARK_API_KEY", raising=False)
    code = main(["run", "--env-file", str(tmp_path / "absent"), "--out", str(tmp_path / "r")])
    assert code == 2
    assert "BENCHMARK_API_KEY" in capsys.readouterr().err
