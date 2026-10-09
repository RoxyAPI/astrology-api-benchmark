"""Discovery: every ``domains/{id}/check.py`` is a domain. The core never lists domains.

A domain folder holds ``check.py`` (exports ``DOMAIN`` and ``check``), ``references.json``
and ``pull.py`` (exports ``pull``). Adding a domain is adding the folder.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from benchmark.api import ApiClient
from benchmark.paths import DOMAINS_DIR
from benchmark.schema import Chart, Domain, Measurement, References, SchemaError, parse_references

type Check = Callable[[ApiClient, References], list[Measurement]]
"""``check(api, refs)``: call the API for every case and return one Measurement per value."""

type Pull = Callable[[], dict[str, Any]]
"""``pull()``: rebuild the references document from its source; the core validates and writes."""

CHECK_FILE = "check.py"
REFERENCES_FILE = "references.json"
PULL_FILE = "pull.py"


class DomainError(Exception):
    """A domain folder breaks the discovery contract."""


@dataclass(frozen=True, slots=True)
class LoadedDomain:
    domain: Domain
    check: Check
    references: References
    path: Path


def discover(charts: Mapping[str, Chart], root: Path = DOMAINS_DIR) -> list[LoadedDomain]:
    """Load every domain under ``root``, ordered by ``Domain.order`` then id."""
    if not root.is_dir():
        return []
    loaded = [load(folder, charts) for folder in sorted(root.iterdir()) if _is_domain(folder)]
    return sorted(loaded, key=lambda d: (d.domain.order, d.domain.id))


def load(folder: Path, charts: Mapping[str, Chart]) -> LoadedDomain:
    """Import ``check.py``, validate its exports against the folder and parse the references."""
    module = load_module(folder, CHECK_FILE)
    domain = getattr(module, "DOMAIN", None)
    check = getattr(module, "check", None)
    if not isinstance(domain, Domain) or not callable(check):
        raise DomainError(f"{folder.name}/{CHECK_FILE}: must export DOMAIN (a Domain) and check()")
    if domain.id != folder.name:
        raise DomainError(f"{folder.name}: DOMAIN.id {domain.id!r} must equal the folder name")
    return LoadedDomain(domain, check, read_references(folder, charts), folder)


def read_references(folder: Path, charts: Mapping[str, Chart]) -> References:
    path = folder / REFERENCES_FILE
    if not path.is_file():
        raise DomainError(f"{folder.name}: {REFERENCES_FILE} is missing")
    try:
        return parse_references(json.loads(path.read_text(encoding="utf-8")), folder.name, charts)
    except (json.JSONDecodeError, SchemaError) as e:
        raise DomainError(f"{folder.name}/{REFERENCES_FILE}: {e}") from None


def references_for(
    ids: Iterable[str], charts: Mapping[str, Chart], root: Path = DOMAINS_DIR
) -> dict[str, References]:
    """The references of each domain a results file names, refusing one with no folder."""
    refs: dict[str, References] = {}
    for domain_id in ids:
        folder = root / domain_id
        if not folder.is_dir():
            raise DomainError(f"{domain_id}: in the results but not under {root.name}/")
        refs[domain_id] = read_references(folder, charts)
    return refs


def write_references(folder: Path, doc: dict[str, Any], charts: Mapping[str, Chart]) -> Path:
    """Validate a pulled document, then write it in the one committed layout."""
    try:
        parse_references(doc, folder.name, charts)
    except SchemaError as e:
        raise DomainError(f"{folder.name}: pulled references are invalid: {e}") from None
    path = folder / REFERENCES_FILE
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_pull(folder: Path) -> Pull:
    module = load_module(folder, PULL_FILE)
    pull: Pull | None = getattr(module, "pull", None)
    if not callable(pull):
        raise DomainError(f"{folder.name}/{PULL_FILE}: must export pull()")
    return pull


def _is_domain(folder: Path) -> bool:
    """A folder with any tracked content must carry a check.py; an empty one is skipped."""
    if not folder.is_dir() or folder.name.startswith((".", "_")):
        return False
    if (folder / CHECK_FILE).is_file():
        return True
    if any(p.name != "__pycache__" for p in folder.iterdir()):
        raise DomainError(f"{folder.name}: a domain folder needs {CHECK_FILE}")
    return False


def load_module(folder: Path, filename: str) -> ModuleType:
    """Import ``filename`` from a domain folder as a module of its own."""
    path = folder / filename
    if not path.is_file():
        raise DomainError(f"{folder.name}: {filename} is missing")
    name = f"domain_{folder.name.replace('-', '_')}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise DomainError(f"{folder.name}: cannot import {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
