"""Accuracy benchmark core: discovery, HTTP, schema, statistics and results.

A domain is a folder under ``domains/`` with a ``check.py``, a ``references.json`` and a
``pull.py``. The core never lists domains. A ``check.py`` imports what it needs from here.
"""

from benchmark.api import ApiClient, ApiError
from benchmark.schema import (
    Case,
    Chart,
    CrossCheck,
    Domain,
    Endpoint,
    Measurement,
    References,
    Source,
    Status,
    Tolerance,
    Unit,
)
from benchmark.stats import measure, measure_cases

__all__ = [
    "ApiClient",
    "ApiError",
    "Case",
    "Chart",
    "CrossCheck",
    "Domain",
    "Endpoint",
    "Measurement",
    "References",
    "Source",
    "Status",
    "Tolerance",
    "Unit",
    "measure",
    "measure_cases",
]
