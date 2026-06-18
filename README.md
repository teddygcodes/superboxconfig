# ABB ReliaGear neXT SuperBox — BOM Generator

Turns a panel spec (main type + breaker loadout + enclosure) into an orderable
bill of materials for a merchandised **ReliaGear neXT SuperBox** power
panelboard — or refuses with a clear *factory-assembled required* flag when the
configuration falls outside the merchandised envelope.

Source of truth: **ABB BuyLog Section 11**, pp. 11-52..11-66 (ABB's copyrighted
catalog — not included in this repo; obtain it from ABB).
All catalog data lives in `data/*.json`; the engine is pure logic with no data
baked in.

## Install / run

The data was transcribed against a real CPython (the `python` on the system
`PATH` here is a Microsoft Store stub — use a real interpreter):

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # click, PyYAML, pytest
.venv/Scripts/python -m pytest -q                # 35 tests
```

### Web UI (ABB empower-styled)

A local browser app wraps the same engine — no terminal needed:

```bash
.venv/Scripts/python webapp/app.py     # serves http://127.0.0.1:5000, opens your browser
```

Tabs: **Panel** (ampacity / main type / enclosure / voltage+system / main breaker —
sized amps-first, frame auto-defaults; main type gated to the boxes that exist, e.g.
MCB-GF only at 1200 A; the main carries its own aux/shunt/UVR/padlock/SE-barrier
accessories) · **Feeders** (catalog-driven cascading dropdowns, also amps-first;
only real frame/amp/rating/lug combos are selectable, with per-row aux/shunt/UVR/
padlock/SE-barrier accessories filtered to what each frame supports) · **Accessories**
(SPD / RGM40 / RELT kit / blanks) · **BOM** (live bill of materials
+ validation: selected box, XT1 grouping, left/right X-space bars vs. capacity, flags) ·
**Drawing** (an empower-style panel-marks sheet — technical specs incl. voltage/system
and a derived **KAIC/SCCR** (lowest installed device rating), main disconnect, interior
X-values, Box BOM + Interior BOM — beside a two-sided layout diagram with numbered
positions, the main at the bottom, spacers, and enclosure dimension lines, plus a
**Print / Save PDF** button). It
recomputes live as you change the config. The UI is a thin layer over `assemble_bom`;
all the verified logic is unchanged.

### CLI

Run it:

```bash
# from a spec file (YAML or JSON)
python -m superbox_bom.cli --spec examples/spec_mlo_nema1.yaml
python -m superbox_bom.cli --spec examples/spec_mlo_nema1.yaml --json

# or from flags  (branch = frame:poles:amps:kA:qty[:lug], repeatable)
python -m superbox_bom.cli --panel-amps 1200 --main-type MLO --enclosure NEMA1 \
    --branch "XT4:3:250:65:2:3/0-350"
```

Exit code is `0` on a clean BOM, `2` on refuse/ambiguous, `1` on a usage error
(e.g. an under-specified breaker that matches multiple trip units).

## The five correctness rules (the whole point)

1. **XT1 grouping** — X-space is non-linear (1×=3X, 2×=5X, 5×=11X). N breakers are
   binned `[5,2,1]` to minimize total X (7 → 5+2 = 16X, *not* 5+1+1 = 17X). Each
   group needs its own mounting-rail SKU (`SR5XBF` / `SR2XBF` / `SR1XBF`, or the
   `*BR` family by orientation) — a separate BOM line, **not** included in the box.
2. **Two-sided packing** — XT5/XT6/XT7 (and XT4 in 45" boxes) mount **left only**.
   A loadout that fits on *total* X but exceeds the *left* capacity is rejected,
   not rounded away. Flexible breakers are bin-packed across the leftover left +
   right capacity (indivisible units).
3. **Main X-space** — the Step 4 left/right columns are the panel's usable capacity
   as-published, so the main is charged against them directly: **MLO = 0** (the lugs
   are already netted out — MLO boxes show 4X less per side than the identical MCB),
   and **MCB = the selected main breaker's own frame X-space** (Step 4 footnote 1), no
   separate lug-pad add.
4. **XT5 +1X** when electrical accessories are present.
5. **Box selection by exact ampacity** — `panel_amps` is the panel's rating, so the
   tool selects the SuperBox of *that* ampacity (600/800/1200), not a larger one. If
   the loadout overflows that box's X-space it **refuses** with "select a larger panel
   ampacity" rather than silently upsizing.
6. **Refuse, don't fabricate** — unknown combo, 750 kcmil lugs, 100%-rated, or a load
   that exceeds the chosen box all return *"REQUIRES FACTORY-ASSEMBLED neXT — contact
   ABB"* with a specific reason; nothing is invented.

## Layout

```
data/        breakers.json · xspace.json · superbox.json · accessories.json
superbox_bom/ engine.py (pure rules) · catalog.py (I/O) · cli.py · errors.py
tests/       group_xt1 · pack_two_sided · xspace · refuse · assemble_bom
             · branches_teyfba2 · accessories
examples/    spec_mlo_nema1.yaml · spec_mcb_750kcmil_refuse.yaml · spec_accessories.yaml
```

## Accessories (Step 2, pp.11-61/62)

`accessories.json` holds the Step 2 catalog. Two classes:

- **Breaker-mounted** (`aux_contacts`, `shunt_trip`, `undervoltage_release`,
  `padlock`, `service_entrance_barrier`) — attach to a branch/main via that
  breaker's `accessories: [...]` list. They resolve by the breaker's frame + keys
  and emit BOM lines. An aux/shunt/UVR on an **XT5 adds +1X** automatically (rule #4).
- **Panel-level plug-ins** (`spd` 10X, `rgm40` 4X, `blank` 1–3X, `relt` kit 3X) —
  listed under the spec's top-level `accessories: [...]`. They consume panel
  X-space and emit BOM lines. See `examples/spec_accessories.yaml`.

Example breaker-mounted: `{kind: shunt_trip, volts: 110}` on an XT1 → `KXTASORCFPD`.
Example panel-level: `{kind: spd, voltage: "480Y/277", ka: 150}` → `RGPPSP277Y15T2` (10X).
A missing or ambiguous accessory raises a clear error rather than guessing.

## Data provenance (all confirmed against BuyLog scans)

These are flagged inline in the JSON; the engine raises a clear `CatalogError`
if it hits an un-transcribed cell rather than guessing:

- ✅ **`xspace.json` `frame_xspace`** — confirmed from a clean scan of the Step 3
  table (p.11-63): XT4=3, XT5=4@3P. (Resolved.)
- ✅ **`superbox.json` SKU table + wire-bend** — confirmed from clean scans of Step 4
  and the wire-bend table (p.11-64). All 14 SKUs / dims / L-R capacities match, and
  the wire-bend inch values are now filled. Correction applied: **XT4 is NOT
  left-only** (it has a 5.2" right mount in both enclosures); only XT5/XT6/XT7 are.
  left-only is now derived from the table's `right_in == null`. (Resolved.)
- ✅ **`xspace.json` SPD / RGM40 X-space** — resolved: **SPD plug-in = 10X**, **RGM40
  meter = 4X** (p.11-62 device-page footnotes, confirmed). The Step 3 table's printed
  SPD = 6X is a known BuyLog inconsistency; 10X governs. (Resolved.)
- ✅ **`superbox.json` MLO X-space basis** — resolved: the published left/right values
  are the usable capacity as-is. MLO charges 0 for the main (lugs already netted out);
  MCB charges only the selected main breaker's frame X-space. (Resolved.)
- ✅ **`superbox.json` `rail_orientation`** — resolved: the SuperBox uses the **BF** rail
  family (SR1XBF/SR2XBF/SR5XBF) per the Step 2 SuperBox accessories table (p.11-61). The
  BR variants on the breaker-nomenclature page (11-65/66) are generic Tmax/SB mounting,
  not SuperBox. (Resolved.)
- ✅ **`breakers.json`** — all 177 rows transcribed and verified against clean scans:
  XT1 (31), XT2 (11), XT4 (49), XT5 (22), XT6 (5), XT7 (13), TEY (21), FB (12),
  A2 (13). 1-/2-pole TEY/FB/A2 are phase-specific (resolve needs `phase`). One known
  BuyLog quirk: `A2N2125ABDXXXX` prints "A (10 kA)" in the rating column but its part
  number encodes N (25 kA); we follow the part number and flag it on that row.
  (Resolved.)
- ✅ **`accessories.json`** — Step 2 catalog (pp.11-61/62) transcribed and wired into
  the BOM: aux contacts, shunt trip, UVR, padlocks, RELT kits, service-entrance
  barriers, blanks/fillers, SPD, RGM40. One flagged quirk: the XT5/XT6 shunt-trip
  cell is merged in the BuyLog (`KXTFYOCFPD`, voltage variants not differentiated).
  (Resolved.)

**All BuyLog data items are now confirmed against clean scans — no open data TODOs.**
(The XT5/XT6 shunt-trip merged cell and the `A2N2125ABDXXXX` rating misprint are
documented BuyLog quirks, not open questions.)
