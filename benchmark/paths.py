"""Repository locations the core reads and writes, resolved from this file so any cwd works."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOMAINS_DIR = ROOT / "domains"
DATA_DIR = ROOT / "data"
"""Shared inputs every domain may read, such as the subject corpus."""
CHARTS_PATH = DATA_DIR / "charts.csv"
RESULTS_DIR = ROOT / "results"
ENV_FILE = ROOT / ".env.local"
README_PATH = ROOT / "README.md"
TEMPLATE_PATH = ROOT / "site" / "template.html"
DIST_DIR = ROOT / "dist"
LOGO_PATH = ROOT / "assets" / "logo.png"
