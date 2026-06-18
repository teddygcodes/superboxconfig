"use strict";
// GitHub Pages build: load the real Python engine with Pyodide and route the
// app's /api/catalog and /api/bom calls to it, so the same verified code runs
// fully client-side with no server. app.js is unchanged.

(async () => {
  const PY_FILES = ["__init__.py", "errors.py", "catalog.py", "engine.py"];
  const DATA_FILES = ["breakers.json", "xspace.json", "superbox.json", "accessories.json"];
  const boot = document.getElementById("boot");
  const setMsg = (t) => { const m = boot && boot.querySelector(".msg"); if (m) m.textContent = t; };

  try {
    setMsg("Starting Python runtime…");
    const pyodide = await loadPyodide({ indexURL: "https://cdn.jsdelivr.net/pyodide/v0.26.2/full/" });

    setMsg("Loading the catalog…");
    pyodide.FS.mkdir("superbox_bom");
    pyodide.FS.mkdir("data");
    const grab = async (url) => {
      const r = await fetch(url);
      if (!r.ok) throw new Error("could not load " + url + " (" + r.status + ")");
      return r.text();
    };
    for (const f of PY_FILES) pyodide.FS.writeFile("superbox_bom/" + f, await grab("superbox_bom/" + f));
    for (const f of DATA_FILES) pyodide.FS.writeFile("data/" + f, await grab("data/" + f));

    setMsg("Initializing the engine…");
    await pyodide.runPythonAsync([
      "import sys, json",
      "sys.path.insert(0, '.')",
      "from superbox_bom.catalog import Catalog",
      "from superbox_bom.engine import assemble_bom, spec_from_dict, result_to_jsonable",
      "_cat = Catalog.load()",
      "def _options():",
      "    return json.dumps(_cat.export_options())",
      "def _bom(spec_json):",
      "    try:",
      "        spec = spec_from_dict(json.loads(spec_json))",
      "        return json.dumps(result_to_jsonable(assemble_bom(spec, _cat)))",
      "    except Exception as e:",
      "        return json.dumps({'status': 'error', 'reason': str(e)})",
    ].join("\n"));

    const optionsFn = pyodide.globals.get("_options");
    const bomFn = pyodide.globals.get("_bom");

    const jsonResp = (s) => new Response(s, { status: 200, headers: { "Content-Type": "application/json" } });
    const origFetch = window.fetch.bind(window);
    window.fetch = async (url, opts) => {
      const u = typeof url === "string" ? url : (url && url.url);
      if (u === "/api/catalog") return jsonResp(optionsFn());
      if (u === "/api/bom") return jsonResp(bomFn(opts && opts.body));
      return origFetch(url, opts);
    };

    if (boot) boot.remove();
    const s = document.createElement("script");
    s.src = "webapp/static/app.js";
    document.body.appendChild(s);
  } catch (err) {
    console.error(err);
    setMsg("Failed to load: " + (err && err.message ? err.message : err));
    const sub = boot && boot.querySelector(".sub");
    if (sub) sub.textContent = "Check your connection and refresh.";
  }
})();
