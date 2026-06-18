"""SuperBox BOM engine — pure functions, no I/O.

Every function takes an already-loaded ``Catalog`` and plain spec dataclasses and
returns plain data. The hard correctness rules from BuyLog Section 11 live here;
each function's docstring names the rule it enforces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .catalog import Catalog
from .errors import CatalogError, FactoryAssemblyRequired

# --------------------------------------------------------------------------
# Spec dataclasses (the parsed user request)
# --------------------------------------------------------------------------


@dataclass
class Breaker:
    frame: str
    poles: int
    amps: int
    int_rating: Any = None          # letter ("H") or kA (65) — both accepted
    qty: int = 1
    trip_unit: Optional[str] = None
    load_lug: Optional[str] = None
    phase: Optional[str] = None      # A|B|C|AB|AC|BC — for 1/2-pole TEY/FB/A2
    elec_accessory: bool = False    # XT5 +1X rule (#4)
    rated_100pct: bool = False      # → factory-assembled refuse
    orientation: str = "horizontal"  # main only: 'horizontal' | 'vertical'
    lug_pad_sets: int = 1           # MLO main only
    accessories: list = field(default_factory=list)  # breaker-mounted: aux/shunt/uvr/padlock/seb


@dataclass
class Spec:
    panel_amps: int
    main_type: str                  # 'MLO' | 'MCB' | 'MCB-GF'
    enclosure: str                  # 'NEMA1' | 'NEMA3R'
    main: Optional[Breaker] = None  # required if MCB/MCB-GF
    branches: list[Breaker] = field(default_factory=list)
    accessories: list[dict] = field(default_factory=list)  # [{type, qty}]
    voltage: Optional[str] = None   # e.g. "208Y/120V" (drawing only)
    system: Optional[str] = None    # e.g. "3Ø, 4-wire" (drawing only)


# --------------------------------------------------------------------------
# Internal item model used for packing
# --------------------------------------------------------------------------


@dataclass
class XItem:
    """One indivisible block of X-space to place in the panel."""
    label: str
    xspace: int
    frame: str
    side: str = "flexible"  # 'left' (forced) | 'flexible'


# --------------------------------------------------------------------------
# 1. resolve_breaker
# --------------------------------------------------------------------------


def _requests_750(load_lug: Optional[str]) -> bool:
    return bool(load_lug) and "750" in str(load_lug)


def resolve_breaker(item: Breaker, catalog: Catalog) -> dict:
    """Resolve one breaker to its ordering code, or refuse.

    Enforces the refuse-don't-fabricate posture: a 100%-rated request, a
    750 kcmil lug request, or a frame/pole/amp/rating combo that is not in
    breakers.json all raise FactoryAssemblyRequired rather than inventing a SKU.
    """
    if item.rated_100pct:
        raise FactoryAssemblyRequired(
            "100% rated breaker requested (catalog breakers are 80% rated)",
            detail={"breaker": _bk_label(item)},
        )
    if _requests_750(item.load_lug):
        raise FactoryAssemblyRequired(
            "750 kcmil lugs requested",
            detail={"breaker": _bk_label(item)},
        )

    matches = catalog.find_breakers(
        item.frame, item.poles, item.amps, item.int_rating,
        item.trip_unit, item.load_lug, item.phase,
    )
    if not matches:
        raise FactoryAssemblyRequired(
            f"breaker not in catalog: {_bk_label(item)}",
            detail={"breaker": _bk_label(item)},
        )
    if len(matches) > 1:
        codes = [m["ordering_code"] for m in matches]
        raise CatalogError(
            f"ambiguous breaker match for {_bk_label(item)}; "
            f"specify trip_unit/load_lug to disambiguate. Candidates: {codes}"
        )
    return matches[0]


def _bk_label(b: Breaker) -> str:
    r = b.int_rating if b.int_rating is not None else "?"
    return f"{b.frame} {b.poles}P {b.amps}A {r}"


# --------------------------------------------------------------------------
# Accessories (Step 2, pp.11-61/62)
# --------------------------------------------------------------------------

# accessory kinds that are electrical (trigger XT5 +1X, rule #4)
_ELECTRICAL_KINDS = {"aux_contacts", "shunt_trip", "undervoltage_release"}
# breaker-mounted accessory kind -> the selection keys to match (besides frame)
_BREAKER_ACC_KEYS = {
    "aux_contacts": ("type", "volts"),
    "shunt_trip": ("volts",),
    "undervoltage_release": ("volts",),
    "padlock": ("style",),
    "service_entrance_barrier": ("variant",),
}
# panel-level accessory kind -> (category, selection keys)
_PANEL_ACC_KEYS = {
    "spd": ("spd", ("voltage", "ka")),
    "rgm40": ("rgm40", ("function", "protocol", "voltage")),
    "blank": ("blank", ("width", "filler")),
    "relt": ("relt", ("type", "volts")),
}


def _breaker_has_electrical(b: Breaker) -> bool:
    """True if the breaker carries an aux/shunt/UVR accessory (rule #4 trigger)."""
    return any(a.get("kind") in _ELECTRICAL_KINDS for a in b.accessories)


def resolve_breaker_accessory(acc: dict, frame: str, catalog: Catalog) -> dict:
    """Resolve one breaker-mounted accessory to its ordering code (or raise).

    Looks up accessories.json by the breaker's frame + the accessory's keys.
    A missing/ambiguous match raises CatalogError (no fabrication).
    """
    kind = acc.get("kind")
    if kind not in _BREAKER_ACC_KEYS:
        raise CatalogError(f"unknown breaker accessory kind {kind!r}")
    keys = {k: acc.get(k) for k in _BREAKER_ACC_KEYS[kind]}
    matches = catalog.find_accessories(kind, frame=frame, **keys)
    if not matches:
        raise CatalogError(f"no {kind} accessory for {frame} with {keys} in accessories.json")
    if len(matches) > 1:
        raise CatalogError(
            f"ambiguous {kind} for {frame}: specify {_BREAKER_ACC_KEYS[kind]}. "
            f"Candidates: {[m['code'] for m in matches]}"
        )
    return matches[0]


def resolve_panel_accessory(acc: dict, catalog: Catalog) -> dict:
    """Resolve one panel-level plug-in (spd/rgm40/blank/relt) → code + x_space."""
    kind = acc.get("kind")
    if kind not in _PANEL_ACC_KEYS:
        raise CatalogError(f"unknown panel accessory kind {kind!r}")
    category, key_names = _PANEL_ACC_KEYS[kind]
    keys = {k: acc.get(k) for k in key_names}
    frame = acc.get("frame")  # relt is XT7-specific; others frame-agnostic
    matches = catalog.find_accessories(category, frame=frame, **keys)
    if not matches:
        raise CatalogError(f"no {kind} accessory matching {keys} in accessories.json")
    if len(matches) > 1:
        raise CatalogError(
            f"ambiguous {kind}: specify {key_names}. Candidates: {[m['code'] for m in matches]}"
        )
    rec = matches[0]
    return {
        "kind": kind,
        "code": rec["code"],
        "x_space": int(rec.get("x_space", 0)),
        "page": rec.get("page", ""),
        "record": rec,
    }


# --------------------------------------------------------------------------
# 2. group_xt1  (highest-risk rule)
# --------------------------------------------------------------------------


def group_xt1(n: int, catalog: Catalog, rail_family: str | None = None) -> dict:
    """Bin N XT1 breakers into groups of 5/2/1 to MINIMIZE total X-space.

    Rule (p.11-62/63): X-space is non-linear — 1×XT1=3X, 2×XT1=5X, 5×XT1=11X.
    Because the 5-group is the most space-efficient (2.2X/breaker) and the
    2-group (2.5X) beats singles (3X), greedily filling [5, 2, 1] is optimal.
    e.g. 7 → [5, 2] (16X), NOT [5, 1, 1] (17X).

    Each emitted group needs its own mounting-rail SKU (NOT included in the
    SuperBox) — a separate BOM line. Rail SKU depends on the box's orientation
    family (rail_family); pass it to get the rails, or omit for grouping only.
    """
    if n < 0:
        raise ValueError("XT1 count cannot be negative")
    group_x = catalog.xt1_group_xspace  # {1:3, 2:5, 5:11}
    groups: list[int] = []
    remaining = n
    for size in catalog.xt1_bin_order:  # [5, 2, 1]
        while remaining >= size:
            groups.append(size)
            remaining -= size
    if remaining:  # only possible if bin_order lacks a 1; guard anyway
        raise CatalogError(f"cannot bin {n} XT1 breakers with order {catalog.xt1_bin_order}")

    total_x = sum(group_x[g] for g in groups)
    result = {"count": n, "groups": groups, "total_xspace": total_x, "rails": []}
    if rail_family is not None:
        result["rails"] = [catalog.xt1_rail(g, rail_family) for g in groups]
    return result


# --------------------------------------------------------------------------
# 3 & 4. frame_xspace
# --------------------------------------------------------------------------


def frame_xspace(frame: str, poles: int, catalog: Catalog, has_elec_accessory: bool = False) -> int:
    """X-space for ONE non-XT1 breaker.

    Enforces rule #4: an XT5 carrying electrical accessories needs +1X
    (p.11-62 footnote). XT1 is never sized here — it is grouped via group_xt1.
    """
    base = catalog.frame_xspace(frame, poles)
    if frame.upper() == "XT5" and has_elec_accessory:
        base += catalog.xt5_accessory_extra
    return base


# --------------------------------------------------------------------------
# main_xspace
# --------------------------------------------------------------------------


def main_xspace(spec: Spec, catalog: Catalog) -> int:
    """X-space consumed by the main, charged against the published box capacity.

    The Step 4 left/right X-space columns (p.11-64) are the panel's USABLE
    capacity as-published, so:

    - MLO: 0. The main lugs are already netted out of the published MLO value
      (MLO boxes show exactly 4X less per side than the identical MCB box).
    - MCB / MCB-GF: only the selected main breaker's own frame X-space
      (Step 4 footnote 1 — "X-space required for main breaker must be accounted
      for based on specific breaker selected"). No separate lug-pad add.
    """
    if spec.main_type == "MLO":
        return 0
    if spec.main is None:
        raise CatalogError("MCB main_type requires a main_breaker spec")
    has_elec = spec.main.elec_accessory or _breaker_has_electrical(spec.main)
    return frame_xspace(spec.main.frame, spec.main.poles, catalog, has_elec)


# --------------------------------------------------------------------------
# 5. partition loadout into placeable X-items (left-forced vs flexible)
# --------------------------------------------------------------------------


def partition_loadout(spec: Spec, catalog: Catalog, left_only: set[str]) -> dict:
    """Build the list of XItems and split into left-forced vs flexible.

    XT5/XT6/XT7 (and XT4 in 45" boxes) are forced LEFT (rule #2). The main is
    always charged to the left. XT1 breakers are grouped (rule #1) into
    indivisible group-items that may mount either side.
    """
    left_items: list[XItem] = []
    flex_items: list[XItem] = []

    # --- main (always left) ---
    mx = main_xspace(spec, catalog)
    if mx:
        main_lbl = "Main lugs" if spec.main_type == "MLO" else f"Main breaker {_bk_label(spec.main)}"
        left_items.append(XItem(label=main_lbl, xspace=mx, frame=(spec.main.frame if spec.main else "MLO"), side="left"))

    # --- branches ---
    xt1_total = 0
    for b in spec.branches:
        if b.frame.upper() == "XT1":
            xt1_total += b.qty
            continue
        has_elec = b.elec_accessory or _breaker_has_electrical(b)
        fx = frame_xspace(b.frame, b.poles, catalog, has_elec)
        forced = b.frame.upper() in left_only
        for _ in range(b.qty):
            item = XItem(label=_bk_label(b), xspace=fx, frame=b.frame.upper(),
                         side="left" if forced else "flexible")
            (left_items if forced else flex_items).append(item)

    # --- XT1 groups (flexible) ---
    xt1_grouping = group_xt1(xt1_total, catalog) if xt1_total else {"count": 0, "groups": [], "total_xspace": 0, "rails": []}
    gx = catalog.xt1_group_xspace
    for g in xt1_grouping["groups"]:
        flex_items.append(XItem(label=f"XT1 group×{g}", xspace=gx[g], frame="XT1", side="flexible"))

    # --- panel-level accessories (flexible): spd/rgm40/blank/relt ---
    for acc in spec.accessories:
        resolved = resolve_panel_accessory(acc, catalog)
        qty = int(acc.get("qty", 1))
        ax = resolved["x_space"] * qty
        if ax:
            flex_items.append(XItem(label=resolved["code"], xspace=ax,
                                    frame=acc["kind"].upper(), side="flexible"))

    left_sum = sum(i.xspace for i in left_items)
    flex_sum = sum(i.xspace for i in flex_items)
    return {
        "left_items": left_items,
        "flex_items": flex_items,
        "left_required": left_sum,       # minimum that MUST be on the left
        "flex_required": flex_sum,
        "total": left_sum + flex_sum,
        "xt1_grouping": xt1_grouping,
    }


# --------------------------------------------------------------------------
# 6. pack_two_sided  (highest-risk rule)
# --------------------------------------------------------------------------


def _subset_reachable(sizes: list[int], lo: int, hi: int) -> Optional[set[int]]:
    """Return a subset-sum (as a set of indices) with total in [lo, hi], or None.

    Real bin-packing of indivisible flex items across the two sides.
    """
    if lo <= 0 <= hi:
        return set()
    # DP over reachable sums -> one witnessing index-set
    reachable: dict[int, set[int]] = {0: set()}
    for idx, s in enumerate(sizes):
        for total in list(reachable.keys()):
            nt = total + s
            if nt not in reachable:
                reachable[nt] = reachable[total] | {idx}
    for total, idxs in reachable.items():
        if lo <= total <= hi:
            return idxs
    return None


def pack_two_sided(left_items: list[XItem], flex_items: list[XItem], sku: dict) -> dict:
    """Two-sided bin-pack against one SuperBox SKU (rule #2).

    Left-only frames go LEFT first; if their sum exceeds the box's left
    X-space capacity the loadout is INVALID — we reject it, we do NOT fall back
    to total capacity. Remaining flexible items are then bin-packed across the
    leftover left capacity and the right capacity (indivisible units).
    """
    cap_left = int(sku["xspace_left"])
    cap_right = int(sku["xspace_right"])
    left_forced = sum(i.xspace for i in left_items)

    if left_forced > cap_left:
        return {
            "fits": False,
            "reason": f"left-only load {left_forced}X exceeds left capacity {cap_left}X "
                      f"(valid on total X, but per-side limit violated)",
            "left_used": left_forced, "right_used": 0,
            "cap_left": cap_left, "cap_right": cap_right,
        }

    remaining_left = cap_left - left_forced
    flex_sizes = [i.xspace for i in flex_items]
    flex_total = sum(flex_sizes)

    # choose a subset of flex to put on the left: subset_sum in
    # [flex_total - cap_right, remaining_left]
    lo = max(0, flex_total - cap_right)
    hi = remaining_left
    if lo > hi:
        return {
            "fits": False,
            "reason": f"total flexible {flex_total}X exceeds remaining capacity "
                      f"(left {remaining_left}X + right {cap_right}X)",
            "left_used": left_forced, "right_used": 0,
            "cap_left": cap_left, "cap_right": cap_right,
        }

    chosen = _subset_reachable(flex_sizes, lo, hi)
    if chosen is None:
        return {
            "fits": False,
            "reason": "flexible items cannot be split across sides without exceeding a per-side limit",
            "left_used": left_forced, "right_used": 0,
            "cap_left": cap_left, "cap_right": cap_right,
        }

    flex_left = sum(flex_sizes[i] for i in chosen)
    flex_right = flex_total - flex_left
    as_dict = lambda it: {"label": it.label, "frame": it.frame, "xspace": it.xspace, "side": it.side}
    left_assigned = [as_dict(i) for i in left_items] + [as_dict(flex_items[i]) for i in sorted(chosen)]
    right_assigned = [as_dict(flex_items[i]) for i in range(len(flex_items)) if i not in chosen]
    return {
        "fits": True,
        "reason": "ok",
        "left_used": left_forced + flex_left,
        "right_used": flex_right,
        "cap_left": cap_left, "cap_right": cap_right,
        "left_assigned": left_assigned,
        "right_assigned": right_assigned,
    }


# --------------------------------------------------------------------------
# 7. select_superbox
# --------------------------------------------------------------------------


def _candidate_skus(spec: Spec, catalog: Catalog) -> list[dict]:
    # panel_amps is the panel's rating — match the box of THAT ampacity exactly
    # (the user selects a concrete box size, not a "minimum").
    out = []
    for sku in catalog.skus:
        if sku["amps"] != spec.panel_amps:
            continue
        if sku["main_type"] != spec.main_type:
            continue
        if sku["enclosure"] != spec.enclosure:
            continue
        out.append(sku)
    return out


def select_superbox(spec: Spec, catalog: Catalog) -> dict:
    """Pick the SuperBox SKU(s) that fit, or refuse / report ambiguity.

    0 fit  → FactoryAssemblyRequired("exceeds largest SuperBox …").
    >1 fit → ambiguous: return ALL options, do not pick (refuse-to-guess).
    1 fit  → selected.
    """
    candidates = _candidate_skus(spec, catalog)
    if not candidates:
        raise FactoryAssemblyRequired(
            f"no merchandised SuperBox for {spec.panel_amps}A / {spec.main_type} / {spec.enclosure}",
        )

    fitting = []
    attempts = []
    # smallest box first (by amps then left capacity) so options list is ordered
    for sku in sorted(candidates, key=lambda s: (s["amps"], s["xspace_left"] + s["xspace_right"])):
        part = partition_loadout(spec, catalog, catalog.left_only_frames(sku["offset_class"]))
        packed = pack_two_sided(part["left_items"], part["flex_items"], sku)
        attempts.append({"sku": sku["sku"], "packed": packed, "partition": part})
        if packed["fits"]:
            fitting.append({"sku": sku, "packed": packed, "partition": part})

    if not fitting:
        # required X exceeds the chosen-ampacity box — a larger panel rating is needed
        box = max(candidates, key=lambda s: s["xspace_left"] + s["xspace_right"])
        part = partition_loadout(spec, catalog, catalog.left_only_frames(box["offset_class"]))
        raise FactoryAssemblyRequired(
            f"required X-space (left {part['left_required']}X + flex {part['flex_required']}X "
            f"= {part['total']}X) exceeds the {spec.panel_amps}A {spec.main_type} {spec.enclosure} "
            f"SuperBox ({box['sku']}: {box['xspace_left']}+{box['xspace_right']}X) — "
            f"select a larger panel ampacity",
            detail={"attempts": attempts},
        )

    return {
        "status": "ambiguous" if len(fitting) > 1 else "ok",
        "options": fitting,
        "selected": fitting[0] if len(fitting) == 1 else None,
        "attempts": attempts,
    }


# --------------------------------------------------------------------------
# 8. assemble_bom
# --------------------------------------------------------------------------


@dataclass
class BomLine:
    item: str
    qty: int
    part_number: str
    description: str
    page: str


def assemble_bom(spec: Spec, catalog: Catalog) -> dict:
    """Top-level orchestration → {status, bom, validation, flags}.

    Refuse cases (FactoryAssemblyRequired) are caught and returned as a
    structured 'refused' result with the factory-assembled banner + reason.
    Ambiguous (fits >1 box) is returned as 'ambiguous' with the option list.
    """
    flags: list[str] = []
    try:
        # resolve all breakers first (surfaces refuse cases early)
        resolved_branches = []
        for b in spec.branches:
            row = resolve_breaker(b, catalog)
            resolved_branches.append((b, row))
        resolved_main = None
        if spec.main is not None:
            resolved_main = resolve_breaker(spec.main, catalog)

        selection = select_superbox(spec, catalog)
    except FactoryAssemblyRequired as e:
        return {
            "status": "refused",
            "bom": [],
            "validation": {"flags": [str(e)]},
            "reason": e.reason,
            "detail": e.detail,
        }

    if selection["status"] == "ambiguous":
        opts = [o["sku"]["sku"] for o in selection["options"]]
        return {
            "status": "ambiguous",
            "bom": [],
            "validation": {
                "flags": [f"Loadout fits multiple SuperBox sizes: {opts} — select one."],
                "options": opts,
            },
            "reason": "ambiguous: multiple SuperBox sizes fit",
        }

    sel = selection["selected"]
    sku = sel["sku"]
    part = sel["partition"]
    packed = sel["packed"]
    family = sku["rail_orientation"]

    # XT1 grouping with rails resolved for the chosen box's orientation family
    xt1 = group_xt1(part["xt1_grouping"]["count"], catalog, rail_family=family)

    # ---- BOM lines ----
    bom: list[BomLine] = []
    bom.append(BomLine(
        item="SuperBox enclosure+interior",
        qty=1,
        part_number=sku["sku"],
        description=f"{sku['amps']}A {sku['main_type']} {sku['enclosure']} "
                    f"{'x'.join(str(d) for d in sku['dims_in'])} in",
        page=sku["page"],
    ))
    if resolved_main is not None:
        bom.append(BomLine(
            item="Main breaker", qty=1,
            part_number=resolved_main["ordering_code"],
            description=f"{resolved_main['frame']} {resolved_main['poles']}P "
                        f"{resolved_main['amps']}A {resolved_main['int_rating']} "
                        f"({spec.main.orientation})",
            page=resolved_main["page"],
        ))
    # branch breakers (collapse identical ordering codes)
    counts: dict[str, dict] = {}
    for b, row in resolved_branches:
        key = row["ordering_code"]
        if key not in counts:
            counts[key] = {"row": row, "qty": 0}
        counts[key]["qty"] += b.qty
    for code, agg in counts.items():
        row = agg["row"]
        bom.append(BomLine(
            item="Branch breaker", qty=agg["qty"], part_number=code,
            description=f"{row['frame']} {row['poles']}P {row['amps']}A "
                        f"{row['int_rating']} lug {row.get('load_lug','')}",
            page=row["page"],
        ))
    # XT1 mounting rails (one line per group; collapse identical SKUs)
    rail_counts: dict[str, int] = {}
    for r in xt1["rails"]:
        rail_counts[r] = rail_counts.get(r, 0) + 1
    for rail, qty in rail_counts.items():
        bom.append(BomLine(
            item="XT1 mounting rail", qty=qty, part_number=rail,
            description="XT1 mounting rail (not included in SuperBox)",
            page="11-61",
        ))

    # breaker-mounted accessories (aux / shunt / UVR / padlock / service-entrance barrier)
    acc_counts: dict[str, dict] = {}
    def _add_acc(code: str, desc: str, page: str, qty: int) -> None:
        slot = acc_counts.setdefault(code, {"desc": desc, "page": page, "qty": 0})
        slot["qty"] += qty
    for b, _row in resolved_branches:
        for a in b.accessories:
            r = resolve_breaker_accessory(a, b.frame, catalog)
            _add_acc(r["code"], f"{a.get('kind')} for {b.frame}", r.get("page", ""), b.qty)
    if spec.main is not None:
        for a in spec.main.accessories:
            r = resolve_breaker_accessory(a, spec.main.frame, catalog)
            _add_acc(r["code"], f"{a.get('kind')} for main {spec.main.frame}", r.get("page", ""), 1)
    for code, agg in acc_counts.items():
        bom.append(BomLine(item="Accessory", qty=agg["qty"], part_number=code,
                           description=agg["desc"], page=agg["page"]))

    # panel-level accessories (SPD / RGM40 meter / blank+filler / RELT kit)
    panel_counts: dict[str, dict] = {}
    for acc in spec.accessories:
        r = resolve_panel_accessory(acc, catalog)
        slot = panel_counts.setdefault(
            r["code"], {"desc": f"{acc['kind']} ({r['x_space']}X)" if r["x_space"] else acc["kind"],
                        "page": r.get("page", ""), "qty": 0})
        slot["qty"] += int(acc.get("qty", 1))
    for code, agg in panel_counts.items():
        bom.append(BomLine(item="Panel accessory", qty=agg["qty"], part_number=code,
                           description=agg["desc"], page=agg["page"]))

    validation = {
        "xt1_grouping": xt1,
        "xspace": {
            "total": part["total"],
            "left_required": part["left_required"],
            "left_used": packed["left_used"],
            "right_used": packed["right_used"],
            "left_capacity": packed["cap_left"],
            "right_capacity": packed["cap_right"],
            "breakdown": [
                {"label": i.label, "xspace": i.xspace, "frame": i.frame, "side": i.side}
                for i in (part["left_items"] + part["flex_items"])
            ],
        },
        "selected_superbox": sku["sku"],
        "why": f"{sku['amps']}A {sku['main_type']} {sku['enclosure']} box; "
               f"left {packed['left_used']}/{packed['cap_left']}X, "
               f"right {packed['right_used']}/{packed['cap_right']}X",
        "flags": flags,
    }

    # ---- drawing data: panel-marks specs + two-sided layout ----
    if resolved_main is not None:
        main_disc = {
            "type": "Main breaker",
            "catalog": resolved_main["ordering_code"],
            "amps": resolved_main["amps"],
            "poles": resolved_main["poles"],
            "int_rating": resolved_main["int_rating"],
            "lug": resolved_main.get("load_lug", ""),
            "orientation": spec.main.orientation if spec.main else "horizontal",
        }
    else:
        main_disc = {"type": "Main lugs", "catalog": "—", "amps": sku["amps"],
                     "poles": 3, "int_rating": "", "lug": "", "orientation": "—"}
    # panel short-circuit rating = lowest interrupting rating of any installed device
    # (BuyLog General Characteristics). Bus is rated 200/100/65 kAIC @ 240/480/600 V.
    ratings = [row["int_rating_kA"] for _, row in resolved_branches if row.get("int_rating_kA")]
    if resolved_main and resolved_main.get("int_rating_kA"):
        ratings.append(resolved_main["int_rating_kA"])
    kaic = min(ratings) if ratings else None
    validation["specs"] = {
        "panel_type": "ReliaGear neXT SuperBox",
        "amps": sku["amps"],
        "voltage": spec.voltage or "—",
        "system": spec.system or "—",
        "kaic": kaic,
        "main_type": sku["main_type"],
        "enclosure": sku["enclosure"],
        "mounting": "Surface",
        "dims_in": sku["dims_in"],
        "gf_on_main": sku["gf_on_main"],
        "main": main_disc,
    }
    validation["layout"] = {
        "sku": sku["sku"], "amps": sku["amps"], "main_type": sku["main_type"],
        "enclosure": sku["enclosure"], "dims_in": sku["dims_in"],
        "cap_left": packed["cap_left"], "cap_right": packed["cap_right"],
        "left": packed.get("left_assigned", []),
        "right": packed.get("right_assigned", []),
    }
    return {"status": "ok", "bom": bom, "validation": validation}
