"use strict";

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => (n === null || n === undefined ? "–" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }));

// ---- live state via WebSocket (falls back to polling) --------------------
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => setConn(true);
  ws.onclose = () => { setConn(false); setTimeout(connect, 3000); };
  ws.onerror = () => ws.close();
  ws.onmessage = (e) => render(JSON.parse(e.data));
}
function setConn(ok) {
  const el = $("conn");
  el.textContent = ok ? "live" : "reconnecting…";
  el.style.color = ok ? "var(--green)" : "var(--amber)";
}

/**
 * Updates the trading dashboard with data from a snapshot.
 * @param {Object} s - The snapshot object containing current trading state.
 */
function render(s) {
  $("live").textContent = "live trading: " + (s.live_trading_allowed ? "ON" : "off");
  $("live").style.color = s.live_trading_allowed ? "var(--red)" : "var(--muted)";

  const eq = s.equity && s.equity.length ? s.equity[s.equity.length - 1].equity : null;
  $("equity").textContent = "equity: " + fmt(eq);

  renderPending(s.pending_trades || []);
  renderPositions(s.positions || []);
  renderTrades(s.trades || []);
  renderRows("signals", (s.signals || []).map(x =>
    `<td>${x.ts}</td><td>${x.ticker}</td><td>${x.strategy}</td><td class="${x.action.toLowerCase()}">${x.action}</td>`));
  renderInbox(s.inbox || []);
  renderActivity(s.activity || []);
  renderJournal(s.journal || []);
  renderWatchlist(s.watchlist || []);
  renderNews(s.news || []);
  drawEquity(s.equity || []);
  loadStrategies();
}

/**
 * Renders a news feed from an array of news objects.
 * @param {Array} rows - News items, each with title, source, and optional symbol, sentiment, url, and timestamp properties.
 */
function renderNews(rows) {
  const tone = (x) => x > 0.1 ? "buy" : (x < -0.1 ? "sell" : "");
  $("news").innerHTML = rows.map(n =>
    `<li><span class="ts">${n.published || n.ts || ""}</span>` +
    `<span class="kind">${escapeHtml(n.source || "")}</span>` +
    (n.symbol ? `<span class="pill">${n.symbol}</span> ` : " ") +
    (n.sentiment != null ? `<b class="${tone(n.sentiment)}">${n.sentiment}</b> ` : "") +
    (n.url ? `<a href="${n.url}" target="_blank" rel="noopener">${escapeHtml(n.title)}</a>`
           : escapeHtml(n.title)) + `</li>`).join("");
}
$("collectNews").onclick = async () => {
  const r = await fetch("/api/news/collect", { method: "POST" });
  if (!r.ok) alert((await r.json()).detail || "collect failed");
};

/**
 * Renders journal entries with optional tags to the journal list.
 * @param {Array} rows - Journal entries to render.
 */
function renderJournal(rows) {
  $("journal").innerHTML = rows.map(j =>
    `<li><span class="ts">${j.ts}</span>${j.tag ? `<span class="kind">${escapeHtml(j.tag)}</span>` : ""} ${escapeHtml(j.text)}</li>`).join("");
}

function renderWatchlist(rows) {
  $("watchlist").querySelector("tbody").innerHTML = rows.map(w => `<tr>
    <td>${w.symbol}</td><td>${w.exchange || "-"}</td><td>${w.interval || "-"}</td>
    <td>${escapeHtml(w.note || "")}</td>
    <td><button class="ghost" onclick="rmWatch('${w.symbol}')">remove</button></td>
  </tr>`).join("") || `<tr><td colspan="5" class="muted">empty</td></tr>`;
}

const RISK_FIELDS = ["max_order_value", "max_position_value", "max_open_positions",
                     "max_symbol_weight", "daily_loss_limit", "cooldown_minutes"];
async function loadRisk() {
  const r = await fetch("/api/risk"); if (!r.ok) return;
  const p = await r.json();
  $("risk").innerHTML = RISK_FIELDS.map(f =>
    `<label>${f}<input id="risk_${f}" value="${p[f] ?? ""}" placeholder="none" /></label>`).join("");
}
$("saveRisk").onclick = async () => {
  const body = {};
  RISK_FIELDS.forEach(f => { body[f] = $("risk_" + f).value.trim() || null; });
  await post("/api/risk", body); loadRisk();
};

async function loadReport() {
  const r = await fetch("/api/report"); if (!r.ok) return;
  const d = await r.json();
  const cell = (k, v) => `<div class="stat"><span>${k}</span><b>${v ?? "–"}</b></div>`;
  $("report").innerHTML =
    cell("equity", fmt(d.equity_now)) + cell("total return", d.total_return) +
    cell("realized PnL", fmt(d.realized_pnl)) + cell("max DD", d.max_drawdown) +
    cell("sharpe", d.sharpe) + cell("win rate", d.win_rate) +
    cell("closed", d.closed_trades) + cell("cash", fmt(d.cash));
}
$("refreshReport").onclick = loadReport;

function renderDecisions(proposals) {
  $("decisions").querySelector("tbody").innerHTML = (proposals || []).map(p => `<tr>
    <td class="${p.side.toLowerCase()}">${p.side}</td><td>${p.symbol}</td>
    <td>${fmt(p.quantity, 6)}</td><td>${fmt(p.price)}</td>
    <td>${escapeHtml(p.reason || "")}</td><td>${p.status || "(dry-run)"}</td>
  </tr>`).join("") || `<tr><td colspan="6" class="muted">no decisions</td></tr>`;
}
$("previewDecide").onclick = async () => {
  const r = await fetch("/api/decide");
  if (!r.ok) { alert((await r.json()).detail || "decide failed"); return; }
  renderDecisions((await r.json()).proposals);
};
$("execDecide").onclick = async () => {
  if (!confirm("Submit these decisions as PAPER orders?")) return;
  const r = await fetch("/api/decide", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "paper" }) });
  if (!r.ok) { alert((await r.json()).detail || "decide failed"); return; }
  renderDecisions((await r.json()).proposals);
};

$("watchAdd").onclick = async () => {
  const symbol = $("watchSymbol").value.trim();
  if (symbol && await post("/api/watch", { symbol, interval: $("watchInterval").value.trim() || "1d" }))
    $("watchSymbol").value = "";
};
window.rmWatch = (symbol) => fetch(`/api/watch/${symbol}`, { method: "DELETE" });
$("journalAdd").onclick = async () => {
  const text = $("journalText").value.trim();
  if (text && await post("/api/journal", { text, tag: $("journalTag").value.trim() })) {
    $("journalText").value = ""; $("journalTag").value = "";
  }
};

async function loadStrategies() {
  const r = await fetch("/api/strategies");
  if (!r.ok) return;
  const items = await r.json();
  $("strategies").innerHTML = items.map(s =>
    `<span class="strat-row">
       <button class="${s.enabled ? 'ok' : 'ghost'}" onclick="toggleStrategy('${s.name}', ${!s.enabled})">
         ${s.enabled ? '●' : '○'} ${s.name}</button>
       <input class="wt" title="ensemble vote weight" value="${s.weight}"
              onchange="setWeight('${s.name}', this.value)" />
     </span>`).join("");
  // keep the Research strategy dropdown in sync
  const sel = $("rsStrategy");
  if (sel && sel.options.length !== items.length) {
    sel.innerHTML = items.map(s => `<option>${s.name}</option>`).join("");
  }
}
window.toggleStrategy = async (name, enable) => {
  await post("/api/settings", { key: `strategy.${name}.enabled`, value: enable });
  loadStrategies();
};
window.setWeight = async (name, value) => {
  await post("/api/settings", { key: `strategy.${name}.weight`, value: parseFloat(value) || 0 });
};

function renderRows(id, rowsHtml) {
  $(id).querySelector("tbody").innerHTML = rowsHtml.map(r => `<tr>${r}</tr>`).join("");
}

function renderPending(rows) {
  $("pending").querySelector("tbody").innerHTML = rows.map(t => `<tr>
    <td>${t.id}</td><td>${t.mode}</td><td class="${t.side.toLowerCase()}">${t.side}</td>
    <td>${t.ticker}</td><td>${fmt(t.quantity, 6)}</td><td>${fmt(t.price)}</td>
    <td class="muted" title="${escapeHtml(t.rationale || "")}">${escapeHtml((t.rationale || "").slice(0, 60))}</td>
    <td><button class="ok" onclick="approve(${t.id})">approve</button>
        <button class="danger" onclick="reject(${t.id})">reject</button></td>
  </tr>`).join("") || `<tr><td colspan="8" class="muted">none</td></tr>`;
}

function renderPositions(rows) {
  $("positions").querySelector("tbody").innerHTML = rows.map(p => `<tr>
    <td>${p.ticker}</td><td>${fmt(p.quantity, 6)}</td><td>${fmt(p.avg_price)}</td>
    <td><button class="ghost" onclick="closePos('${p.ticker}', ${p.avg_price})">close</button></td>
  </tr>`).join("") || `<tr><td colspan="4" class="muted">flat</td></tr>`;
}

function renderTrades(rows) {
  renderRows("trades", rows.map(t =>
    `<td>${t.id}</td><td>${t.ts}</td><td class="${t.side.toLowerCase()}">${t.side}</td>
     <td>${t.ticker}</td><td>${fmt(t.quantity, 6)}</td><td>${fmt(t.price)}</td>
     <td>${t.mode}</td><td><span class="pill ${t.status}">${t.status}</span></td>`));
}

function renderInbox(rows) {
  $("inbox").innerHTML = rows.map(m =>
    `<li><span class="ts">${m.ts}</span><span class="pill ${m.status === "unread" ? "pending" : "filled"}">${m.status}</span> ${escapeHtml(m.message)}</li>`).join("");
}

function renderActivity(rows) {
  $("activity").innerHTML = rows.map(a =>
    `<li><span class="ts">${a.ts}</span><span class="kind">${a.kind}</span> ${escapeHtml(a.summary)}</li>`).join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// ---- actions -------------------------------------------------------------
async function post(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) alert((await r.json()).detail || "request failed");
  return r.ok;
}
window.approve = (id) => post(`/api/trades/${id}/approve`);
window.reject = (id) => post(`/api/trades/${id}/reject`);
window.closePos = (ticker, price) => {
  const p = prompt(`Close ${ticker} at price:`, price);
  if (p) post(`/api/positions/${ticker}/close`, { price: parseFloat(p) });
};
$("send").onclick = async () => {
  const msg = $("msg").value.trim();
  if (msg && await post("/api/inbox", { message: msg })) $("msg").value = "";
};

// ---- charts --------------------------------------------------------------
const layout = (title) => ({
  title: { text: title, font: { size: 12, color: "#7d8794" }, x: 0 },
  paper_bgcolor: "transparent", plot_bgcolor: "transparent",
  font: { color: "#7d8794", size: 11 }, margin: { t: 28, r: 10, b: 28, l: 48 },
  xaxis: { gridcolor: "#232a33" }, yaxis: { gridcolor: "#232a33" },
});

async function loadChart() {
  const ticker = $("ticker").value.trim().toUpperCase();
  const interval = $("interval").value;
  const r = await fetch(`/api/candles?ticker=${ticker}&interval=${interval}`);
  if (!r.ok) { Plotly.purge("price"); alert("no stored candles — run: yq collect " + ticker + " " + interval); return; }
  const c = await r.json();
  Plotly.react("price", [{
    type: "candlestick", x: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    increasing: { line: { color: "#3fb950" } }, decreasing: { line: { color: "#f85149" } },
  }], { ...layout(`${ticker} ${interval}`), xaxis: { rangeslider: { visible: false }, gridcolor: "#232a33" } }, { displayModeBar: false, responsive: true });
}
$("loadChart").onclick = loadChart;

function drawEquity(eq) {
  if (!eq.length) return;
  Plotly.react("equityPlot", [{
    type: "scatter", mode: "lines", x: eq.map(e => e.ts), y: eq.map(e => e.equity),
    line: { color: "#4da3ff", width: 2 }, fill: "tozeroy", fillcolor: "rgba(77,163,255,0.08)",
  }], layout("equity"), { displayModeBar: false, responsive: true });
}

// ---- control center ------------------------------------------------------
const CONTROL_FIELDS = ["auto_trade", "trade_mode", "ensemble_rule",
  "ensemble_threshold", "sentiment_gate", "sizing", "target_vol", "exchange"];

function parseVal(v) {
  if (v === "") return null;
  if (v === "true") return true;
  if (v === "false") return false;
  const n = Number(v);
  return (!isNaN(n) && v !== "") ? n : v;
}

async function loadControl() {
  const r = await fetch("/api/settings"); if (!r.ok) return;
  const s = await r.json();
  $("control").innerHTML = CONTROL_FIELDS.map(f =>
    `<label>${f}<input id="ctl_${f}" value="${s[f] ?? ""}" placeholder="unset" /></label>`).join("");
}
$("saveControl").onclick = async () => {
  for (const f of CONTROL_FIELDS) {
    await post("/api/settings", { key: f, value: parseVal($("ctl_" + f).value.trim()) });
  }
  loadControl();
};
$("setAdd").onclick = async () => {
  const k = $("setKey").value.trim(); if (!k) return;
  if (await post("/api/settings", { key: k, value: parseVal($("setVal").value.trim()) })) {
    $("setKey").value = ""; $("setVal").value = ""; loadControl();
  }
};
$("runCycle").onclick = async () => {
  const r = await fetch("/api/cycle", { method: "POST" });
  alert(r.ok ? "cycle complete" : (await r.json()).detail || "cycle failed");
};
$("sendStatus").onclick = async () => {
  const r = await fetch("/api/notify", { method: "POST" });
  const d = await r.json();
  alert(r.ok ? "status sent to: " + ((d.channels || []).join(", ") || "(log only)") : "failed");
};

$("trSubmit").onclick = async () => {
  const body = { ticker: $("trTicker").value.trim(), side: $("trSide").value,
    quantity: $("trQty").value, price: $("trPrice").value, mode: $("trMode").value };
  const r = await fetch("/api/trade", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  $("trResult").textContent = r.ok ? `#${d.id} → ${d.status}` : (d.detail || "failed");
};

$("setTargets").onclick = async () => {
  const t = {};
  $("targetSpec").value.trim().split(/\s+/).forEach(p => {
    const [k, v] = p.split("="); if (k && v) t[k] = parseFloat(v);
  });
  const r = await fetch("/api/target", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(t) });
  const d = await r.json();
  $("targetResult").textContent = r.ok ? "targets: " + JSON.stringify(d.targets) : "failed";
};
$("riskParity").onclick = async () => {
  // parse symbols from the spec box: bare symbols, or the keys of SYM=w pairs
  const symbols = $("targetSpec").value.trim().toUpperCase().split(/[\s,]+/)
    .map(t => t.split("=")[0]).filter(Boolean);
  if (!symbols.length) { $("targetResult").textContent = "enter symbols"; return; }
  const r = await fetch("/api/target/risk-parity", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbols }) });
  const d = await r.json();
  $("targetResult").textContent = r.ok
    ? "risk-parity targets: " + JSON.stringify(d.targets) : (d.detail || "failed");
};
$("rebalanceBtn").onclick = async () => {
  const r = await fetch("/api/rebalance", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ execute: true }) });
  const d = await r.json();
  $("targetResult").textContent = r.ok
    ? `rebalanced: ${(d.orders || d.proposals || []).length} order(s)` : (d.detail || "failed");
};

function renderResearch(title, obj) {
  const cell = (k, v) => `<div class="stat"><span>${escapeHtml(k)}</span><b>${escapeHtml(
    typeof v === "object" ? JSON.stringify(v) : v)}</b></div>`;
  const flat = {};
  Object.entries(obj).forEach(([k, v]) => { if (typeof v !== "object" || v === null) flat[k] = v; });
  $("research").innerHTML = `<div class="stat"><span>—</span><b>${title}</b></div>` +
    Object.entries(flat).map(([k, v]) => cell(k, v)).join("");
}
async function research(path, extra) {
  const body = { ticker: $("rsTicker").value.trim().toUpperCase(),
    interval: $("rsInterval").value.trim(), strategy: $("rsStrategy").value, ...extra };
  $("research").innerHTML = `<div class="stat"><span>…</span><b>running</b></div>`;
  const r = await fetch(path, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  if (!r.ok) { $("research").innerHTML = `<div class="stat"><span>error</span><b>${escapeHtml(d.detail || "failed")}</b></div>`; Plotly.purge("researchPlot"); return; }
  renderResearch(`${body.strategy} ${body.ticker} ${body.interval}`, d);
  // walk-forward: grouped bars of in-sample vs out-of-sample score per fold
  if (d.folds && d.folds.length) {
    const x = d.folds.map(f => "fold " + f.fold);
    const metric = d.metric || "sharpe";
    Plotly.react("researchPlot", [
      { type: "bar", name: "in-sample", x, y: d.folds.map(f => f.in_sample_score),
        marker: { color: "#4da3ff" } },
      { type: "bar", name: "out-of-sample",
        x, y: d.folds.map(f => (f.out_of_sample || {})[metric] ?? null),
        marker: { color: "#3fb950" } },
    ], { ...layout(`walk-forward ${metric}: in-sample vs out-of-sample`), barmode: "group",
      showlegend: true }, { displayModeBar: false, responsive: true });
    Plotly.purge("researchSignals"); Plotly.purge("researchDrawdown"); Plotly.purge("researchMonthly");
    return;
  }
  if (d.equity && d.equity.length) {
    const traces = [{ type: "scatter", mode: "lines", name: "strategy",
      x: d.equity.map(e => e.ts), y: d.equity.map(e => e.equity),
      line: { color: "#3fb950", width: 2 }, fill: "tozeroy", fillcolor: "rgba(63,185,80,0.08)" }];
    // buy-and-hold benchmark overlay (dashed) — beat-the-market check
    if (d.equity[0].bench !== undefined) {
      traces.push({ type: "scatter", mode: "lines", name: "buy & hold",
        x: d.equity.map(e => e.ts), y: d.equity.map(e => e.bench),
        line: { color: "#7d8794", width: 1.4, dash: "dot" } });
    }
    const bt = (d.benchmark_return != null)
      ? `backtest equity — vs buy & hold (${(d.benchmark_return * 100).toFixed(1)}%)` : "backtest equity";
    Plotly.react("researchPlot", traces,
      { ...layout(bt), showlegend: true }, { displayModeBar: false, responsive: true });
    // underwater (drawdown) chart: how far below the running peak, in %
    if (d.equity[0].dd !== undefined) {
      Plotly.react("researchDrawdown", [{ type: "scatter", mode: "lines",
        x: d.equity.map(e => e.ts), y: d.equity.map(e => (e.dd * 100)),
        line: { color: "#f85149", width: 1.3 }, fill: "tozeroy",
        fillcolor: "rgba(248,81,73,0.12)" }],
        { ...layout("drawdown (% below peak)"), yaxis: { ticksuffix: "%" } },
        { displayModeBar: false, responsive: true });
    } else { Plotly.purge("researchDrawdown"); }
    // monthly returns heatmap (calendar consistency / seasonality)
    const mo = d.monthly;
    if (mo && mo.years && mo.years.length) {
      const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      const pct = mo.matrix.map(row => row.map(v => v == null ? null : v * 100));
      Plotly.react("researchMonthly", [{
        type: "heatmap", z: pct, x: months, y: mo.years.map(String),
        zmid: 0, colorscale: [[0, "#f85149"], [0.5, "#0e1116"], [1, "#3fb950"]],
        text: pct.map(row => row.map(v => v == null ? "" : v.toFixed(1) + "%")),
        texttemplate: "%{text}", textfont: { size: 10 }, hoverongaps: false,
        xgap: 1, ygap: 1,
      }], { ...layout("monthly returns (%)") }, { displayModeBar: false, responsive: true });
    } else { Plotly.purge("researchMonthly"); }
  } else { Plotly.purge("researchPlot"); Plotly.purge("researchDrawdown"); Plotly.purge("researchMonthly"); }
  // price with buy/sell markers overlay
  if (d.price && d.price.length) {
    const tr = d.trades || [];
    const buys = tr.filter(t => t.side === "BUY"), sells = tr.filter(t => t.side === "SELL");
    Plotly.react("researchSignals", [
      { type: "scatter", mode: "lines", name: "price",
        x: d.price.map(p => p.ts), y: d.price.map(p => p.close),
        line: { color: "#7d8794", width: 1.3 } },
      { type: "scatter", mode: "markers", name: "buy",
        x: buys.map(t => t.ts), y: buys.map(t => t.price),
        marker: { color: "#3fb950", size: 9, symbol: "triangle-up" } },
      { type: "scatter", mode: "markers", name: "sell",
        x: sells.map(t => t.ts), y: sells.map(t => t.price),
        marker: { color: "#f85149", size: 9, symbol: "triangle-down" } },
    ], { ...layout("price + signals"), showlegend: false },
      { displayModeBar: false, responsive: true });
  } else { Plotly.purge("researchSignals"); }
}
$("rsBacktest").onclick = () => research("/api/backtest", {});
$("rsOptimize").onclick = () => research("/api/optimize", { walk_forward: parseInt($("rsWF").value) || 0 });
$("rsPortfolio").onclick = async () => {
  const symbols = $("rsSymbols").value.trim().toUpperCase().split(/[\s,]+/).filter(Boolean);
  if (!symbols.length) { $("research").innerHTML = `<div class="stat"><span>!</span><b>enter symbols</b></div>`; return; }
  $("research").innerHTML = `<div class="stat"><span>…</span><b>running</b></div>`;
  const r = await fetch("/api/portfolio", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols, interval: $("rsInterval").value.trim(),
      strategy: $("rsStrategy").value, risk_parity: $("rsRiskParity").checked }) });
  const d = await r.json();
  if (!r.ok) { $("research").innerHTML = `<div class="stat"><span>error</span><b>${escapeHtml(d.detail || "failed")}</b></div>`; Plotly.purge("researchPlot"); return; }
  renderResearch(`portfolio (${symbols.join(", ")}) ${$("rsStrategy").value}`, d.portfolio);
  Plotly.purge("researchSignals"); Plotly.purge("researchDrawdown"); Plotly.purge("researchMonthly");
  if (d.equity && d.equity.length) {
    Plotly.react("researchPlot", [{ type: "scatter", mode: "lines",
      x: d.equity.map(e => e.ts), y: d.equity.map(e => e.equity),
      line: { color: "#a371f7", width: 2 }, fill: "tozeroy", fillcolor: "rgba(163,113,247,0.08)" }],
      layout("portfolio equity"), { displayModeBar: false, responsive: true });
  }
}

// ---- plugin authoring & attribution --------------------------------------
async function loadPluginFiles() {
  const r = await fetch("/api/plugins/files"); if (!r.ok) return;
  const files = await r.json();
  $("plFile").innerHTML = `<option value="">— edit a file —</option>` +
    files.map(f => `<option value="${f.path}">${f.path}</option>`).join("");
}
window.openPluginFile = async (path) => {
  if (!path) { $("plEditor").value = ""; return; }
  const r = await fetch("/api/plugins/file?path=" + encodeURIComponent(path));
  const d = await r.json();
  $("plEditor").value = r.ok ? d.content : (d.detail || "");
  $("plEditor").dataset.path = path;
};
$("plNew").onclick = async () => {
  const body = { kind: $("plKind").value, name: $("plName").value.trim() };
  if (!body.name) return;
  const r = await fetch("/api/plugins/new", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const d = await r.json();
  $("plResult").textContent = r.ok ? "created " + d.created : (d.detail || "failed");
  $("plName").value = ""; loadPlugins(); loadPluginFiles();
};
$("plSave").onclick = async () => {
  const path = $("plEditor").dataset.path;
  if (!path) { $("plResult").textContent = "select a file first"; return; }
  const r = await fetch("/api/plugins/file", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content: $("plEditor").value }) });
  const d = await r.json();
  $("plResult").textContent = r.ok
    ? `saved · loaded: ${(d.reload.strategies || []).concat(d.reload.indicators || []).join(", ") || "—"}`
      + ((d.reload.errors || []).length ? ` · errors: ${d.reload.errors.join("; ")}` : "")
    : (d.detail || "failed");
  loadPlugins();
};

$("corrRun").onclick = async () => {
  const symbols = $("corrSymbols").value.trim().toUpperCase().split(/[\s,]+/).filter(Boolean);
  if (symbols.length < 2) { alert("enter at least two symbols"); return; }
  const r = await fetch("/api/correlation", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbols }) });
  const d = await r.json();
  if (!r.ok) { alert(d.detail || "failed"); Plotly.purge("corrPlot"); return; }
  Plotly.react("corrPlot", [{
    type: "heatmap", z: d.matrix, x: d.symbols, y: d.symbols,
    zmin: -1, zmax: 1, colorscale: [[0, "#f85149"], [0.5, "#0e1116"], [1, "#3fb950"]],
    text: d.matrix, texttemplate: "%{text}", textfont: { size: 11 },
  }], { ...layout(`return correlation (${d.bars} bars)`) },
    { displayModeBar: false, responsive: true });
};

$("cmpRun").onclick = async () => {
  const ticker = $("cmpTicker").value.trim().toUpperCase();
  const interval = $("cmpInterval").value.trim();
  const metric = $("cmpMetric").value;
  if (!ticker) { alert("enter a ticker"); return; }
  $("cmpRun").textContent = "ranking…"; $("cmpRun").disabled = true;
  try {
    const r = await fetch("/api/compare", { method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ticker, interval, metric }) });
    const d = await r.json();
    if (!r.ok) { alert(d.detail || "failed"); Plotly.purge("cmpPlot"); return; }
    const rows = d.ranking || [];
    // horizontal bars of the ranked metric, best at the top
    const ordered = rows.slice().reverse();
    Plotly.react("cmpPlot", [{
      type: "bar", orientation: "h",
      x: ordered.map(s => s[metric]), y: ordered.map(s => s.strategy),
      marker: { color: ordered.map(s => (s[metric] || 0) >= 0 ? "#3fb950" : "#f85149") },
    }], { ...layout(`${metric} by strategy · ${ticker} ${interval}`
            + (d.benchmark_return != null ? ` (buy&hold ${(d.benchmark_return * 100).toFixed(1)}%)` : "")),
          margin: { l: 130, r: 10, t: 30, b: 30 } },
      { displayModeBar: false, responsive: true });
    $("cmpTable").querySelector("tbody").innerHTML = rows.map((s, i) => `<tr>
      <td>${i + 1}</td><td>${s.strategy}</td><td><b>${fmt(s[metric])}</b></td>
      <td>${fmt(s.total_return)}</td>
      <td class="${(s.excess_return || 0) >= 0 ? 'buy' : 'sell'}">${fmt(s.excess_return)}</td>
      <td>${fmt(s.max_drawdown)}</td><td>${s.num_trades ?? "—"}</td></tr>`).join("")
      || `<tr><td colspan="7" class="muted">no results</td></tr>`;
  } finally { $("cmpRun").textContent = "rank all"; $("cmpRun").disabled = false; }
};

async function loadAttribution() {
  const r = await fetch("/api/attribution"); if (!r.ok) return;
  const rows = (await r.json()).by_strategy || [];
  $("attribution").querySelector("tbody").innerHTML = rows.map(s => `<tr>
    <td>${s.strategy}</td><td>${s.round_trips}</td>
    <td class="${s.pnl >= 0 ? 'buy' : 'sell'}">${fmt(s.pnl)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="muted">no closed round-trips yet</td></tr>`;
}
$("loadAttr").onclick = loadAttribution;

async function loadPlugins() {
  const r = await fetch("/api/plugins"); if (!r.ok) return;
  const d = await r.json();
  const cell = (k, v) => `<div class="stat"><span>${k}</span><b>${v}</b></div>`;
  $("plugins").innerHTML =
    cell("strategies", (d.strategies || []).join(", ") || "–") +
    cell("indicators", (d.indicators || []).join(", ") || "–") +
    cell("errors", (d.errors || []).length || 0);
}
$("reloadPlugins").onclick = loadPlugins;

connect();
loadChart();
loadRisk();
loadReport();
loadControl();
loadPlugins();
loadPluginFiles();
loadAttribution();
