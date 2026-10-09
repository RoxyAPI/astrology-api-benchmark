"""Typed contracts shared by the core and every domain, and the strict ``references.json`` loader.

Every object is a frozen dataclass. ``parse_references`` rejects unknown keys, unsourced values,
quantities without a tolerance and values whose type does not fit their unit, so an unsourced or
malformed reference file fails the test suite before it can reach a run.
"""

from __future__ import annotations

import csv
import math
import re
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, TypeGuard
from zoneinfo import ZoneInfo

from benchmark.paths import CHARTS_PATH

RESULT_FORMAT = 1
"""Version of ``results/latest.json``. Bump only on a breaking change; readers refuse others."""

REFERENCES_FORMAT = 1
"""Version of every ``domains/*/references.json``."""

ALL: Literal["*"] = "*"
"""Selector that matches every quantity of a domain."""

type Value = str | int | float | bool
"""A reference or measured value: a number, an ISO 8601 string or a discrete machine id."""

type Selector = tuple[str, ...] | Literal["*"]
"""The quantities a tolerance or a source applies to: named ones, or every one."""

HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CHART_COLUMNS = (
    "chart_id",
    "name",
    "date",
    "time",
    "latitude",
    "longitude",
    "timezone",
    "rodden_rating",
    "description",
)


class SchemaError(ValueError):
    """A reference file, chart row or domain declaration breaks the contract."""


class Unit(StrEnum):
    """How a quantity is compared. The deviation and the tolerance share the unit."""

    ARCSEC = "arcsec"
    """Angles. Values are decimal degrees; the deviation is the wrapped distance in arcseconds."""
    SECONDS = "seconds"
    """Instants. Values are ISO 8601 strings with an offset; the deviation is in seconds."""
    DAYS = "days"
    """Calendar counts. Values are numbers or ISO dates; the deviation is in days."""
    EXACT = "exact"
    """Discrete values. The deviation is 0 when equal, else 1; the tolerance is always 0."""


class Status(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One API operation a domain calls, as the OpenAPI spec of the API declares it."""

    method: str
    """Upper case HTTP method, for example ``POST``."""
    path: str
    """The spec path below the server base, ``{param}`` intact: ``/astrology/natal-chart``."""
    tag: str
    """The first OpenAPI tag of the operation: its section of the API reference."""

    def __post_init__(self) -> None:
        if self.method not in HTTP_METHODS:
            raise SchemaError(f"endpoint {self.path}: method must be one of {sorted(HTTP_METHODS)}")
        if not self.path.startswith("/"):
            raise SchemaError(f"endpoint {self.path!r}: path must start with /")
        if not self.tag.strip():
            raise SchemaError(f"endpoint {self.path}: tag must not be empty")


@dataclass(frozen=True, slots=True)
class Domain:
    """What a ``check.py`` declares as ``DOMAIN``. ``id`` equals its folder name."""

    id: str
    title: str
    authority: str
    """The named source a reader trusts for this domain, for the scorecard."""
    endpoints: tuple[Endpoint, ...]
    """The operations ``check()`` calls, checked against the live spec on every run."""
    order: int
    """Position in every listing: lower first."""

    def __post_init__(self) -> None:
        if not _SLUG.match(self.id):
            raise SchemaError(f"domain id {self.id!r} must be a lowercase slug")
        if not self.title.strip() or not self.authority.strip():
            raise SchemaError(f"domain {self.id}: title and authority must not be empty")
        if not self.endpoints or not all(isinstance(e, Endpoint) for e in self.endpoints):
            raise SchemaError(f"domain {self.id}: endpoints must be a non-empty tuple of Endpoint")


@dataclass(frozen=True, slots=True)
class Chart:
    """One row of ``data/charts.csv``, the shared subject corpus."""

    id: str
    name: str
    date: str
    time: str
    latitude: float
    longitude: float
    timezone: float | str
    """A decimal UTC offset in hours, or an IANA zone name."""
    rodden_rating: str
    description: str

    def utc(self) -> datetime:
        """Birth instant in UT: a zone name resolves with the default fold, a number is hours."""
        naive = datetime.strptime(f"{self.date} {self.time}", "%Y-%m-%d %H:%M:%S")
        zone: tzinfo = (
            ZoneInfo(self.timezone)
            if isinstance(self.timezone, str)
            else timezone(timedelta(seconds=int(self.timezone * 3600)))
        )
        return naive.replace(tzinfo=zone).astimezone(UTC)

    def request(self) -> dict[str, Any]:
        """The birth-data body most chart endpoints accept."""
        return {
            "date": self.date,
            "time": self.time,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "timezone": self.timezone,
        }


@dataclass(frozen=True, slots=True)
class Source:
    """Where a set of reference values comes from. Rendered into the README credits."""

    name: str
    retrieved: str
    """ISO date the values were pulled or the text was read."""
    licence: str
    method: str
    url: str | None = None
    command: str | None = None
    """The command in this repo that regenerates the values."""
    citation: str | None = None
    """Title, edition and page for a printed text."""
    notes: str | None = None
    applies_to: Selector = ALL

    def covers(self, quantity: str) -> bool:
        return covers(self.applies_to, quantity)


@dataclass(frozen=True, slots=True)
class Tolerance:
    """A vendor-neutral pass band for some quantities, with the reason for its size."""

    applies_to: Selector
    value: float
    unit: Unit
    why: str

    def covers(self, quantity: str) -> bool:
        return covers(self.applies_to, quantity)


@dataclass(frozen=True, slots=True)
class Case:
    """One subject: a chart from the corpus or an inline input, and its expected values."""

    id: str
    expected: Mapping[str, Value]
    chart: Chart | None = None
    input: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CrossCheck:
    """Values transcribed from a second source that the domain recomputation must reproduce."""

    source: str
    id: str
    expected: Mapping[str, Value]
    chart: Chart | None = None
    input: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Family:
    """A reader facing name for a group of quantities, shown in the coverage map and the cards."""

    label: str
    quantities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class References:
    """A parsed ``references.json``."""

    format: int
    domain: str
    sources: tuple[Source, ...]
    tolerances: tuple[Tolerance, ...]
    cases: tuple[Case, ...]
    cross_checks: tuple[CrossCheck, ...] = ()
    families: tuple[Family, ...] = ()
    """Optional: when present, every quantity of the cases sits in exactly one family."""

    def tolerance_for(self, quantity: str) -> Tolerance:
        """The tolerance naming a quantity, else the ``*`` one. Validation keeps names disjoint."""
        ranked = sorted(self.tolerances, key=lambda t: t.applies_to == ALL)
        for t in ranked:
            if t.covers(quantity):
                return t
        raise SchemaError(f"{self.domain}: no tolerance applies to {quantity!r}")


@dataclass(frozen=True, slots=True)
class Measurement:
    """One expected value compared with the value the API returned."""

    case: str
    quantity: str
    unit: Unit
    expected: Value
    actual: Value | None
    deviation: float | None
    """In ``unit``. None when the value is MISSING."""
    tolerance: float
    status: Status
    note: str = ""
    """Why a value is MISSING: an HTTP error, an absent field, an unreadable value."""


@dataclass(frozen=True, slots=True)
class Worst:
    case: str
    quantity: str
    deviation: float


@dataclass(frozen=True, slots=True)
class Tier:
    """How many points sit at or under ``limit``: a precision figure beside the pass band."""

    limit: float
    points: int


@dataclass(frozen=True, slots=True)
class Summary:
    """Statistics for one (domain, unit). Deviation figures cover measured points only."""

    domain: str
    unit: Unit
    points: int
    passed: int
    failed: int
    missing: int
    median: float | None
    mean: float | None
    p95: float | None
    max: float | None
    worst_case: Worst | None
    per_quantity_max: tuple[Worst, ...] = ()
    """Largest deviation per quantity, largest first."""
    tiers: tuple[Tier, ...] = ()
    """Precision tiers, loosest first, for angles and instants only. Results written before
    tiers existed carry none, so a reader treats the field as optional."""


def covers(selector: Selector, quantity: str) -> bool:
    return selector == ALL or quantity in selector


def load_charts(path: Path = CHARTS_PATH) -> dict[str, Chart]:
    """Read ``data/charts.csv`` keyed by chart id."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != _CHART_COLUMNS:
            raise SchemaError(f"{path.name}: header must be {','.join(_CHART_COLUMNS)}")
        charts: dict[str, Chart] = {}
        for row in reader:
            chart_id = row["chart_id"]
            if chart_id in charts:
                raise SchemaError(f"{path.name}: duplicate chart_id {chart_id!r}")
            charts[chart_id] = Chart(
                id=chart_id,
                name=row["name"],
                date=row["date"],
                time=row["time"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
                timezone=_parse_timezone(row["timezone"]),
                rodden_rating=row["rodden_rating"],
                description=row["description"],
            )
    return charts


def _parse_timezone(value: str) -> float | str:
    try:
        return float(value)
    except ValueError:
        return value


def parse_references(doc: object, domain_id: str, charts: Mapping[str, Chart]) -> References:
    """Validate a decoded ``references.json`` for ``domain_id`` and return it typed."""
    root = _object(
        doc,
        "references",
        required={"format", "domain", "sources", "tolerances", "cases"},
        optional={"cross_checks", "families"},
    )
    if root["format"] != REFERENCES_FORMAT:
        raise SchemaError(f"references: format must be {REFERENCES_FORMAT}")
    if root["domain"] != domain_id:
        raise SchemaError(f"references: domain must be {domain_id!r}, found {root['domain']!r}")

    sources = tuple(
        _source(s, f"sources[{i}]") for i, s in enumerate(_list(root["sources"], "sources"))
    )
    names = [s.name for s in sources]
    if len(set(names)) != len(names):
        raise SchemaError("sources: names must be unique")

    tolerances = tuple(
        _tolerance(t, f"tolerances[{i}]")
        for i, t in enumerate(_list(root["tolerances"], "tolerances"))
    )
    _check_tolerances_disjoint(tolerances)

    refs = References(
        format=REFERENCES_FORMAT,
        domain=domain_id,
        sources=sources,
        tolerances=tolerances,
        cases=tuple(
            Case(**_subject(c, f"cases[{i}]", charts))
            for i, c in enumerate(_list(root["cases"], "cases"))
        ),
        cross_checks=tuple(
            _cross_check(c, f"cross_checks[{i}]", charts, names)
            for i, c in enumerate(_list(root.get("cross_checks", []), "cross_checks", empty=True))
        ),
    )
    families = tuple(
        _family(f, f"families[{i}]")
        for i, f in enumerate(_list(root.get("families", []), "families", empty=True))
    )
    refs = replace(refs, families=families)
    _check_families(refs)
    _check_ids_unique([c.id for c in refs.cases], "cases")
    _check_ids_unique([c.id for c in refs.cross_checks], "cross_checks")
    for kind, subjects in (("cases", refs.cases), ("cross_checks", refs.cross_checks)):
        for subject in subjects:
            for quantity, value in subject.expected.items():
                where = f"{kind} {subject.id!r} {quantity!r}"
                tolerance = _resolve_tolerance(refs, quantity, where)
                if not any(s.covers(quantity) for s in sources):
                    raise SchemaError(f"{where}: no source covers this quantity")
                _check_value(tolerance.unit, value, where)
    return refs


_PLAIN_LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ,]*")


def _family(raw: object, where: str) -> Family:
    obj = _object(raw, where, required={"label", "quantities"})
    label = _text(obj["label"], f"{where}.label")
    if not _PLAIN_LABEL.fullmatch(label):
        raise SchemaError(f"{where}.label: plain prose only, letters, digits, spaces and commas")
    quantities = tuple(
        _text(q, f"{where}.quantities[{i}]")
        for i, q in enumerate(_list(obj["quantities"], f"{where}.quantities"))
    )
    return Family(label, quantities)


def _check_families(refs: References) -> None:
    if not refs.families:
        return
    known = {q for c in refs.cases for q in c.expected}
    seen: dict[str, str] = {}
    for family in refs.families:
        for q in family.quantities:
            if q not in known:
                raise SchemaError(f"families {family.label!r}: {q!r} is not a quantity of any case")
            if q in seen:
                raise SchemaError(f"families: {q!r} is in {seen[q]!r} and {family.label!r}")
            seen[q] = family.label
    if missing := known - seen.keys():
        raise SchemaError(f"families: no family holds {', '.join(sorted(missing))}")
    labels = [f.label for f in refs.families]
    if len(set(labels)) != len(labels):
        raise SchemaError("families: labels must be unique")


def _check_value(unit: Unit, value: object, where: str) -> None:
    """Raise unless ``value`` is a well formed reference value for ``unit``."""
    if unit is Unit.ARCSEC:
        if not is_number(value):
            raise SchemaError(f"{where}: an angle must be a number of degrees")
    elif unit is Unit.SECONDS:
        if not isinstance(value, str) or parse_instant(value) is None:
            raise SchemaError(f"{where}: an instant must be ISO 8601 with an offset")
    elif unit is Unit.DAYS:
        if not (is_number(value) or (isinstance(value, str) and parse_day(value) is not None)):
            raise SchemaError(f"{where}: a day value must be a number or an ISO date")
    elif not isinstance(value, str | int):
        raise SchemaError(f"{where}: an exact value must be a string, integer or boolean")


def parse_instant(value: str) -> datetime | None:
    """An ISO 8601 instant with an offset, else None. A naive time is ambiguous and refused."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def parse_day(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _object(
    value: object,
    where: str,
    *,
    required: AbstractSet[str],
    optional: AbstractSet[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SchemaError(f"{where}: expected an object")
    keys = set(value)
    if missing := required - keys:
        raise SchemaError(f"{where}: missing {', '.join(sorted(missing))}")
    if unknown := keys - required - optional:
        raise SchemaError(f"{where}: unknown {', '.join(sorted(unknown))}")
    return value


def _list(value: object, where: str, *, empty: bool = False) -> list[Any]:
    if not isinstance(value, list) or (not value and not empty):
        raise SchemaError(f"{where}: expected a {'' if empty else 'non-empty '}list")
    return value


def _text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{where}: expected a non-empty string")
    return value


def _optional_text(raw: Mapping[str, Any], key: str, where: str) -> str | None:
    return _text(raw[key], f"{where}.{key}") if key in raw else None


def _selector(value: object, where: str) -> Selector:
    if value == ALL:
        return ALL
    items = _list(value, where)
    return tuple(_text(q, f"{where}[{i}]") for i, q in enumerate(items))


def _source(value: object, where: str) -> Source:
    raw = _object(
        value,
        where,
        required={"name", "retrieved", "licence", "method"},
        optional={"url", "command", "citation", "notes", "applies_to"},
    )
    retrieved = _text(raw["retrieved"], f"{where}.retrieved")
    day = parse_day(retrieved)
    if day is None or len(retrieved) != 10:
        raise SchemaError(f"{where}.retrieved: expected YYYY-MM-DD")
    if day > date.today():
        raise SchemaError(f"{where}.retrieved: date is in the future")
    source = Source(
        name=_text(raw["name"], f"{where}.name"),
        retrieved=retrieved,
        licence=_text(raw["licence"], f"{where}.licence"),
        method=_text(raw["method"], f"{where}.method"),
        url=_optional_text(raw, "url", where),
        command=_optional_text(raw, "command", where),
        citation=_optional_text(raw, "citation", where),
        notes=_optional_text(raw, "notes", where),
        applies_to=_selector(raw["applies_to"], f"{where}.applies_to")
        if "applies_to" in raw
        else ALL,
    )
    if source.url is None and source.command is None and source.citation is None:
        raise SchemaError(f"{where}: needs a url, a command or a citation")
    if source.url is not None and not source.url.startswith("https://"):
        raise SchemaError(f"{where}.url: expected an https URL")
    return source


def _tolerance(value: object, where: str) -> Tolerance:
    raw = _object(value, where, required={"applies_to", "value", "unit", "why"})
    try:
        unit = Unit(raw["unit"])
    except ValueError:
        raise SchemaError(f"{where}.unit: expected one of {', '.join(Unit)}") from None
    band = raw["value"]
    if not is_number(band) or band < 0:
        raise SchemaError(f"{where}.value: expected a non-negative number")
    if unit is Unit.EXACT and band != 0:
        raise SchemaError(f"{where}.value: an exact tolerance is 0")
    return Tolerance(
        applies_to=_selector(raw["applies_to"], f"{where}.applies_to"),
        value=float(band),
        unit=unit,
        why=_text(raw["why"], f"{where}.why"),
    )


def _check_tolerances_disjoint(tolerances: tuple[Tolerance, ...]) -> None:
    if sum(t.applies_to == ALL for t in tolerances) > 1:
        raise SchemaError("tolerances: at most one applies to *")
    seen: set[str] = set()
    for t in tolerances:
        if t.applies_to == ALL:
            continue
        if overlap := seen & set(t.applies_to):
            raise SchemaError(f"tolerances: {', '.join(sorted(overlap))} named twice")
        seen |= set(t.applies_to)


def _resolve_tolerance(refs: References, quantity: str, where: str) -> Tolerance:
    try:
        return refs.tolerance_for(quantity)
    except SchemaError:
        raise SchemaError(f"{where}: no tolerance applies to this quantity") from None


def _subject(
    value: object, where: str, charts: Mapping[str, Chart], *, extra: frozenset[str] = frozenset()
) -> dict[str, Any]:
    raw = _object(value, where, required={"id", "expected"} | extra, optional={"chart", "input"})
    if ("chart" in raw) == ("input" in raw):
        raise SchemaError(f"{where}: name a chart or carry an input, not both or neither")
    chart = None
    if "chart" in raw:
        chart = charts.get(raw["chart"]) if isinstance(raw["chart"], str) else None
        if chart is None:
            raise SchemaError(f"{where}.chart: {raw['chart']!r} is not in data/charts.csv")
    return {
        "id": _text(raw["id"], f"{where}.id"),
        "expected": _mapping(raw["expected"], f"{where}.expected"),
        "chart": chart,
        "input": _mapping(raw["input"], f"{where}.input") if "input" in raw else None,
    }


def _mapping(value: object, where: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or not value:
        raise SchemaError(f"{where}: expected a non-empty object")
    return MappingProxyType(dict(value))


def _cross_check(
    value: object, where: str, charts: Mapping[str, Chart], source_names: list[str]
) -> CrossCheck:
    fields = _subject(value, where, charts, extra=frozenset({"source"}))
    source = value["source"] if isinstance(value, dict) else None
    if source not in source_names:
        raise SchemaError(f"{where}.source: {source!r} is not a name in sources")
    return CrossCheck(source=source, **fields)


def _check_ids_unique(ids: list[str], where: str) -> None:
    if len(set(ids)) != len(ids):
        raise SchemaError(f"{where}: ids must be unique")
