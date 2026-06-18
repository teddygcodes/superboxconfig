"""Local web UI for the SuperBox BOM generator (ABB empower-styled).

Thin Flask layer over the pure engine — no BOM/X-space logic lives here. Run:

    python webapp/app.py

then open http://127.0.0.1:5000 in your browser.
"""

from __future__ import annotations

import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

# make the package importable when run as `python webapp/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from superbox_bom.catalog import Catalog
from superbox_bom.engine import assemble_bom, result_to_jsonable, spec_from_dict
from superbox_bom.errors import FACTORY_BANNER, SuperBoxError

STATIC = Path(__file__).resolve().parent / "static"
app = Flask(__name__, static_folder=str(STATIC), static_url_path="/static")
catalog = Catalog.load()


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/catalog")
def api_catalog():
    """Options for the UI dropdowns, straight from the verified data files."""
    return jsonify(catalog.export_options())


@app.post("/api/bom")
def api_bom():
    """Take a spec (same shape as the YAML spec) → BOM + validation."""
    data = request.get_json(force=True) or {}
    try:
        spec = spec_from_dict(data)
        result = result_to_jsonable(assemble_bom(spec, catalog))
        return jsonify(result)
    except SuperBoxError as e:
        # e.g. ambiguous breaker that needs trip_unit/load_lug/phase to resolve
        return jsonify({"status": "error", "reason": str(e), "banner": FACTORY_BANNER}), 200
    except (KeyError, ValueError, TypeError) as e:
        return jsonify({"status": "error", "reason": f"bad spec: {e}"}), 400


def main():
    url = "http://127.0.0.1:5000"
    print(f"SuperBox BOM web UI -> {url}  (Ctrl+C to stop)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
