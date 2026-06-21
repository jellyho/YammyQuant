# YammyQuant v0.2.0-rc.1 (pre-release)

First release candidate. The **research → paper** pipeline is feature-complete and
well-tested (386 tests); the **live** path is code-complete and duplicate/consistency-safe
but its exchange adapters have **not yet been verified against real venues** — see the
go-live checklist below. Treat this as a paper-trading / testnet build.

## Highlights since 0.1

**Backtest realism**
- Next-bar-open fills (no look-ahead), signed long/short positions, borrow cost on shorts.
- Per-exchange maker/taker fee schedules, applied automatically by venue; configurable slippage; resting LIMIT (maker) orders are not slipped.
- Risk layer: fixed/ATR stops, trailing, breakeven, scale-out, time stops, volatility/Kelly sizing, drawdown kill-switch.
- Statistical validation: PSR, Deflated Sharpe, bootstrap CI, walk-forward OOS, VaR/CVaR, Monte-Carlo / risk-of-ruin, alpha/beta, Ulcer, recovery factor.
- Intraday analytics: wall-clock avg holding time, trades/day.

**Strategies & signals**
- 26 strategies across trend / breakout / mean-reversion / scalping, all optimizable; `RegimeFilter` / `SessionFilter` meta-wrappers; ensemble vote rules (`any`/`weighted`/`majority`/`unanimous`).
- `yq decide` gates: session, sentiment, and a min-edge (cost-aware) gate for scalping.

**Paper mirrors live**
- Paper fills at the venue's real-time price, pays that venue's real fees, and incurs configurable slippage — so backtest → paper → live cost the same.

**Operating loop & safety**
- `yq promote`: backtest → paper → live readiness gate (account-level + per-strategy attribution); runs in `yq cycle`.
- Auto mode (hands-off live) behind four opt-ins (`YQ_ALLOW_LIVE=1` + `auto_approve` + `auto_trade` + `trade_mode=live`); risk policy still vets every order.
- Daily-loss **kill-switch** auto-disarms auto mode; **remote control** from Slack/Discord (`arm`/`disarm`/`pause`/`resume`/`flat`/`status`).
- Order lifecycle: failed live placements are rejected (not dangling), `yq cancel`, drift detection (positions + cash), `yq sync` + `yq reconcile` run each cycle.

**Live correctness**
- Live market fills are booked at the venue's *actual* price/qty/fee.
- Idempotent `client_order_id` per order + no re-placement of an already-placed trade.
- Single-flight `yq cycle` lock so manual and scheduled runs can't overlap.

**Surfaces**
- FastAPI cockpit dashboard (auto-mode toggle, fees/realism, data integrity, promotion readiness, …) and an MkDocs docs site.

## ⚠️ Go-live checklist (do this before risking real money)

1. **Verify exchange adapters against a real account** — `create_order` / `order_status` / `cancel_order` are only covered by mocked tests so far. Start on a testnet or with the smallest possible size: place → check status → cancel, per venue you'll use. (Toss request paths in particular are unconfirmed.)
2. **Keep it paper first.** Default mode is paper; run the full loop and review `yq report` / `yq promote` before considering live.
3. **Set risk guardrails** — `yq risk set max_open_positions=… max_order_value=… daily_loss_limit=…` before any live order.
4. **Live needs two gates** you set yourself: `export YQ_ALLOW_LIVE=1` **and** per-order approval (or, deliberately, auto mode).
5. **Reconcile** after the first live fills — `yq reconcile` (positions + cash) and confirm the local book matches the venue.

See `docs/safety.md` for the full money-safety model.
