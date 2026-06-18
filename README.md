# SuperBox BOM Generator

A configurator that turns a panel spec — main type, breaker loadout, enclosure — into a
complete, **orderable bill of materials** for an ABB ReliaGear® neXT **SuperBox** power
panelboard, or tells you clearly when the configuration falls outside the merchandised
envelope and must be factory-assembled.

It does the fiddly, error-prone parts an estimator would otherwise do by hand off the
BuyLog: the non-linear XT1 X-space grouping, the two-sided wire-bending packing, the
main/accessory X-space accounting, and the "is this even a merchandised box?" check.

**Repo:** https://github.com/teddygcodes/superboxconfig
**By:** HESCO Solutions

---

## Use it online (no install)

The whole tool runs in your browser — the verified Python engine is executed
client-side via [Pyodide](https://pyodide.org), so there's nothing to install and
no server to run:

### 👉 https://teddygcodes.github.io/superboxconfig/

(First load fetches the Python runtime — a few seconds — then it's instant.)

If you'd rather run it locally or hack on it, see below.

---

## Quick start

Requires **Python 3.9+**.

```bash
git clone https://github.com/teddygcodes/superboxconfig.git
cd superboxconfig

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

### Run the web app (recommended)

```bash
python webapp/app.py
```

This serves the configurator at **http://127.0.0.1:5000** and opens your browser. Build a
panel visually and watch the BOM, validation, and drawing update live.

### Run from the command line

```bash
# from a spec file (YAML or JSON)
python -m superbox_bom.cli --spec examples/spec_mlo_nema1.yaml
python -m superbox_bom.cli --spec examples/spec_mlo_nema1.yaml --json

# or from flags (branch = frame:poles:amps:kA:qty[:lug], repeatable)
python -m superbox_bom.cli --panel-amps 1200 --main-type MLO --enclosure NEMA1 \
    --branch "XT4:3:250:65:2:3/0-350"
```

Exit code is `0` for a clean BOM, `2` for a refuse/ambiguous result, `1` for a usage error.

### Run the tests

```bash
python -m pytest
```

---

## What the web app does

Five tabs, modeled on the ABB empower Panelboards flow:

- **Panel** — ampacity, main type, enclosure, voltage/system, and (for MCB) the main
  breaker. You size by **amperage first** and the frame auto-defaults but stays editable.
  The main type is gated to boxes that actually exist (e.g. MCB-GF only at 1200 A). The
  main carries its own aux / shunt / UVR / padlock / service-entrance-barrier accessories.
- **Feeders** — a branch table with **catalog-driven cascading dropdowns**: only real
  frame/amp/rating/trip/lug combinations are selectable, the part number resolves live,
  and each row has its frame-appropriate accessories.
- **Accessories** — panel-level plug-ins: SPD (10X), RGM40 meter (4X), RELT kit, blanks.
- **BOM** — the live bill of materials plus a validation panel: the selected SuperBox, the
  XT1 grouping with rail SKUs, left/right X-space bars vs. capacity, and any flags.
- **Drawing** — an empower-style panel-marks sheet (technical specs incl. a **derived
  KAIC/SCCR**, main disconnect, interior X-values, Box BOM + Interior BOM) beside a
  two-sided layout diagram showing each breaker placed left/right by X-space, with a
  **Print / Save PDF** button.

A configuration either produces an orderable BOM or returns
*"REQUIRES FACTORY-ASSEMBLED neXT — contact ABB"* with a specific reason. It never
invents a part number.

## The rules it gets exact

1. **XT1 grouping** — X-space is non-linear (1×=3X, 2×=5X, 5×=11X). N breakers are binned
   `[5, 2, 1]` to minimize total X (7 → 5+2 = 16X, *not* 5+1+1 = 17X). Each group needs its
   own mounting-rail SKU (`SR1XBF` / `SR2XBF` / `SR5XBF`) as a separate BOM line.
2. **Two-sided packing** — XT5/XT6/XT7 mount on the wide (left) side only. A loadout that
   fits on *total* X but exceeds the *left* capacity is rejected, not rounded away.
3. **Main X-space** — the published box left/right capacity is used as-is: MLO charges 0
   (lugs already netted out), MCB charges only the selected main breaker's frame X-space.
4. **XT5 +1X** when electrical accessories are present.
5. **Box selection by exact ampacity** — `panel_amps` is the panel's rating, so the tool
   picks the box of *that* ampacity; if the load overflows it, it refuses and tells you to
   step up — it never silently upsizes.

## How it's built

```
data/         breakers.json · xspace.json · superbox.json · accessories.json   (catalog)
superbox_bom/ engine.py (pure rules) · catalog.py (I/O) · cli.py · errors.py
webapp/       app.py (Flask) · static/ (HTML · CSS · vanilla JS UI)
tests/        64 unit tests
examples/     spec_mlo_nema1.yaml · spec_mcb_750kcmil_refuse.yaml · spec_accessories.yaml
```

All catalog data lives in JSON; the engine is pure functions with no data baked in, so the
logic is fully testable without a server and the catalog can be updated without touching
code. The web UI and CLI are thin layers over the same `assemble_bom` function.

The catalog is the **merchandised** subset of ABB's offering. Anything outside it (a
breaker not in the table, 750 kcmil lugs, a 100%-rated breaker, a load that exceeds the
largest box) returns a clear factory-assembled flag rather than a fabricated SKU.

## Data source & disclaimer

The catalog data is transcribed from **ABB BuyLog Section 11** (ReliaGear neXT SuperBox,
pp. 11-52..11-66) — ABB's copyrighted catalog, which is **not** included in this repo.
177 breaker rows, 14 SuperBox SKUs, and the full Step 2 accessory tables were transcribed
and cross-checked against the source.

This is an **independent tool and is not affiliated with, endorsed by, or supported by
ABB.** "ReliaGear", "SuperBox", "Tmax", and the part numbers are ABB's. Always verify the
generated BOM against current ABB documentation and your local ABB sales team before
ordering — the tool is provided **as-is, without warranty**, and the authors are not
responsible for ordering errors.

## License

The source code is released under the **MIT License** (see [LICENSE](LICENSE)). The
catalog data under `data/` is transcribed from ABB's BuyLog and remains ABB's
intellectual property — it is included here for interoperability, not relicensed.
