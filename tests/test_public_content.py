"""Public-content guard: every committed byte of this repository is public.

Scans the prose of every tracked or new file: markdown and citation metadata in full (code
excluded), the comments and docstrings of Python, YAML and TOML, and the visible text, readable
attributes and inline scripts of HTML, and the built report page, whose sentences are generated
by Python. Other code and JSON strings are not prose and are not scanned. An inline script is
scanned whole, so its strings use double quotes or backticks.
"""

from __future__ import annotations

import ast
import io
import re
import subprocess
import tokenize
from collections.abc import Iterator
from html.parser import HTMLParser
from pathlib import Path

import pytest

from benchmark.paths import ROOT
from benchmark.site import build

RULES: dict[str, re.Pattern[str]] = {
    "apostrophe": re.compile("['\u2018\u2019\u02bc]"),
    "em dash": re.compile("\u2014"),
    "double hyphen as a dash": re.compile(r"\s--\s"),
    "date beside a verification verb": re.compile(
        r"\b(?:verified|checked|confirmed|validated)\s+(?:on|in)\s+(?:19|20)\d\d"
        r"|\bas of (?:19|20)\d\d",
        re.IGNORECASE,
    ),
}

type Line = tuple[int, str]


def tracked_files() -> list[Path]:
    """Tracked files plus new ones git would add, so the guard runs before the first commit."""
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [ROOT / name for name in out.split("\0") if name and (ROOT / name).is_file()]


def prose(path: Path) -> list[Line]:
    text = path.read_text(encoding="utf-8")
    match path.suffix:
        case ".md":
            return list(_markdown(text))
        case ".cff":
            return list(enumerate(text.splitlines(), 1))
        case ".py":
            return sorted(_python(text))
        case ".yml" | ".yaml" | ".toml":
            return list(_hash_comments(text))
        case ".html":
            return _html(text)
        case _:
            return []


def violations(lines: list[Line]) -> list[str]:
    return [
        f"{number}: {name}: {line.strip()}"
        for number, line in lines
        for name, rule in RULES.items()
        if rule.search(line)
    ]


def _markdown(text: str) -> Iterator[Line]:
    fenced = False
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced:
            yield number, re.sub(r"`[^`]*`", "", line)


def _python(text: str) -> Iterator[Line]:
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            yield token.start[0], token.string
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for offset, line in enumerate(node.value.value.splitlines()):
                yield node.lineno + offset, line


def _hash_comments(text: str) -> Iterator[Line]:
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("#"):
            yield number, line
        elif " #" in line:
            yield number, line.split(" #", 1)[1]


class _Visible(HTMLParser):
    """Collects what a reader or a script can show: text, readable attributes, inline scripts."""

    ATTRIBUTES = frozenset({"alt", "title", "aria-label", "content", "placeholder"})
    SKIPPED = frozenset({"style", "application/json", "application/ld+json"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[Line] = []
        self.skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        self.skip = tag == "style" or (tag == "script" and values.get("type") in self.SKIPPED)
        line = self.getpos()[0]
        self.lines += [(line, v) for k, v in attrs if k in self.ATTRIBUTES and v]

    def handle_endtag(self, tag: str) -> None:
        self.skip = False

    def handle_data(self, data: str) -> None:
        if not self.skip:
            first = self.getpos()[0]
            self.lines += [(first + i, line) for i, line in enumerate(data.splitlines())]


def _html(text: str) -> list[Line]:
    parser = _Visible()
    parser.feed(text)
    parser.close()
    return sorted(parser.lines)


SUFFIXES = {".md", ".cff", ".py", ".yml", ".yaml", ".toml", ".html"}
FILES = [p for p in tracked_files() if p.suffix in SUFFIXES]


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_public_prose(path: Path) -> None:
    found = violations(prose(path))
    assert not found, "\n".join(found)


def test_built_page_prose(tmp_path: Path) -> None:
    """The generated sentences, tables and head of the report page, which no tracked file holds."""
    found = violations(_html(build(out_dir=tmp_path).read_text(encoding="utf-8")))
    assert not found, "\n".join(found)


@pytest.mark.parametrize(
    ("line", "rule"),
    [
        ("the chart\u2019s time", "apostrophe"),
        ("the chart's time", "apostrophe"),
        ("4 Ajaw in K\u02bcan orthography", "apostrophe"),
        ("one \u2014 two", "em dash"),
        ("one -- two", "double hyphen as a dash"),
        ("Verified on 2026-10-09", "date beside a verification verb"),
        ("as of 2026, the median", "date beside a verification verb"),
    ],
)
def test_guard_catches_each_rule(line: str, rule: str) -> None:
    assert violations([(1, line)]) == [f"1: {rule}: {line}"]


def test_code_and_fenced_blocks_are_not_prose() -> None:
    markdown = "Run `it's` here.\n```\necho it's -- fine\n```\nPlain prose.\n"
    assert violations(list(_markdown(markdown))) == []
    source = 'x = "it\'s code"  # a clean comment\n'
    assert violations(sorted(_python(source))) == []
    assert violations(sorted(_python("# the chart's time\n"))) != []
    assert violations(sorted(_python('"""The chart\'s time."""\n'))) != []


def test_html_scans_visible_text_attributes_and_scripts_only() -> None:
    page = (
        "<style>a::after { content: 'x'; }</style>"
        '<script type="application/json">{"note": "it\'s data"}</script>'
        '<p title="clean">Plain text.</p>'
    )
    assert violations(_html(page)) == []
    assert violations(_html("<p>the chart\u2019s time</p>")) != []
    assert violations(_html('<img alt="the chart\'s time">')) != []
    assert violations(_html("<script>const s = 'it';</script>")) != []
