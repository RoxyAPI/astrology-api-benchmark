"""Build the report page: ``site/template.html`` with every section rendered and the data inlined.

The output is one self-contained file, ``dist/index.html``, so the same bytes work on Pages,
from ``file://``, in a screenshot and when printed to PDF. Every claim, table and card is HTML
text rendered here (``page.py``), with the head metadata and schema.org JSON-LD generated from the
results and references, so the page reads in full without JavaScript. The inlined JSON feeds only
the charts, the coverage diagram and the measurement tables. ``robots.txt`` and ``sitemap.xml``
are written beside it.
"""

from __future__ import annotations

import base64
import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from benchmark import page
from benchmark.claims import headline, labels, quantity_lines, subject, target_host
from benchmark.diagram import coverage_map, family_labels
from benchmark.domains import references_for
from benchmark.paths import DIST_DIR, DOMAINS_DIR, LOGO_PATH, RESULTS_DIR, TEMPLATE_PATH
from benchmark.results import CSV_FILE, JSON_FILE, read_results
from benchmark.schema import Endpoint, load_charts
from benchmark.spec import link

DATA_SLOT = "REPORT_DATA"
PLACEHOLDER = f"__{DATA_SLOT}__"
"""Where the template takes the data, inside a ``<script type="application/json">`` element."""

_SLOT = re.compile(r"__([A-Z]+(?:_[A-Z]+)*)__")
"""A template slot, ``__NAME__``: the data once, every rendered fragment at least once."""

OUTPUT_FILE = "index.html"
PDF_FILE = "report.pdf"
"""The latest report as a PDF, printed from the page and published beside it."""
ROBOTS_FILE = "robots.txt"
SITEMAP_FILE = "sitemap.xml"

SITE_URL = "https://roxyapi.github.io/astrology-api-benchmark/"
"""The stable address of the latest report. The page links its downloads from here."""
RAW_URL = "https://raw.githubusercontent.com/RoxyAPI/astrology-api-benchmark/main/"
IMAGE_URL = RAW_URL + "assets/report.png"
"""The report screenshot the README shows, as the social preview image."""

TITLE = "RoxyAPI Accuracy Report"
DATASET_NAME = "Astrology API Accuracy Benchmark results"
DESCRIPTION_MAX = 160
LICENSE_URL = "https://opensource.org/licenses/MIT"
PUBLISHER = {
    "@type": "Organization",
    "@id": "https://roxyapi.com/#organization",
    "name": "RoxyAPI",
    "url": "https://roxyapi.com",
    "logo": "https://roxyapi.com/logo.png",
}
"""The publisher, under the same ``@id`` as on roxyapi.com so search engines join the two."""

# A JSON string may hold "</script>" or "<!--"; escaping these three keeps the data inert in HTML
# while JSON.parse still reads the identical text.
_HTML_SAFE = str.maketrans({"<": "\\u003c", ">": "\\u003e", "&": "\\u0026"})


class SiteError(Exception):
    """The template cannot take the data."""


def report_data(
    results: dict[str, Any], domains_dir: Path = DOMAINS_DIR, logo_path: Path = LOGO_PATH
) -> dict[str, Any]:
    """The page model: the results with each domain carrying its sources, tolerances, per quantity
    lines and unit labels, the shared headline and description, the logo and the links."""
    refs = references_for((d["id"] for d in results["domains"]), load_charts(), domains_dir)
    names = labels(refs)
    domains = [
        {
            **domain,
            "covers": family_labels(refs[domain["id"]]),
            "sources": [asdict(s) for s in refs[domain["id"]].sources],
            "tolerances": [asdict(t) for t in refs[domain["id"]].tolerances],
            "quantity_lines": quantity_lines(results, domain, refs[domain["id"]]),
            "endpoint_links": [link(Endpoint(**e)) for e in domain["endpoints"]],
            "unit_labels": {
                s["unit"]: names[(domain["id"], s["unit"])]
                for s in domain["summaries"]
                if (domain["id"], s["unit"]) in names
            },
        }
        for domain in results["domains"]
    ]
    sentences = headline(results, names)
    fallback = (
        f"Open accuracy benchmark of {subject(results)}: every returned value compared with a "
        "named reference source and a stated pass band."
    )
    logo = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return {
        **results,
        "domains": domains,
        "target_host": target_host(results["run"]["target"]),
        "headline": " ".join(sentences),
        "description": next((s for s in sentences if len(s) < DESCRIPTION_MAX), fallback),
        "coverage": coverage_map(results["domains"], refs),
        "logo": f"data:image/png;base64,{logo}",
        "links": {
            "page": SITE_URL,
            "pdf": SITE_URL + PDF_FILE,
            "json": SITE_URL + JSON_FILE,
            "csv": SITE_URL + CSV_FILE,
        },
    }


def script_data(model: Mapping[str, Any]) -> dict[str, Any]:
    """What the page script reads: chart rows, measurements, the coverage source, the run."""
    return {
        "run": model["run"],
        "links": {"page": model["links"]["page"]},
        "coverage": model["coverage"],
        "icons": {"pass": page.ICON_PASS, "fail": page.ICON_FAIL},
        "domains": [
            {
                "summaries": [
                    {"unit": s["unit"], "per_quantity_max": s["per_quantity_max"]}
                    for s in d["summaries"]
                ],
                "measurements": d["measurements"],
            }
            for d in model["domains"]
        ],
    }


def title(model: Mapping[str, Any]) -> str:
    return f"{TITLE} {model['run']['date']}"


def json_ld(model: Mapping[str, Any]) -> dict[str, Any]:
    """A schema.org graph: the publisher, the results as a Dataset, and this page as a Report."""
    links, date = model["links"], model["run"]["date"]
    dataset_id, report_id = SITE_URL + "#dataset", SITE_URL + "#report"
    publisher = {"@id": PUBLISHER["@id"]}
    based_on: dict[tuple[str, str | None], dict[str, str]] = {}
    for d in model["domains"]:
        for s in d["sources"]:
            work = {"@type": "CreativeWork", "name": s["name"]}
            if s.get("url"):
                work["url"] = s["url"]
            based_on.setdefault((s["name"], s.get("url")), work)
    dataset = {
        "@type": "Dataset",
        "@id": dataset_id,
        "name": f"{DATASET_NAME}, run {date}",
        "description": model["headline"],
        "url": SITE_URL,
        "creator": publisher,
        "publisher": publisher,
        "license": LICENSE_URL,
        "isAccessibleForFree": True,
        "dateModified": date,
        "keywords": [d["title"] for d in model["domains"]],
        "measurementTechnique": " ".join(page.METHOD[:2]),
        "variableMeasured": [
            {
                "@type": "PropertyValue",
                "name": f"{d['title']}, deviation in {s['unit']}",
                "unitText": s["unit"],
                "description": f"Deviation of the {d['unit_labels'].get(s['unit'], d['title'])} "
                f"from {d['authority']}. {page.UNIT_EXPLAIN[s['unit']]}",
            }
            for d in model["domains"]
            for s in d["summaries"]
        ],
        "distribution": [
            {"@type": "DataDownload", "encodingFormat": media, "contentUrl": links[key]}
            for key, _, media in page.DOWNLOADS
        ],
        "isBasedOn": list(based_on.values()),
    }
    report = {
        "@type": "Report",
        "@id": report_id,
        "headline": title(model),
        "description": model["description"],
        "url": SITE_URL,
        "inLanguage": "en",
        "dateModified": date,
        "image": IMAGE_URL,
        "author": publisher,
        "publisher": publisher,
        "about": {"@id": dataset_id},
        "isBasedOn": {"@id": dataset_id},
    }
    return {"@context": "https://schema.org", "@graph": [PUBLISHER, dataset, report]}


def head(model: Mapping[str, Any]) -> str:
    """Title, description, canonical, alternates, Open Graph and the JSON-LD block."""
    esc, links = page.esc, model["links"]
    meta = {
        "og:type": "article",
        "og:site_name": "RoxyAPI",
        "og:title": title(model),
        "og:description": model["description"],
        "og:url": SITE_URL,
        "og:image": IMAGE_URL,
    }
    graph = _inert(json.dumps(json_ld(model), ensure_ascii=False, separators=(",", ":")))
    return "\n".join(
        [
            f"<title>{esc(title(model))}</title>",
            f'<meta name="description" content="{esc(model["description"])}">',
            f'<link rel="canonical" href="{SITE_URL}">',
            *(
                f'<link rel="alternate" type="{media}" href="{esc(links[key])}" title="{name}">'
                for key, name, media in page.DOWNLOADS
            ),
            *(f'<meta property="{k}" content="{esc(v)}">' for k, v in meta.items()),
            '<meta name="twitter:card" content="summary_large_image">',
            f'<script type="application/ld+json">{graph}</script>',
        ]
    )


def render(template: str, model: Mapping[str, Any]) -> str:
    """Fill every slot of the template from the page model.

    Refuses a template without the data placeholder exactly once, or whose slots differ from
    the rendered fragments.
    """
    if template.count(PLACEHOLDER) != 1:
        raise SiteError(f"the template must hold {PLACEHOLDER} exactly once")
    values = {
        **page.sections(model),
        "HEAD": head(model),
        DATA_SLOT: _inert(
            json.dumps(script_data(model), ensure_ascii=False, separators=(",", ":"))
        ),
    }
    found = set(_SLOT.findall(template))
    if found != set(values):
        raise SiteError(
            f"template slots differ from the page: missing {sorted(set(values) - found)}, "
            f"unknown {sorted(found - set(values))}"
        )
    return _SLOT.sub(lambda m: values[m.group(1)], template)


def robots() -> str:
    return f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}{SITEMAP_FILE}\n"


def sitemap(date: str) -> str:
    """The page and the PDF report, both changed by the run of ``date``."""
    urls = "".join(
        f"  <url><loc>{xml_escape(url)}</loc><lastmod>{xml_escape(date)}</lastmod></url>\n"
        for url in (SITE_URL, SITE_URL + PDF_FILE)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )


def _inert(payload: str) -> str:
    return payload.translate(_HTML_SAFE)


def build(
    results_path: Path = RESULTS_DIR / JSON_FILE,
    template_path: Path = TEMPLATE_PATH,
    out_dir: Path = DIST_DIR,
    domains_dir: Path = DOMAINS_DIR,
) -> Path:
    """Write ``out_dir/index.html`` beside copies of the results it links for download, the
    robots file and the sitemap.

    Refuses a results format this version does not read.
    """
    model = report_data(read_results(results_path), domains_dir)
    html = render(template_path.read_text(encoding="utf-8"), model)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in (JSON_FILE, CSV_FILE):
        shutil.copyfile(results_path.with_name(name), out_dir / name)
    (out_dir / ROBOTS_FILE).write_text(robots(), encoding="utf-8")
    (out_dir / SITEMAP_FILE).write_text(sitemap(model["run"]["date"]), encoding="utf-8")
    path = out_dir / OUTPUT_FILE
    path.write_text(html, encoding="utf-8")
    return path
