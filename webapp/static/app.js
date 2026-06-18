"use strict";

const FIELDS = ["frame", "poles", "amps", "int_rating", "trip_unit", "phase", "load_lug"];
// the main breaker AND feeders are sized by amperage first; the frame then follows
// (but stays editable). Picking the amps auto-defaults the rest to a valid breaker.
const MAIN_ORDER = ["amps", "frame", "poles", "int_rating", "trip_unit", "phase", "load_lug"];
const FEEDER_ORDER = MAIN_ORDER;
let CAT = null;            // /api/catalog payload
let feeders = [];         // feeder row objects
let mainSel = {};         // main breaker selection
let rowSeq = 0;
let recomputeTimer = null;

const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- bootstrap
fetch("/api/catalog").then(r => r.json()).then(cat => {
  CAT = cat;
  initPanel();
  initAccessories();
  addFeeder();
  recompute();
});

// ---------------------------------------------------------------- tabs
$("tabs").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-tab]");
  if (!btn) return;
  document.querySelectorAll("nav.tabs button").forEach(b => b.classList.toggle("active", b === btn));
  document.querySelectorAll(".tabpane").forEach(p =>
    p.classList.toggle("hide", p.dataset.pane !== btn.dataset.tab));
});

// ---------------------------------------------------------------- helpers
function opt(value, label, selected) {
  const o = document.createElement("option");
  o.value = value; o.textContent = label ?? value;
  if (selected) o.selected = true;
  return o;
}
function fillSelect(sel, values, current, placeholder) {
  sel.innerHTML = "";
  if (placeholder !== undefined) sel.appendChild(opt("", placeholder, !current));
  values.forEach(v => sel.appendChild(opt(v, String(v), String(v) === String(current))));
  sel.disabled = values.length === 0;
}
function uniq(arr) { return [...new Set(arr)]; }

// breakers matching a partial selection
function matchBreakers(partial) {
  return CAT.breakers.filter(r =>
    FIELDS.every(f => partial[f] == null || partial[f] === "" ||
      String(r[f] ?? "") === String(partial[f])));
}
// distinct options for `field` given everything chosen before it (in `order`)
function optionsFor(field, sel, order = FIELDS) {
  const before = {};
  for (const f of order) { if (f === field) break; before[f] = sel[f]; }
  const vals = uniq(matchBreakers(before).map(r => r[field]).filter(v => v != null && v !== ""));
  if (field === "frame")
    vals.sort((a, b) => (FRAME_RANK[a] || 99) - (FRAME_RANK[b] || 99));
  else
    vals.sort((a, b) => (typeof a === "number" ? a - b : String(a).localeCompare(String(b))));
  return vals;
}
// preferred frame ordering so the auto-default frame is the expected power frame
// (e.g. 250A -> XT4 before the 2-pole A2)
const FRAME_RANK = { XT1: 1, XT2: 2, XT4: 3, XT5: 4, XT6: 5, XT7: 6, TEY: 7, FB: 8, A2: 9 };
function resolvedCode(sel) {
  const m = matchBreakers(sel);
  if (m.length === 1) return { code: m[0].ordering_code, ok: true };
  if (m.length === 0) return { code: "no match", ok: false };
  return { code: `choose (${m.length})`, ok: false };
}

// ---------------------------------------------------------------- panel
// BuyLog system voltages (General Characteristics)
const VOLTAGES = [
  { v: "208Y/120V", sys: "3Ø, 4-wire" },
  { v: "480Y/277V", sys: "3Ø, 4-wire" },
  { v: "600Y/347V", sys: "3Ø, 4-wire" },
  { v: "240V", sys: "3Ø, 3-wire" },
  { v: "480V", sys: "3Ø, 3-wire" },
  { v: "600V", sys: "3Ø, 3-wire" },
];
function syncSystem() {
  const found = VOLTAGES.find(x => x.v === $("voltage").value);
  $("system").value = found ? found.sys : "";
}
// only offer main types that actually exist as a box for this ampacity+enclosure
// (e.g. MCB-GF exists only at 1200 A)
function validMainTypes() {
  const a = parseInt($("panelAmps").value), e = $("enclosure").value;
  const order = { MLO: 0, MCB: 1, "MCB-GF": 2 };
  return [...new Set(CAT.skus.filter(s => s.amps === a && s.enclosure === e).map(s => s.main_type))]
    .sort((x, y) => order[x] - order[y]);
}
function refreshMainTypes() {
  const cur = $("mainType").value;
  const vals = validMainTypes();
  fillSelect($("mainType"), vals, vals.includes(cur) ? cur : vals[0]);
}
function initPanel() {
  fillSelect($("panelAmps"), CAT.panel_amps, 1200);
  fillSelect($("enclosure"), CAT.enclosures, "NEMA1");
  fillSelect($("voltage"), VOLTAGES.map(x => x.v), "208Y/120V");
  refreshMainTypes();
  syncSystem();
  $("voltage").addEventListener("change", () => { syncSystem(); recompute(); });
  $("panelAmps").addEventListener("change", () => {
    refreshMainTypes(); toggleMain();
    if ($("mainType").value !== "MLO" && $("mainBreakerGrid").dataset.built) { mainSel = {}; renderMainSelects(); }
    recompute();
  });
  $("enclosure").addEventListener("change", () => { refreshMainTypes(); toggleMain(); recompute(); });
  $("mainType").addEventListener("change", () => { toggleMain(); recompute(); });
  toggleMain();
}
function toggleMain() {
  const isMcb = $("mainType").value !== "MLO";
  $("mainBreakerBlock").classList.toggle("hide", !isMcb);
  if (isMcb && !$("mainBreakerGrid").dataset.built) buildMainGrid();
}
function buildMainGrid() {
  const grid = $("mainBreakerGrid");
  grid.dataset.built = "1";
  grid.innerHTML = "";
  const labels = { frame: "Frame", poles: "Poles", amps: "Amps", int_rating: "Int. rating",
                   trip_unit: "Trip unit", phase: "Phase", load_lug: "Load lug" };
  for (const f of MAIN_ORDER) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    wrap.innerHTML = `<label>${labels[f]}${f === "amps" ? " (sizes the main)" : ""}</label>`;
    const sel = document.createElement("select");
    sel.dataset.f = f;
    sel.addEventListener("change", () => {
      mainSel[f] = sel.value;
      // a manual change upstream invalidates the auto-picked fields after it
      let after = false;
      for (const g of MAIN_ORDER) { if (g === f) { after = true; continue; } if (after) mainSel[g] = ""; }
      renderMainSelects(); recompute();
    });
    wrap.appendChild(sel);
    grid.appendChild(wrap);
  }
  document.querySelectorAll('input[name=mainOrient]').forEach(r =>
    r.addEventListener("change", recompute));
  renderMainSelects();
}

// Render the main-breaker selects. Amps leads; the frame and the rest auto-default
// to the first valid option (so a complete main resolves from just the amperage),
// while every field stays editable.
function renderMainSelects() {
  for (const f of MAIN_ORDER) {
    const vals = optionsFor(f, mainSel, MAIN_ORDER);
    if (!vals.map(String).includes(String(mainSel[f]))) mainSel[f] = "";
    if (mainSel[f] === "" && vals.length && f !== "phase") {
      if (f === "amps") {
        const pa = parseInt($("panelAmps").value);          // prefer the panel ampacity
        mainSel.amps = vals.map(Number).includes(pa) ? pa : vals[vals.length - 1];
      } else {
        mainSel[f] = vals[0];
      }
    }
  }
  document.querySelectorAll("#mainBreakerGrid select").forEach(sel => {
    const f = sel.dataset.f;
    const vals = optionsFor(f, mainSel, MAIN_ORDER);
    fillSelect(sel, vals, mainSel[f], f === "phase" ? "(any)" : "—");
    if (f === "phase") sel.parentElement.style.display = vals.length ? "" : "none";
  });
  buildMainAccCell();
}
function buildMainAccCell() {
  const cell = document.getElementById("mainAccCell");
  if (!cell) return;
  if (!mainSel.frame) { cell.innerHTML = '<span class="muted">Select a main breaker first.</span>'; return; }
  mainSel.acc = mainSel.acc || {};
  if (!buildBreakerAccSelectors(cell, mainSel.frame, mainSel.acc, recompute))
    cell.innerHTML = '<span class="muted">No catalog accessories for this frame.</span>';
}

// ---------------------------------------------------------------- feeders
$("addFeeder").addEventListener("click", () => { addFeeder(); recompute(); });

function addFeeder() {
  feeders.push({ id: ++rowSeq, qty: 1, sel: {}, acc: { shunt: "", uvr: "", aux: "", padlock: "", seb: "" } });
  renderFeeders();
}
function removeFeeder(id) {
  feeders = feeders.filter(r => r.id !== id);
  renderFeeders();
  recompute();
}
function renderFeeders() {
  const tb = $("feederRows");
  tb.innerHTML = "";
  feeders.forEach(row => tb.appendChild(feederRowEl(row)));
}
function feederRowEl(row) {
  const tr = document.createElement("tr");

  // qty
  const tdQty = document.createElement("td");
  const qty = document.createElement("input");
  qty.type = "number"; qty.min = 1; qty.value = row.qty; qty.style.width = "56px";
  qty.addEventListener("input", () => { row.qty = Math.max(1, parseInt(qty.value || "1")); recompute(); });
  tdQty.appendChild(qty); tr.appendChild(tdQty);

  // cascade selects (amps-first, like the main)
  const selByField = {};
  for (const f of FEEDER_ORDER) {
    const td = document.createElement("td");
    const sel = document.createElement("select");
    sel.dataset.f = f;
    selByField[f] = sel;
    sel.addEventListener("change", () => {
      row.sel[f] = sel.value;
      // a manual change resets the auto-picked fields after it
      let after = false;
      for (const g of FEEDER_ORDER) { if (g === f) { after = true; continue; } if (after) row.sel[g] = ""; }
      paintRow(); buildAccCell(); recompute();
    });
    td.appendChild(sel); tr.appendChild(td);
  }

  // accessories cell
  const tdAcc = document.createElement("td");
  tdAcc.className = "acc-cell"; tr.appendChild(tdAcc);

  // part # pill
  const tdPn = document.createElement("td");
  const pill = document.createElement("span"); pill.className = "code-pill";
  tdPn.appendChild(pill); tr.appendChild(tdPn);

  // delete
  const tdDel = document.createElement("td");
  const x = document.createElement("button"); x.className = "icon-x"; x.textContent = "×";
  x.title = "remove"; x.addEventListener("click", () => removeFeeder(row.id));
  tdDel.appendChild(x); tr.appendChild(tdDel);

  function paintRow() {
    // once the amperage is chosen, auto-default the frame and the rest to a valid breaker
    const doFill = row.sel.amps !== "" && row.sel.amps != null;
    for (const f of FEEDER_ORDER) {
      const vals = optionsFor(f, row.sel, FEEDER_ORDER);
      if (!vals.map(String).includes(String(row.sel[f]))) row.sel[f] = "";
      if (doFill && row.sel[f] === "" && vals.length && f !== "phase") row.sel[f] = vals[0];
      const ph = (f === "phase" || f === "load_lug" || f === "trip_unit") ? "(any)" : "—";
      fillSelect(selByField[f], vals, row.sel[f], ph);
      if (f === "phase") selByField[f].parentElement.style.opacity = vals.length ? "1" : "0.35";
    }
    const r = resolvedCode(row.sel);
    pill.textContent = (row.sel.amps ? r.code : "—");
    pill.classList.toggle("bad", !!row.sel.amps && !r.ok);
  }

  function buildAccCell() {
    const frame = row.sel.frame;
    if (!frame) { tdAcc.innerHTML = '<span class="muted">—</span>'; return; }
    if (!buildBreakerAccSelectors(tdAcc, frame, row.acc, recompute))
      tdAcc.innerHTML = '<span class="muted">—</span>';
  }

  paintRow(); buildAccCell();
  return tr;
}

// selection keys per breaker-mounted accessory category (mirror of the engine)
const BREAKER_ACC_KEYS = {
  aux_contacts: ["type", "volts"], shunt_trip: ["volts"], undervoltage_release: ["volts"],
  padlock: ["style"], service_entrance_barrier: ["variant"],
};
const pretty = (s) => String(s).replace(/_/g, " ");

// build {label,value,rec} options for an accessory category applicable to a frame
function accFor(category, frame) {
  const recs = (CAT.accessories[category] || []).filter(r =>
    (r.frame && r.frame.toUpperCase() === frame.toUpperCase()) ||
    (r.frames && r.frames.map(x => x.toUpperCase()).includes(frame.toUpperCase())));
  return recs.map(r => {
    const parts = [r.type, r.style ? pretty(r.style) : null, r.variant ? pretty(r.variant) : null,
      (r.volts != null && r.volts !== "") ? r.volts + "V" : null].filter(Boolean);
    return { value: r.code, label: parts.join(" ") || r.code, rec: r };
  });
}
function addAccSelect(parent, name, options, current, onChange) {
  if (!options.length) return;
  const sel = document.createElement("select");
  sel.style.height = "30px"; sel.style.fontSize = "11px";
  sel.appendChild(opt("", name + ": none", !current));
  options.forEach(o => sel.appendChild(opt(o.value, name + ": " + o.label, o.value === current)));
  sel.addEventListener("change", () => onChange(sel.value));
  parent.appendChild(sel);
}
// map a chosen accessory code back to its spec dict (kind + distinguishing keys)
function accSpec(category, frame, code) {
  if (!code) return null;
  const o = accFor(category, frame).find(x => x.value === code);
  if (!o) return null;
  const out = { kind: category };
  (BREAKER_ACC_KEYS[category] || []).forEach(k => { if (o.rec[k] != null) out[k] = o.rec[k]; });
  return out;
}
// the breaker-mounted accessory selectors shared by feeders and the main breaker
function buildBreakerAccSelectors(cell, frame, acc, onChange) {
  cell.innerHTML = "";
  const add = (name, cat, key) =>
    addAccSelect(cell, name, accFor(cat, frame), acc[key] || "", v => { acc[key] = v; onChange(); });
  add("Shunt", "shunt_trip", "shunt");
  add("UVR", "undervoltage_release", "uvr");
  add("Aux", "aux_contacts", "aux");
  add("Padlock", "padlock", "padlock");
  add("SE barrier", "service_entrance_barrier", "seb");
  return cell.children.length;
}
function breakerAccSpecs(frame, acc) {
  acc = acc || {};
  return [
    accSpec("shunt_trip", frame, acc.shunt),
    accSpec("undervoltage_release", frame, acc.uvr),
    accSpec("aux_contacts", frame, acc.aux),
    accSpec("padlock", frame, acc.padlock),
    accSpec("service_entrance_barrier", frame, acc.seb),
  ].filter(Boolean);
}

// ---------------------------------------------------------------- panel accessories
function initAccessories() {
  const spd = CAT.accessories.spd || [];
  fillSelect($("spdVoltage"), uniq(spd.map(r => r.voltage)), "480Y/277");
  const setSpdKa = () => fillSelect($("spdKa"),
    spd.filter(r => r.voltage === $("spdVoltage").value).map(r => r.ka), null);
  setSpdKa();
  $("spdVoltage").addEventListener("change", () => { setSpdKa(); recompute(); });
  $("spdOn").addEventListener("change", () => {
    [$("spdVoltage"), $("spdKa")].forEach(s => s.disabled = !$("spdOn").checked); recompute();
  });

  const rgm = CAT.accessories.rgm40 || [];
  fillSelect($("rgmFunction"), uniq(rgm.map(r => r.function)), "standard");
  fillSelect($("rgmProtocol"), uniq(rgm.map(r => r.protocol)), "Modbus RTU");
  fillSelect($("rgmVoltage"), uniq(rgm.map(r => r.voltage)), null);
  $("rgmOn").addEventListener("change", () => {
    ["rgmFunction", "rgmProtocol", "rgmVoltage"].forEach(id => $(id).disabled = !$("rgmOn").checked); recompute();
  });
  const relt = (CAT.accessories.relt || []).filter(r => r.type === "kit");
  fillSelect($("reltVoltage"), relt.map(r => r.volts), null);
  $("reltOn").addEventListener("change", () => { $("reltVoltage").disabled = !$("reltOn").checked; recompute(); });

  ["rgmFunction", "rgmProtocol", "rgmVoltage", "spdKa", "reltVoltage", "blankWidth", "blankFiller", "blankQty"]
    .forEach(id => $(id).addEventListener("change", recompute));
  $("blankQty").addEventListener("input", recompute);
}
function panelAccessories() {
  const out = [];
  if ($("spdOn").checked && $("spdKa").value)
    out.push({ kind: "spd", voltage: $("spdVoltage").value, ka: parseInt($("spdKa").value) });
  if ($("rgmOn").checked && $("rgmVoltage").value)
    out.push({ kind: "rgm40", function: $("rgmFunction").value, protocol: $("rgmProtocol").value, voltage: $("rgmVoltage").value });
  if ($("reltOn").checked && $("reltVoltage").value)
    out.push({ kind: "relt", type: "kit", volts: $("reltVoltage").value });
  if ($("blankWidth").value)
    out.push({ kind: "blank", width: parseInt($("blankWidth").value), filler: $("blankFiller").value === "true", qty: parseInt($("blankQty").value || "1") });
  return out;
}

// ---------------------------------------------------------------- build spec + recompute
function buildSpec() {
  const spec = {
    panel_amps: parseInt($("panelAmps").value),
    main_type: $("mainType").value,
    enclosure: $("enclosure").value,
    voltage: $("voltage").value,
    system: $("system").value,
    branches: [],
    accessories: panelAccessories(),
  };
  if (spec.main_type !== "MLO" && mainSel.frame) {
    const orient = document.querySelector('input[name=mainOrient]:checked');
    spec.main = clean({ ...mainSel, acc: undefined, qty: undefined, orientation: orient ? orient.value : "horizontal" });
    const macc = breakerAccSpecs(mainSel.frame, mainSel.acc);
    if (macc.length) spec.main.accessories = macc;
  }
  for (const row of feeders) {
    if (!row.sel.frame) continue;
    const b = clean({ ...row.sel, acc: undefined, qty: row.qty });
    const accs = breakerAccSpecs(row.sel.frame, row.acc);
    if (accs.length) b.accessories = accs;
    spec.branches.push(b);
  }
  return spec;
}
function clean(o) {
  const out = {};
  for (const k in o) if (o[k] !== "" && o[k] != null) out[k] = o[k];
  // numeric coercion
  ["poles", "amps", "qty"].forEach(k => { if (out[k] != null) out[k] = parseInt(out[k]); });
  return out;
}

function recompute() {
  clearTimeout(recomputeTimer);
  recomputeTimer = setTimeout(() => {
    const spec = buildSpec();
    fetch("/api/bom", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(spec) })
      .then(r => r.json()).then(renderResult).catch(err => renderResult({ status: "error", reason: String(err) }));
  }, 250);
}
function renderResult(res) { renderBom(res); renderDrawing(res); }

// ---------------------------------------------------------------- render BOM
function setChip(status, text) {
  const c = $("statusChip");
  c.className = "status-chip " + (status || "");
  c.textContent = text;
}
function renderBom(res) {
  const out = $("bomOutput");
  out.innerHTML = "";

  if (res.status === "refused") {
    setChip("refused", "FACTORY-ASSEMBLED REQUIRED");
    out.appendChild(banner("refused", res.validation.flags[0] + (res.reason ? "\nReason: " + res.reason : "")));
    return;
  }
  if (res.status === "error") {
    setChip("refused", "NEEDS INPUT");
    out.appendChild(banner("error", res.reason || "error"));
    return;
  }
  if (res.status === "ambiguous") {
    setChip("ambiguous", "AMBIGUOUS");
    out.appendChild(banner("ambiguous",
      "Loadout fits multiple SuperBox sizes — narrow the ampacity to pick one.\nOptions: " +
      (res.validation.options || []).join(", ")));
    return;
  }

  setChip("ok", "OK — " + res.validation.selected_superbox);

  // BOM table
  const tbl = document.createElement("table");
  tbl.className = "bom";
  tbl.innerHTML = `<thead><tr><th class="qty">Qty</th><th>Part number</th><th>Description</th><th class="pg">Pg</th></tr></thead>`;
  const tb = document.createElement("tbody");
  for (const l of res.bom) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td class="qty">${l.qty}</td><td class="pn">${l.part_number}</td><td>${l.description}</td><td class="pg">${l.page}</td>`;
    tb.appendChild(tr);
  }
  tbl.appendChild(tb);
  out.appendChild(tbl);

  // validation
  const v = res.validation, x = v.xspace;
  const wrap = document.createElement("div");
  wrap.className = "validation";
  wrap.appendChild(vbox("Selected SuperBox", [
    kv("Product", v.selected_superbox),
    kv("Why", v.why),
  ]));
  wrap.appendChild(vbox("XT1 grouping", [
    kv("Count", v.xt1_grouping.count),
    kv("Groups", "[" + v.xt1_grouping.groups.join(", ") + "]  (" + v.xt1_grouping.total_xspace + "X)"),
    pills("Rails", v.xt1_grouping.rails),
  ]));
  wrap.appendChild(vbox("X-space — left", [bar(x.left_used, x.left_capacity)]));
  wrap.appendChild(vbox("X-space — right", [bar(x.right_used, x.right_capacity)]));
  out.appendChild(wrap);

  if (v.flags && v.flags.length) out.appendChild(banner("ambiguous", v.flags.join("\n")));
}

function banner(kind, text) {
  const d = document.createElement("div");
  d.className = "banner " + kind;
  d.style.whiteSpace = "pre-line";
  d.textContent = (kind === "refused" ? "⚠ " : "") + text;
  return d;
}
function vbox(title, children) {
  const d = document.createElement("div"); d.className = "vbox";
  d.innerHTML = `<h3>${title}</h3>`;
  children.forEach(c => d.appendChild(c));
  return d;
}
function kv(k, val) {
  const d = document.createElement("div"); d.className = "kv";
  d.innerHTML = `<span>${k}</span><span>${val}</span>`; return d;
}
function pills(k, arr) {
  const d = document.createElement("div"); d.className = "kv";
  const list = (arr && arr.length) ? arr.map(a => `<span class="pill">${a}</span>`).join(" ") : '<span class="muted">none</span>';
  d.innerHTML = `<span>${k}</span><span class="pill-list">${list}</span>`; return d;
}
function bar(used, cap) {
  const pct = cap ? Math.min(100, Math.round(used / cap * 100)) : 0;
  const cls = used > cap ? "over" : (pct >= 85 ? "warn" : "");
  const d = document.createElement("div");
  d.innerHTML = `<div class="bar"><i class="${cls}" style="width:${pct}%"></i></div>
                 <div class="bar-label"><span>${used}X used</span><span>${cap}X capacity</span></div>`;
  return d;
}

// ---------------------------------------------------------------- drawing tab
const FRAME_COLOR = {
  XT1: "#5b8def", XT2: "#3f6fd1", XT4: "#2f9e7c", XT5: "#e0892f", XT6: "#d2552a",
  XT7: "#b03a2e", TEY: "#8e7cc3", FB: "#7a9b3f", A2: "#c2417a", MLO: "#888", default: "#7a8691"
};
const shortLabel = (it) => {
  const a = /(\d+)\s*A/.exec(it.label);
  const main = /main/i.test(it.label) ? "MAIN " : "";
  return main + it.frame + (a ? " " + a[1] + "A" : "");
};
document.getElementById("printBtn").addEventListener("click", () => window.print());

function renderDrawing(res) {
  const out = $("drawingOutput");
  out.innerHTML = "";
  if (res.status !== "ok") {
    const reason = res.reason || (res.validation && res.validation.flags && res.validation.flags[0]) || "incomplete configuration";
    out.appendChild(banner(res.status === "refused" ? "refused" : "error", "No drawing — " + reason));
    return;
  }
  const v = res.validation, sp = v.specs, lay = v.layout, x = v.xspace;

  const sheet = document.createElement("div");
  sheet.className = "sheet";

  // ----- left: panel marks -----
  const marks = document.createElement("div");
  marks.className = "marks";
  const m = sp.main;
  const boxLines = res.bom.filter(l => /SuperBox/.test(l.item));
  const intLines = res.bom.filter(l => !/SuperBox/.test(l.item));
  const spec = (k, val) => `<div class="spec"><span>${k}</span><span>${val}</span></div>`;
  const miniBom = (lines) => `<table class="minibom"><thead><tr><th class="q">Qty</th><th>Cat #</th><th>Description</th></tr></thead>
    <tbody>${lines.map(l => `<tr><td class="q">${l.qty}</td><td class="c">${l.part_number}</td><td>${l.description}</td></tr>`).join("")}</tbody></table>`;

  marks.innerHTML =
    `<h3>Panel marks &mdash; technical specifications</h3>` +
    spec("Panel type", sp.panel_type) +
    spec("Amps", sp.amps + " A") +
    spec("Voltage", sp.voltage) +
    spec("System", sp.system) +
    spec("KAIC (SCCR)", sp.kaic != null ? sp.kaic + " kA" : "&mdash;") +
    spec("Main type", sp.main_type) +
    spec("Enclosure", sp.enclosure) +
    spec("Mounting", sp.mounting) +
    spec("Ground fault on main", sp.gf_on_main ? "Yes" : "No") +
    spec("Dimensions (H&times;W&times;D)", sp.dims_in.join(" &times; ") + " in") +
    `<h3>Main disconnect device</h3>` +
    spec("Type", m.type) +
    spec("Catalog no.", m.catalog) +
    spec("Amps", m.amps ? m.amps + " A" : "&mdash;") +
    spec("Poles", m.poles) +
    spec("Int. rating", m.int_rating || "&mdash;") +
    spec("Load lug", m.lug || "&mdash;") +
    spec("Orientation", m.orientation) +
    `<h3>Interior X-values</h3>` +
    spec("Total X used", (x.left_used + x.right_used) + " X") +
    spec("Available X", (x.left_capacity + x.right_capacity) + " X") +
    spec("Left used / cap", x.left_used + " / " + x.left_capacity + " X") +
    spec("Right used / cap", x.right_used + " / " + x.right_capacity + " X") +
    `<h3>Box BOM</h3>` + miniBom(boxLines) +
    `<h3>Interior BOM</h3>` + miniBom(intLines);

  // ----- right: layout diagram -----
  const diagram = document.createElement("div");
  diagram.className = "diagram";
  diagram.innerHTML =
    `<div class="title">${lay.sku} &mdash; ${lay.amps} A ${lay.main_type} ${lay.enclosure}</div>` +
    drawLayoutSVG(lay) +
    `<div class="dims">Enclosure ${lay.dims_in.join('" &times; ')}"  &middot;  left ${x.left_used}/${x.left_capacity}X &middot; right ${x.right_used}/${x.right_capacity}X</div>` +
    legend(lay);

  sheet.appendChild(marks);
  sheet.appendChild(diagram);
  out.appendChild(sheet);
}

function legend(lay) {
  const frames = [...new Set([...lay.left, ...lay.right].map(i => i.frame))];
  if (!frames.length) return "";
  return `<div class="legend">${frames.map(f =>
    `<span><i style="background:${FRAME_COLOR[f] || FRAME_COLOR.default}"></i>${f}</span>`).join("")}</div>`;
}

const isMainItem = (it) => /^Main/i.test(it.label);

function drawLayoutSVG(lay) {
  const unit = 16, colW = 130, gap = 28;
  const LM = 46, RM = 14, TM = 28, BM = 40;        // margins for dim lines + titles
  const maxCap = Math.max(lay.cap_left, lay.cap_right, 1);
  const innerH = maxCap * unit, innerW = colW * 2 + gap;
  const W = LM + innerW + RM, H = TM + innerH + BM;
  const x0L = LM, x0R = LM + colW + gap, yTop = TM, yBot = TM + innerH;

  // a panel side: feeders stacked from the top, main at the bottom, spacer between
  const side = (feeders, mainItem, cap, x0, title) => {
    let s = `<text x="${x0 + colW / 2}" y="${TM - 8}" text-anchor="middle" font-size="11" font-weight="700">${title}</text>`;
    s += `<rect x="${x0}" y="${yTop}" width="${colW}" height="${cap * unit}" fill="#fcfcfc" stroke="#c7ccd0"/>`;
    for (let i = 0; i < cap; i++) {                 // position guides + numbers
      const y = yTop + i * unit;
      if (i) s += `<line x1="${x0}" y1="${y}" x2="${x0 + colW}" y2="${y}" stroke="#eef1f3"/>`;
      s += `<text x="${x0 - 6}" y="${y + 11}" text-anchor="end" font-size="8" fill="#9aa3aa">${i + 1}</text>`;
    }
    const block = (it, y, h, main) => {
      const col = FRAME_COLOR[it.frame] || FRAME_COLOR.default;
      return `<rect x="${x0 + 2}" y="${y + 1}" width="${colW - 4}" height="${h - 2}" rx="2"
                fill="${col}" opacity="${main ? 1 : 0.9}" stroke="${main ? '#111' : 'none'}" stroke-width="${main ? 1.5 : 0}"/>
              <text x="${x0 + colW / 2}" y="${y + h / 2 + 4}" text-anchor="middle" font-size="10" fill="#fff" font-weight="700">${shortLabel(it)}</text>`;
    };
    let used = 0;
    for (const it of feeders) { s += block(it, yTop + used * unit, it.xspace * unit, false); used += it.xspace; }
    const mainX = mainItem ? mainItem.xspace : 0;
    if (mainItem) s += block(mainItem, yBot - mainX * unit, mainX * unit, true);
    const spacerX = cap - used - mainX;
    if (spacerX > 0) {
      const y = yTop + used * unit, h = spacerX * unit;
      s += `<text x="${x0 + colW / 2}" y="${y + h / 2 + 4}" text-anchor="middle" font-size="9" fill="#aab0b5">${spacerX}X spacer</text>`;
    }
    return s;
  };

  // dimension line helpers (with arrow markers)
  const vdim = (x, label) =>
    `<line x1="${x}" y1="${yTop}" x2="${x}" y2="${yBot}" stroke="#555" marker-start="url(#a)" marker-end="url(#a)"/>
     <text x="${x - 5}" y="${(yTop + yBot) / 2}" text-anchor="middle" font-size="9" fill="#555" transform="rotate(-90 ${x - 5} ${(yTop + yBot) / 2})">${label}</text>`;
  const hdim = (y, label) =>
    `<line x1="${x0L}" y1="${y}" x2="${x0R + colW}" y2="${y}" stroke="#555" marker-start="url(#a)" marker-end="url(#a)"/>
     <text x="${(x0L + x0R + colW) / 2}" y="${y - 4}" text-anchor="middle" font-size="9" fill="#555">${label}</text>`;

  const leftFeeders = lay.left.filter(it => !isMainItem(it));
  const mainItem = lay.left.find(isMainItem) || null;

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px" xmlns="http://www.w3.org/2000/svg">
    <defs><marker id="a" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
      <path d="M0,4 L8,1 L8,7 Z" fill="#555"/></marker></defs>
    ${side(leftFeeders, mainItem, lay.cap_left, x0L, "LEFT (wide)")}
    ${side(lay.right, null, lay.cap_right, x0R, "RIGHT")}
    ${vdim(LM - 26, lay.dims_in[0] + '" H')}
    ${hdim(yBot + 22, lay.dims_in[1] + '" W · ' + (lay.amps === 600 ? '40' : '45') + '" offset')}
  </svg>`;
}
