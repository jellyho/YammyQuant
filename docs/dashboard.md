# The web dashboard (cockpit)

The dashboard is how you **monitor everything live** and leave the operator
instructions. It's a dependency-free single-page app served by FastAPI — no build
step, charts via Plotly.

```bash
yq dashboard          # → http://127.0.0.1:8000
```

It reads the same shared state the CLI writes (`yammyquant_state.db` + the DuckDB
candle store), and pushes a fresh snapshot over a WebSocket on an interval — so
anything the operator does shows up in real time, and the badge in the header
flips between **live** and **reconnecting…**.

!!! note "Screenshots"
    Live captures are best taken on your own machine (`yq dashboard`) — the panels
    below describe exactly what each one shows. Drop screenshots into
    `docs/assets/` and they can be embedded here.

## Header

- **connection badge** — `live` (green) when the WebSocket is streaming.
- **live trading** — `ON` (red) only when `YQ_ALLOW_LIVE=1`; otherwise `off`.
- **equity** — the latest equity point.

## Panels

| Panel | What it shows / does |
|---|---|
| **Chart** | Candlestick price + equity curve for a chosen `ticker` / `interval` (`yq collect` to populate). |
| **Pending approvals** | Live orders awaiting a human — **approve** / **reject** buttons (the live gate). |
| **Positions** | Open positions with quantity & average price; **close** flattens one (paper). |
| **Recent trades** | The fill log (paper + live), newest first. |
| **Strategies** | Every registered strategy as a toggle — enable/disable feeds straight into `yq decide`. |
| **Signals** | Latest per-symbol strategy signals (BUY/SELL/flat). |
| **Decisions (signal → order)** | Preview what `yq decide` would do, then submit as paper orders. |
| **Performance** | Realized PnL, total return, max drawdown, Sharpe, win rate, cash. |
| **News** | Collected headlines with source, tagged symbol, and sentiment; a **collect** button. |
| **Watchlist** | The universe for cycles — add/remove symbols. |
| **Leave an instruction** | A box that writes to the operator's **inbox** — what Claude Code reads via `yq recall` / `yq inbox` next run. |
| **Operator activity / Journal** | The live activity log and the cross-session journal. |

## How you actually use it

1. Leave the operator an instruction in the **inbox** ("rotate 20% into KR stocks").
2. Watch **Signals** and **Decisions** populate as cycles run.
3. When a **live** order needs you, it lands in **Pending approvals** (and fires a
   Discord notification if `DISCORD_WEBHOOK_URL` is set) — you approve or reject.
4. Track the outcome in **Performance** and the equity chart.

The conversation happens in Claude Code; the dashboard is the glass cockpit over
the top. See the [Tutorial](tutorial.md) for the end-to-end loop.
