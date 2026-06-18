"""Command-line interface (click) for the SuperBox BOM generator.

Reads a spec from a YAML/JSON file (``--spec``) or from explicit flags, runs the
engine, and renders either a human-readable BOM + validation block or (--json)
machine output.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import click

from .catalog import Catalog
from .engine import Breaker, Spec, assemble_bom
from .errors import FACTORY_BANNER, SuperBoxError


# --------------------------------------------------------------------------
# spec parsing
# --------------------------------------------------------------------------


def _load_spec_file(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml  # lazy import so JSON-only users don't need PyYAML
        return yaml.safe_load(text)
    if path.suffix.lower() == ".json":
        return json.loads(text)
    # auto-detect: try JSON, then YAML
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import yaml
        return yaml.safe_load(text)


def _breaker_from_dict(d: dict) -> Breaker:
    return Breaker(
        frame=d["frame"],
        poles=int(d["poles"]),
        amps=int(d["amps"]),
        int_rating=d.get("int_rating"),
        qty=int(d.get("qty", 1)),
        trip_unit=d.get("trip_unit"),
        load_lug=d.get("load_lug"),
        phase=d.get("phase"),
        elec_accessory=bool(d.get("elec_accessory", False)),
        rated_100pct=bool(d.get("rated_100pct", False)),
        orientation=d.get("orientation", "horizontal"),
        lug_pad_sets=int(d.get("lug_pad_sets", 1)),
        accessories=d.get("accessories", []),
    )


def _spec_from_dict(d: dict) -> Spec:
    main = _breaker_from_dict(d["main"]) if d.get("main") else None
    branches = [_breaker_from_dict(b) for b in d.get("branches", [])]
    return Spec(
        panel_amps=int(d["panel_amps"]),
        main_type=d["main_type"],
        enclosure=d["enclosure"],
        main=main,
        branches=branches,
        accessories=d.get("accessories", []),
        voltage=d.get("voltage"),
        system=d.get("system"),
    )


def _parse_branch_flag(s: str) -> Breaker:
    # frame:poles:amps:kA:qty[:lug]
    parts = s.split(":")
    if len(parts) < 5:
        raise click.BadParameter(f"--branch must be frame:poles:amps:kA:qty[:lug], got {s!r}")
    frame, poles, amps, kA, qty = parts[:5]
    lug = parts[5] if len(parts) > 5 else None
    return Breaker(frame=frame, poles=int(poles), amps=int(amps),
                   int_rating=kA, qty=int(qty), load_lug=lug)


# --------------------------------------------------------------------------
# rendering
# --------------------------------------------------------------------------


def _render_table(bom: list) -> str:
    headers = ["Qty", "Part number", "Description", "Pg"]
    rows = [[str(l.qty), l.part_number, l.description, l.page] for l in bom]
    widths = [len(h) for h in headers]
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    line = lambda cells: "  ".join(c.ljust(widths[i]) for i, c in enumerate(cells))
    out = [line(headers), "  ".join("-" * w for w in widths)]
    out += [line(r) for r in rows]
    return "\n".join(out)


def _render_human(result: dict) -> str:
    status = result["status"]
    if status == "refused":
        return f"{FACTORY_BANNER}\nReason: {result['reason']}"
    if status == "ambiguous":
        opts = ", ".join(result["validation"]["options"])
        return (f"{FACTORY_BANNER if False else 'AMBIGUOUS — multiple SuperBox sizes fit'}\n"
                f"Options: {opts}\nNarrow the spec (ampacity / enclosure) to pick one.")

    v = result["validation"]
    x = v["xspace"]
    out = ["BILL OF MATERIALS", "=" * 60, _render_table(result["bom"]), ""]
    out.append("VALIDATION")
    out.append("-" * 60)
    g = v["xt1_grouping"]
    out.append(f"XT1 grouping : {g['count']} XT1 → groups {g['groups']} "
               f"({g['total_xspace']}X) rails {g['rails']}")
    out.append(f"Selected box : {v['selected_superbox']}  ({v['why']})")
    out.append(f"X-space      : total {x['total']}X | "
               f"left {x['left_used']}/{x['left_capacity']}X | "
               f"right {x['right_used']}/{x['right_capacity']}X")
    if v.get("flags"):
        out.append(f"Flags        : {v['flags']}")
    return "\n".join(out)


def _result_to_jsonable(result: dict) -> dict:
    out = dict(result)
    if out.get("bom"):
        out["bom"] = [asdict(l) for l in out["bom"]]
    return out


# --------------------------------------------------------------------------
# command
# --------------------------------------------------------------------------


@click.command()
@click.option("--spec", "spec_path", type=click.Path(exists=True, path_type=Path),
              help="YAML or JSON spec file.")
@click.option("--panel-amps", type=int, help="Panel ampacity (if not using --spec).")
@click.option("--main-type", type=click.Choice(["MLO", "MCB", "MCB-GF"]), help="Main type.")
@click.option("--enclosure", type=click.Choice(["NEMA1", "NEMA3R"]), help="Enclosure.")
@click.option("--branch", "branch_flags", multiple=True,
              help="Repeatable: frame:poles:amps:kA:qty[:lug]")
@click.option("--data-dir", type=click.Path(path_type=Path), default=None,
              help="Override data/ directory.")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable JSON output.")
def main(spec_path, panel_amps, main_type, enclosure, branch_flags, data_dir, as_json):
    """Generate an orderable BOM for an ABB ReliaGear neXT SuperBox."""
    # Windows consoles default to cp1252; the output uses em-dash / arrow glyphs.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    catalog = Catalog.load(data_dir)

    if spec_path:
        spec = _spec_from_dict(_load_spec_file(spec_path))
    else:
        if not (panel_amps and main_type and enclosure):
            raise click.UsageError("provide --spec, or all of --panel-amps/--main-type/--enclosure")
        spec = Spec(
            panel_amps=panel_amps, main_type=main_type, enclosure=enclosure,
            branches=[_parse_branch_flag(b) for b in branch_flags],
        )

    try:
        result = assemble_bom(spec, catalog)
    except SuperBoxError as e:
        # e.g. ambiguous breaker match that needs trip_unit/load_lug to resolve
        raise click.ClickException(str(e))

    if as_json:
        click.echo(json.dumps(_result_to_jsonable(result), indent=2))
    else:
        click.echo(_render_human(result))

    # non-zero exit on refuse/ambiguous so scripts can detect it
    if result["status"] != "ok":
        sys.exit(2)


if __name__ == "__main__":
    main()
