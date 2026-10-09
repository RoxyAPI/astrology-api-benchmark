"""Build the report page: ``site/template.html`` with the results and their sources inlined.

The output is one self-contained file, ``dist/index.html``, so the same bytes work on Pages,
from ``file://``, in a screenshot and when printed to PDF.
"""

from __future__ import annotations

import base64
import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmark.claims import headline, quantity_lines, target_host
from benchmark.diagram import coverage_map, family_labels
from benchmark.domains import references_for
from benchmark.paths import DIST_DIR, DOMAINS_DIR, LOGO_PATH, RESULTS_DIR, TEMPLATE_PATH
from benchmark.results import CSV_FILE, JSON_FILE, read_results
from benchmark.schema import Endpoint, load_charts
from benchmark.spec import link

PLACEHOLDER = "__REPORT_DATA__"
"""Where the template takes the data, inside a ``<script type="application/json">`` element."""

OUTPUT_FILE = "index.html"
PDF_FILE = "report.pdf"
"""The latest report as a PDF, printed from the page and published beside it."""

SITE_URL = "https://roxyapi.github.io/astrology-api-benchmark/"
"""The stable address of the latest report. The page links its downloads from here."""

# A JSON string may hold "</script>" or "<!--"; escaping these three keeps the data inert in HTML
# while JSON.parse still reads the identical text.
_HTML_SAFE = str.maketrans({"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"})


class SiteError(Exception):
    """The template cannot take the data."""


def report_data(
    results: dict[str, Any], domains_dir: Path = DOMAINS_DIR, logo_path: Path = LOGO_PATH
) -> dict[str, Any]:
    """The results with each domain carrying its sources, tolerances and per quantity lines, the
    shared headline, the logo and the links."""
    refs = references_for((d["id"] for d in results["domains"]), load_charts(), domains_dir)
    domains = [
        {
            **domain,
            "covers": family_labels(refs[domain["id"]]),
            "sources": [asdict(s) for s in refs[domain["id"]].sources],
            "tolerances": [asdict(t) for t in refs[domain["id"]].tolerances],
            "quantity_lines": quantity_lines(results, domain, refs[domain["id"]]),
            "endpoint_links": [link(Endpoint(**e)) for e in domain["endpoints"]],
        }
        for domain in results["domains"]
    ]
    logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return {
        **results,
        "domains": domains,
        "target_host": target_host(results["run"]["target"]),
        "headline": " ".join(headline(results)),
        "coverage": coverage_map(results["domains"], refs),
        "logo": f"data:image/png;base64,{logo}",
        "links": {
            "page": SITE_URL,
            "pdf": SITE_URL + PDF_FILE,
            "json": SITE_URL + JSON_FILE,
            "csv": SITE_URL + CSV_FILE,
        },
    }


def render(template: str, data: dict[str, Any]) -> str:
    if template.count(PLACEHOLDER) != 1:
        raise SiteError(f"the template must hold {PLACEHOLDER} exactly once")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).translate(_HTML_SAFE)
    return template.replace(PLACEHOLDER, payload)


def build(
    results_path: Path = RESULTS_DIR / JSON_FILE,
    template_path: Path = TEMPLATE_PATH,
    out_dir: Path = DIST_DIR,
    domains_dir: Path = DOMAINS_DIR,
) -> Path:
    """Write ``out_dir/index.html`` beside copies of the results it links for download.

    Refuses a results format this version does not read.
    """
    data = report_data(read_results(results_path), domains_dir)
    html = render(template_path.read_text(encoding="utf-8"), data)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (JSON_FILE, CSV_FILE):
        shutil.copyfile(results_path.with_name(name), out_dir / name)
    path = out_dir / OUTPUT_FILE
    path.write_text(html, encoding="utf-8")
    return path
