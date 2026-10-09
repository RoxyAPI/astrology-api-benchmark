"""Capture the built report page: the README screenshot and the A4 PDF report.

``python -m benchmark.report --png assets/report.png --pdf dist/report.pdf`` after
``python -m benchmark site``. Needs the ``report`` dependency group and Chromium
(``playwright install chromium``); the core never imports this module.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from playwright.sync_api import Browser, FloatRect, Page, ViewportSize, sync_playwright
from pypdf import PdfWriter

from benchmark.paths import DIST_DIR
from benchmark.site import OUTPUT_FILE

AUTHOR = "RoxyAPI"
SCREEN: ViewportSize = {"width": 1280, "height": 900}
PRINT_WIDTH = 673
"""CSS pixels across the A4 content box (210 mm less two 16 mm margins), so charts lay out at
the printed width."""
READY = "body[data-ready]"
COVERAGE = "[data-coverage] svg"
SUMMARY = "#summary"


def open_page(browser: Browser, url: str, width: int, *, media: str = "screen") -> Page:
    """Load the page and wait for the webfonts, the charts and the Mermaid coverage map, so nothing
    renders half drawn."""
    page = browser.new_context(
        viewport={"width": width, "height": SCREEN["height"]},
        device_scale_factor=2,
        color_scheme="light",
    ).new_page()
    page.emulate_media(media="print" if media == "print" else "screen")
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(READY, state="attached")
    page.wait_for_selector(COVERAGE, state="attached")
    return page


def screenshot(browser: Browser, url: str, path: Path) -> None:
    """The header and the executive summary at desktop width: the scorecard a reader sees first."""
    page = open_page(browser, url, SCREEN["width"])
    box = page.locator(SUMMARY).bounding_box()
    if box is None:
        raise RuntimeError(f"{SUMMARY} is not on the page")
    clip: FloatRect = {
        "x": 0,
        "y": 0,
        "width": SCREEN["width"],
        "height": box["y"] + box["height"] + 24,
    }
    page.screenshot(path=path, full_page=True, clip=clip)


def pdf(browser: Browser, url: str, path: Path) -> None:
    """Print through the page print stylesheet, then stamp the document information."""
    page = open_page(browser, url, PRINT_WIDTH, media="print")
    title = page.title()
    subject = page.locator("meta[name=description]").get_attribute("content") or title
    page.pdf(path=path, prefer_css_page_size=True, print_background=True, outline=True, tagged=True)
    stamp(path, title=title, subject=subject)


def stamp(path: Path, *, title: str, subject: str) -> None:
    """Chromium writes only the title; a report also carries its author and subject."""
    writer = PdfWriter(clone_from=path)
    writer.add_metadata({"/Title": title, "/Author": AUTHOR, "/Subject": subject})
    writer.write(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmark.report", description=__doc__)
    parser.add_argument("--page", type=Path, default=DIST_DIR / OUTPUT_FILE, help="built page")
    parser.add_argument("--png", type=Path, help="write a full page screenshot here")
    parser.add_argument("--pdf", type=Path, help="write the PDF report here")
    args = parser.parse_args(argv)
    if not args.png and not args.pdf:
        parser.error("name --png, --pdf or both")
    if not args.page.is_file():
        parser.error(f"{args.page} is missing; run python -m benchmark site first")
    url = args.page.resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            if args.png:
                screenshot(browser, url, args.png)
            if args.pdf:
                pdf(browser, url, args.pdf)
        finally:
            browser.close()
    for out in (args.png, args.pdf):
        if out:
            print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
