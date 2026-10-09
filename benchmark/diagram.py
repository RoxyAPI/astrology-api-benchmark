"""The coverage map: which authority checks which domain, and which quantities it compares.

Built from the results domains and their ``references.json`` only, so a new domain folder joins the
map without a line of hand-written diagram. One Mermaid ``flowchart LR`` source is shared by the
README, the report page and the PDF.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

from benchmark.schema import References

NAMES_SHOWN = 3
"""Quantity names listed before the rest collapse into "and N more"."""

_ESCAPES = str.maketrans(
    {"#": "#35;", '"': "#quot;", "<": "#lt;", ">": "#gt;", "&": "#amp;", "`": "#96;", "\\": "#92;"}
)
_NUMBERED = re.compile(r"(.+?)[ _-]?\d+")


def escape(label: str) -> str:
    """A label safe inside a double quoted Mermaid node: markup and quote characters as entities."""
    return " ".join(label.translate(_ESCAPES).split())


def quantity_families(quantities: Sequence[str]) -> list[str]:
    """Collapse quantity names into short labels, in order of first appearance.

    ``Cusp 2`` and ``Cusp 3`` share the stem ``Cusp``; ``Sun nakshatra`` and ``Moon nakshatra``
    share the suffix when ``Sun`` and ``Moon`` are quantities too. Every other name is listed, and a
    long list keeps its first few names and the count of the rest.
    """
    known = set(quantities)
    grouped: dict[str, list[str]] = {}
    plain: list[str] = []
    for name in quantities:
        numbered = _NUMBERED.fullmatch(name)
        head, _, suffix = name.rpartition(" ")
        if numbered:
            grouped.setdefault(numbered.group(1), []).append(name)
        elif head in known:
            grouped.setdefault(suffix, []).append(name)
        else:
            plain.append(name)
            grouped.setdefault("", plain)
    return [_label(family, members) for family, members in grouped.items()]


def _label(family: str, members: Sequence[str]) -> str:
    if family:
        return f"{len(members)} {family} values" if len(members) > 1 else members[0]
    rest = len(members) - NAMES_SHOWN
    shown = members if rest < 2 else members[:NAMES_SHOWN]
    return ", ".join(shown) + (f" and {rest} more" if rest >= 2 else "")


def family_labels(ref: References) -> list[str]:
    """The declared family labels, else the labels collapsed from the quantity names."""
    if ref.families:
        return [f.label for f in ref.families]
    names = dict.fromkeys(q for case in ref.cases for q in case.expected)
    return quantity_families(list(names))


def coverage_map(domains: Iterable[Mapping[str, str]], refs: Mapping[str, References]) -> str:
    """The Mermaid source, authority to domain to quantity families, for each domain given.

    ``domains`` are results entries (``id`` and ``title``); ``refs`` holds their references.
    """
    authorities: dict[str, str] = {}
    nodes: list[str] = []
    edges: list[str] = []
    for i, domain in enumerate(domains):
        ref = refs[domain["id"]]
        nodes.append(f'd{i}("{escape(domain["title"])}")')
        for source in ref.sources:
            if source.name not in authorities:
                authorities[source.name] = f"a{len(authorities)}"
                nodes.append(f'{authorities[source.name]}["{escape(source.name)}"]')
            edge = f"{authorities[source.name]} --> d{i}"
            if edge not in edges:
                edges.append(edge)
        for j, label in enumerate(family_labels(ref)):
            nodes.append(f'q{i}_{j}["{escape(label)}"]')
            edges.append(f"d{i} --> q{i}_{j}")
    return "\n".join(["flowchart LR", *(f"  {line}" for line in (*nodes, *edges))])
