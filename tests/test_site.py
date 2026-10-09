from __future__ import annotations

import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from benchmark.__main__ import main
from benchmark.claims import headline, labels, measured_deviation
from benchmark.domains import DomainError, references_for
from benchmark.page import esc
from benchmark.paths import RESULTS_DIR, TEMPLATE_PATH
from benchmark.results import CSV_FILE, JSON_FILE, ResultsError
from benchmark.schema import load_charts
from benchmark.site import (
    PDF_FILE,
    PLACEHOLDER,
    ROBOTS_FILE,
    SEARCH_CONSOLE_TOKEN,
    SITE_URL,
    SITEMAP_FILE,
    SiteError,
    build,
    render,
    report_data,
)

SCRIPT = re.compile(r'<script id="report-data" type="application/json">(.*?)</script>', re.DOTALL)
LD = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL)


class _Text(HTMLParser):
    """The text a reader without scripts sees: everything outside script, style and noscript."""

    HIDDEN = frozenset({"script", "style", "noscript"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.depth += tag in self.HIDDEN

    def handle_endtag(self, tag: str) -> None:
        self.depth -= tag in self.HIDDEN

    def handle_data(self, data: str) -> None:
        if not self.depth:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    parser.close()
    return " ".join(" ".join(parser.parts).split())


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    out = tmp_path_factory.mktemp("dist")
    return out, build(out_dir=out).read_text(encoding="utf-8")


def embedded(html: str) -> Any:
    match = SCRIPT.search(html)
    assert match is not None
    return json.loads(match.group(1))


def copy_results(tmp_path: Path) -> Path:
    for name in (JSON_FILE, CSV_FILE):
        shutil.copyfile(RESULTS_DIR / name, tmp_path / name)
    return tmp_path / JSON_FILE


def test_build_inlines_what_the_script_reads(built: tuple[Path, str]) -> None:
    out, html = built
    assert "__" + "REPORT_DATA" not in html
    data = embedded(html)
    committed = json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8"))
    assert data["run"] == committed["run"]
    assert [d["measurements"] for d in data["domains"]] == [
        d["measurements"] for d in committed["domains"]
    ]
    assert data["coverage"].startswith("flowchart LR")
    for name in (JSON_FILE, CSV_FILE):
        assert (out / name).read_bytes() == (RESULTS_DIR / name).read_bytes()


def test_page_reads_in_full_without_scripts(built: tuple[Path, str]) -> None:
    _, html = built
    text = visible_text(html)
    committed = json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8"))
    refs = references_for((d["id"] for d in committed["domains"]), load_charts())
    model = report_data(committed)
    assert len(text.split()) > 1500
    assert " ".join(headline(committed, labels(refs))) in text
    for domain in model["domains"]:
        assert domain["title"] in text and domain["authority"] in text
        for line in domain["quantity_lines"]:
            assert line in text
        for e in domain["endpoint_links"]:
            assert e["label"] in text and f'href="{e["url"]}"' in html
        for s in domain["summaries"]:
            assert f"{s['passed']:,} of {s['points']:,}" in text
        assert esc(measured_deviation(domain["summaries"])) in text
    assert any(
        line.startswith("RoxyAPI Chiron: ")
        for d in model["domains"]
        for line in d["quantity_lines"]
    )
    for name in (PDF_FILE, JSON_FILE, CSV_FILE):
        assert f'href="{SITE_URL}{name}"' in html


def test_head_carries_canonical_social_and_alternates(built: tuple[Path, str]) -> None:
    _, html = built
    head = html[: html.index("</head>")]
    assert f'<link rel="canonical" href="{SITE_URL}">' in head
    for media in ("application/pdf", "application/json", "text/csv"):
        assert f'<link rel="alternate" type="{media}"' in head
    assert f'<meta name="google-site-verification" content="{SEARCH_CONSOLE_TOKEN}">' in head
    assert SEARCH_CONSOLE_TOKEN == "bsKYP1JLQvbPmMzmkD64cDto9zCi2HzeRNNo4Cxthp4"
    for prop in ("og:title", "og:description", "og:type", "og:url", "og:image"):
        assert f'property="{prop}"' in head
    description = re.search(r'<meta name="description" content="([^"]*)">', head)
    assert description is not None and 0 < len(description.group(1)) < 160


def _urls(node: Any) -> list[str]:
    if isinstance(node, dict):
        return [u for k, v in node.items() for u in ([v] if k in URL_KEYS else _urls(v))]
    if isinstance(node, list):
        return [u for v in node for u in _urls(v)]
    return []


URL_KEYS = {"@id", "url", "logo", "license", "contentUrl", "image", "@context"}


def test_json_ld_describes_the_dataset_and_the_report(built: tuple[Path, str]) -> None:
    _, html = built
    match = LD.search(html)
    assert match is not None
    graph = json.loads(match.group(1))["@graph"]
    types = {node["@type"]: node for node in graph}
    dataset, report = types["Dataset"], types["Report"]
    committed = json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8"))
    assert dataset["dateModified"] == committed["run"]["date"]
    assert dataset["isAccessibleForFree"] is True
    assert {d["encodingFormat"] for d in dataset["distribution"]} == {
        "text/csv",
        "application/json",
        "application/pdf",
    }
    assert len(dataset["variableMeasured"]) == sum(
        len(d["summaries"]) for d in committed["domains"]
    )
    assert dataset["keywords"] == [d["title"] for d in committed["domains"]]
    assert dataset["isBasedOn"] and report["about"] == {"@id": dataset["@id"]}
    urls = _urls(graph)
    assert urls and all(isinstance(u, str) and u.startswith("https://") for u in urls)


def test_robots_and_sitemap_name_the_page(built: tuple[Path, str]) -> None:
    out, _ = built
    assert f"Sitemap: {SITE_URL}{SITEMAP_FILE}" in (out / ROBOTS_FILE).read_text(encoding="utf-8")
    sitemap = (out / SITEMAP_FILE).read_text(encoding="utf-8")
    date = json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8"))["run"]["date"]
    for url in (SITE_URL, SITE_URL + PDF_FILE):
        assert f"<loc>{url}</loc><lastmod>{date}</lastmod>" in sitemap


def _template(slots: str) -> str:
    return f'<script id="report-data" type="application/json">{PLACEHOLDER}</script>{slots}'


def test_render_escapes_every_value_and_keeps_data_inert() -> None:
    committed = json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8"))
    model = report_data(committed)
    hostile = "<b>x</b></script><!-- & -->"
    model["domains"][0]["title"] = hostile
    model["domains"][0]["measurements"][0]["note"] = hostile
    html = render(TEMPLATE_PATH.read_text(encoding="utf-8"), model)
    assert "<b>x</b>" not in html and "<!--" not in html
    assert hostile in visible_text(html)
    assert embedded(html)["domains"][0]["measurements"][0]["note"] == hostile
    graph = LD.search(html)
    assert graph is not None and json.loads(graph.group(1))


@pytest.mark.parametrize(
    "template",
    [
        "no placeholder",
        PLACEHOLDER + TEMPLATE_PATH.read_text(encoding="utf-8"),
        _template("__HEAD__"),
    ],
)
def test_render_refuses_a_template_that_does_not_fit(template: str) -> None:
    model = report_data(json.loads((RESULTS_DIR / JSON_FILE).read_text(encoding="utf-8")))
    with pytest.raises(SiteError):
        render(template, model)


def test_build_refuses_an_unknown_results_format(tmp_path: Path) -> None:
    results = copy_results(tmp_path)
    doc = json.loads(results.read_text(encoding="utf-8"))
    results.write_text(json.dumps({**doc, "format": 999}), encoding="utf-8")
    with pytest.raises(ResultsError):
        build(results, out_dir=tmp_path / "dist")
    assert main(["site", "--results", str(results), "--out", str(tmp_path / "dist")]) == 2


def test_build_refuses_a_result_without_its_domain_folder(tmp_path: Path) -> None:
    results = copy_results(tmp_path)
    doc = json.loads(results.read_text(encoding="utf-8"))
    doc["domains"][0]["id"] = "not-a-domain"
    results.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DomainError):
        build(results, out_dir=tmp_path / "dist")


def test_site_command_writes_the_page(tmp_path: Path) -> None:
    assert main(["site", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "index.html").is_file()
