"""Catalog loader: reads the three JSON data files and exposes typed accessors.

I/O lives HERE (file loading). The engine (engine.py) is pure and operates on a
loaded Catalog instance, so all the correctness logic is testable without disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import CatalogError

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_INT_LETTERS = {"N", "S", "H", "L", "V", "D", "A"}


def _strip_meta(obj: dict) -> dict:
    """Drop documentation keys (anything starting with '_' or named TODO-ish)."""
    return {k: v for k, v in obj.items() if not k.startswith("_")}


class Catalog:
    """In-memory view of breakers.json + xspace.json + superbox.json."""

    def __init__(self, breakers: dict, xspace: dict, superbox: dict, accessories: dict | None = None):
        self._breakers = breakers["breakers"]
        self._xspace = xspace
        self._superbox = superbox
        self._accessories = accessories or {}
        self.skus = superbox["skus"]

    # ----- loading -------------------------------------------------------
    @classmethod
    def load(cls, data_dir: str | Path | None = None) -> "Catalog":
        d = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        try:
            breakers = json.loads((d / "breakers.json").read_text(encoding="utf-8"))
            xspace = json.loads((d / "xspace.json").read_text(encoding="utf-8"))
            superbox = json.loads((d / "superbox.json").read_text(encoding="utf-8"))
        except FileNotFoundError as e:
            raise CatalogError(f"data file not found: {e.filename}") from e
        except json.JSONDecodeError as e:
            raise CatalogError(f"invalid JSON in data files: {e}") from e
        # accessories.json is optional
        accessories = None
        acc_path = d / "accessories.json"
        if acc_path.exists():
            try:
                accessories = json.loads(acc_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                raise CatalogError(f"invalid JSON in accessories.json: {e}") from e
        return cls(breakers, xspace, superbox, accessories)

    # ----- breaker lookup ------------------------------------------------
    @staticmethod
    def _match_int_rating(row: dict, req: Any) -> bool:
        if req is None:
            return True
        s = str(req).strip().upper()
        if s in _INT_LETTERS:
            return str(row.get("int_rating", "")).upper() == s
        digits = "".join(ch for ch in s if ch.isdigit())
        if digits:
            return row.get("int_rating_kA") == int(digits)
        return False

    def find_breakers(
        self,
        frame: str,
        poles: int,
        amps: int,
        int_rating: Any = None,
        trip_unit: str | None = None,
        load_lug: str | None = None,
        phase: str | None = None,
    ) -> list[dict]:
        """Return all catalog rows matching the given constraints (may be >1)."""
        out = []
        for row in self._breakers:
            if str(row["frame"]).upper() != str(frame).upper():
                continue
            if int(row["poles"]) != int(poles):
                continue
            if int(row["amps"]) != int(amps):
                continue
            if not self._match_int_rating(row, int_rating):
                continue
            if trip_unit and trip_unit.strip().lower() != str(row.get("trip_unit", "")).strip().lower():
                continue
            if load_lug and load_lug.replace(" ", "") not in str(row.get("load_lug", "")).replace(" ", ""):
                continue
            if phase and "phase" in row and str(phase).upper() != str(row["phase"]).upper():
                continue
            out.append(row)
        return out

    # ----- X-space accessors --------------------------------------------
    def frame_xspace(self, frame: str, poles: int) -> int:
        table = self._xspace["frame_xspace"].get(frame.upper())
        if table is None:
            raise CatalogError(f"no X-space entry for frame {frame!r} (transcribe it in xspace.json)")
        val = table.get(str(poles))
        if val is None:
            raise CatalogError(
                f"X-space for {frame} {poles}-pole is not transcribed yet (TODO in xspace.json)"
            )
        return int(val)

    @property
    def main_lug_pad_xspace(self) -> int:
        return int(self._xspace["main_lug_pad_xspace"])

    @property
    def xt5_accessory_extra(self) -> int:
        return int(self._xspace["xt5_accessory_extra"])

    def accessory_xspace(self, name: str) -> int:
        table = _strip_meta(self._xspace["accessory_xspace"])
        if name.upper() not in {k.upper() for k in table}:
            raise CatalogError(f"no X-space entry for accessory {name!r}")
        for k, v in table.items():
            if k.upper() == name.upper():
                return int(v)
        raise CatalogError(name)  # unreachable

    # ----- XT1 grouping + rails -----------------------------------------
    @property
    def xt1_group_xspace(self) -> dict[int, int]:
        return {int(k): int(v) for k, v in self._xspace["xt1_grouping"]["groups"].items()}

    @property
    def xt1_bin_order(self) -> list[int]:
        return [int(x) for x in self._xspace["xt1_grouping"]["bin_order"]]

    def xt1_rail(self, group_size: int, family: str) -> str:
        rails = self._xspace["xt1_rails"]
        if family not in rails:
            raise CatalogError(f"unknown XT1 rail family {family!r}")
        sku = rails[family].get(str(group_size))
        if not sku:
            raise CatalogError(f"no XT1 rail for group size {group_size} in family {family}")
        return sku

    # ----- SuperBox / wire-bend -----------------------------------------
    # ----- options export (for the web UI dropdowns) ---------------------
    def export_options(self) -> dict:
        """Everything the UI needs to drive cascading dropdowns from real data."""
        return {
            "breakers": self._breakers,
            "skus": self.skus,
            "frames": sorted({r["frame"] for r in self._breakers}),
            "main_types": sorted({s["main_type"] for s in self.skus}),
            "enclosures": sorted({s["enclosure"] for s in self.skus}),
            "panel_amps": sorted({s["amps"] for s in self.skus}),
            "accessories": {k: v for k, v in self._accessories.items() if not k.startswith("_")},
        }

    # ----- accessories ---------------------------------------------------
    def find_accessories(self, category: str, frame: str | None = None, **keys) -> list[dict]:
        """Return accessory records in `category` matching frame + selection keys.

        A record applies to a frame if its 'frame' equals it or its 'frames'
        list contains it (records with neither are frame-agnostic, e.g. SPD).
        Only keys present on a record are compared; a key whose record value is
        null (e.g. merged-cell shunt-trip voltage) is treated as a wildcard.
        """
        if category not in self._accessories:
            raise CatalogError(
                f"accessory category {category!r} not in accessories.json"
                if self._accessories else "accessories.json not loaded"
            )
        out = []
        for rec in self._accessories[category]:
            if frame is not None and ("frame" in rec or "frames" in rec):
                applies = (str(rec.get("frame", "")).upper() == frame.upper()
                           or frame.upper() in {f.upper() for f in rec.get("frames", [])})
                if not applies:
                    continue
            ok = True
            for k, v in keys.items():
                if v is None:
                    continue
                if k in rec and rec[k] is not None and str(rec[k]).upper() != str(v).upper():
                    ok = False
                    break
            if ok:
                out.append(rec)
        return out

    def left_only_frames(self, offset_class: str) -> set[str]:
        """Frames that may mount only on the LEFT side for this enclosure.

        Derived from the wire-bend table: a frame is left-only iff its
        right-mount dimension is null ('—' in the BuyLog). Single source of
        truth, so the rule cannot drift from the published inch values.
        """
        wb = self._superbox["wire_bend"].get(offset_class)
        if not wb:
            raise CatalogError(f"unknown offset_class {offset_class!r} in superbox.json wire_bend")
        frames = wb.get("frames")
        if frames is None:  # legacy explicit list, if a data file predates the table
            return {f.upper() for f in wb.get("left_only", [])}
        return {name.upper() for name, v in frames.items() if v.get("right_in") is None}
