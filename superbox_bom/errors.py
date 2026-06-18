"""Error / flag types for the SuperBox engine.

The engine never fabricates a SKU. When a requested configuration falls
outside the merchandised SuperBox envelope it raises
``FactoryAssemblyRequired`` (a structured flag), which callers render as:

    REQUIRES FACTORY-ASSEMBLED neXT — contact ABB
    Reason: <specific reason>
"""

from __future__ import annotations

FACTORY_BANNER = "REQUIRES FACTORY-ASSEMBLED neXT — contact ABB"


class SuperBoxError(Exception):
    """Base class for all engine errors."""


class FactoryAssemblyRequired(SuperBoxError):
    """The config cannot be served by a merchandised SuperBox.

    Raised for every refuse-don't-fabricate case:
      - breaker/rating combo not present in breakers.json
      - 750 kcmil lugs requested
      - 100% rated breaker requested
      - required X-space exceeds the largest SuperBox for that ampacity
    (The ambiguous "fits multiple sizes" case is NOT an error — it is
    returned as a list of options so the caller can present a choice.)
    """

    def __init__(self, reason: str, *, detail: dict | None = None) -> None:
        self.reason = reason
        self.detail = detail or {}
        super().__init__(f"{FACTORY_BANNER} — {reason}")


class CatalogError(SuperBoxError):
    """A data file is missing, malformed, or references a TODO/unfilled cell."""
