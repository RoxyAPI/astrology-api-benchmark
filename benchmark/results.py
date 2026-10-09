"""Run domains, then write ``results/latest.json`` (the published record) and a flat CSV."""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from benchmark.api import ApiClient
from benchmark.domains import LoadedDomain
from benchmark.schema import RESULT_FORMAT, Domain, Measurement, Status, Summary
from benchmark.stats import summarize

JSON_FILE = "latest.json"
CSV_FILE = "latest.csv"
CSV_COLUMNS = (
    "domain",
    "case",
    "quantity",
    "unit",
    "expected",
    "actual",
    "deviation",
    "tolerance",
    "status",
    "note",
)


class ResultsError(Exception):
    """A results file this version cannot read."""


@dataclass(frozen=True, slots=True)
class DomainResult:
    domain: Domain
    measurements: tuple[Measurement, ...]
    summaries: tuple[Summary, ...]


def run_domain(loaded: LoadedDomain, api: ApiClient) -> DomainResult:
    measurements = tuple(loaded.check(api, loaded.references))
    return DomainResult(loaded.domain, measurements, summarize(loaded.domain.id, measurements))


def exit_code(results: Sequence[DomainResult]) -> int:
    """1 when any value FAILed or is MISSING: a red run is the only alert."""
    statuses = {m.status for r in results for m in r.measurements}
    return 1 if statuses & {Status.FAIL, Status.MISSING} else 0


def document(run_date: str, target: str, results: Sequence[DomainResult]) -> dict[str, Any]:
    return {
        "format": RESULT_FORMAT,
        "run": {"date": run_date, "target": target},
        "domains": [
            {
                **asdict(r.domain),
                "summaries": [asdict(s) for s in r.summaries],
                "measurements": [asdict(m) for m in r.measurements],
            }
            for r in results
        ],
    }


def write_results(out_dir: Path, doc: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = out_dir / JSON_FILE, out_dir / CSV_FILE
    json_path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for domain in doc["domains"]:
            for m in domain["measurements"]:
                writer.writerow({"domain": domain["id"], **m})
    return json_path, csv_path


def read_results(path: Path) -> dict[str, Any]:
    """Load a results file, refusing any ``format`` other than the one this code writes."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("format") != RESULT_FORMAT:
        raise ResultsError(f"{path.name}: unsupported results format, expected {RESULT_FORMAT}")
    return doc
