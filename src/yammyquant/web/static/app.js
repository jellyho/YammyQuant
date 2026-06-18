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

// ---- render snapshot -----------------------------------------------------
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
  drawEquity(s.equity || []);
  loadStrategies();
}

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
    `<button class="${s.enabled ? 'ok' : 'ghost'}" onclick="toggleStrategy('${s.name}', ${!s.enabled})">
       ${s.enabled ? '●' : '○'} ${s.name}
     </button>`).join("");
}
window.toggleStrategy = async (name, enable) => {
  await post("/api/settings", { key: `strategy.${name}.enabled`, value: enable });
  loadStrategies();
};

function renderRows(id, rowsHtml) {
  $(id).querySelector("tbody").innerHTML = rowsHtml.map(r => `<tr>${r}</tr>`).join("");
}

function renderPending(rows) {
  $("pending").querySelector("tbody").innerHTML = rows.map(t => `<tr>
    <td>${t.id}</td><td>${t.mode}</td><td class="${t.side.toLowerCase()}">${t.side}</td>
    <td>${t.ticker}</td><td>${fmt(t.quantity, 6)}</td><td>${fmt(t.price)}</td>
    <td><button class="ok" onclick="approve(${t.id})">approve</button>
        <button class="danger" onclick="reject(${t.id})">reject</button></td>
  </tr>`).join("") || `<tr><td colspan="7" class="muted">none</td></tr>`;
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

connect();
loadChart();
loadRisk();
loadReport();
