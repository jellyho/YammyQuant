# Benchmark — YammyQuant vs. the 2025/2026 landscape

A survey of the most popular open-source trading repos, and how YammyQuant
compares. Used to drive the feature roadmap — the gaps this surfaced have been
implemented (see **Status** column).

## The field we benchmarked against

| Repo | What it is | Stars (approx.) |
| --- | --- | --- |
| [freqtrade](https://github.com/freqtrade/freqtrade) | Crypto bot: backtest + hyperopt + FreqAI (ML) + live, ccxt, Telegram/Web UI | ~40k |
| [nautilus_trader](https://github.com/nautechsystems/nautilus_trader) | Rust-core, event-driven, nanosecond, multi-venue; identical backtest/live code | ~9k |
| [Jesse](https://github.com/jesse-ai/jesse) | Crypto research/backtest; zero look-ahead bias, genetic optimizer, Monte Carlo | ~6.5k |
| [vectorbt](https://github.com/polakowo/vectorbt) | Vectorized, ultra-fast portfolio backtesting & analytics | ~5k |
| [FinRL](https://github.com/AI4Finance-Foundation/FinRL) | Deep RL for trading (envs, agents, pipelines) | ~10k |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | LLM analyst agents (Buffett/Munger/…) + risk & portfolio managers; **research only** | very high |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Multi-agent LLM firm (analysts→researchers→trader→risk→PM), LangGraph | high |
| [FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | LLM agent platform for financial analysis | high |

Sources: GitHub READMEs and 2025/2026 comparison write-ups (freqtrade docs,
nautilustrader.io, Jesse docs, the TradingAgents paper arXiv:2412.20138).

## Feature matrix

| Capability | freqtrade | Jesse | nautilus | ai-hedge-fund / TradingAgents | **YammyQuant** | Status |
| --- | :-: | :-: | :-: | :-: | :-: | --- |
| Backtest engine | ✅ | ✅ | ✅ | (calls a backtester) | ✅ event loop | — |
| Fees + slippage | ✅ | ✅ | ✅ | — | ✅ | — |
| Performance metrics | ✅ | ✅ | ✅ | partial | ✅ Sharpe/Sortino/Calmar/MDD/PF/CAGR/vol/trade stats | **added Sortino/Calmar/vol/trade stats** |
| Risk: stop-loss / take-profit | ✅ | ✅ | ✅ | (agent) | ✅ | **added** |
| Risk: position sizing | ✅ | ✅ | ✅ | (agent) | ✅ fraction / volatility-target | **added** |
| Risk: drawdown kill-switch | ✅ (protections) | ✅ | ✅ | (agent) | ✅ | **added** |
| Param optimization | ✅ hyperopt | ✅ genetic | partial | — | ✅ grid (+optuna optional) | **added** |
| Walk-forward validation | partial | partial | partial | — | ✅ | **added** |
| Multi-exchange data (ccxt) | ✅ 100+ | ✅ | ✅ | — | ✅ CCXTSource | **added** |
| ML / RL | ✅ FreqAI | plugin | bring-your-own | RL (FinRL) | ✅ Gymnasium env + `yq train` | — |
| Feature engineering | ✅ | ✅ | ✅ | (agent) | ✅ `data/features.py` | — |
| Paper trading | ✅ dry-run | ✅ | ✅ | (no exec) | ✅ default | — |
| Live trading | ✅ ccxt | 💰 paid plugin | ✅ | ❌ (research only) | ✅ gated (flag + approval) | — |
| Web dashboard | ✅ | ✅ | — | ✅ (some) | ✅ FastAPI + SPA cockpit | — |
| Notifications | ✅ Telegram | ✅ | — | — | ✅ Discord webhook | — |
| **Agentic operator** | ❌ | JesseGPT 💰 | ❌ | ✅ **but needs paid LLM API keys** | ✅ **Claude Code — no API cost** | differentiator |

## Where YammyQuant stands

**Differentiator — the agent is free.** ai-hedge-fund, TradingAgents, FinRobot
and JesseGPT are the exciting recent wave, but every one of them needs a paid
LLM API key (OpenAI/Anthropic/Gemini/…) and bills per run. YammyQuant's operator
is the **Claude Code session itself** — the same multi-agent reasoning
(research → signal → risk-checked decision) with **zero API cost**, driving a
typed, tested toolbelt. The dashboard is the cockpit; the conversation is Claude
Code.

**Gaps closed in this pass.** The benchmark showed YammyQuant was missing the
risk layer, optimization/walk-forward, expanded analytics, and multi-exchange
data that every serious framework ships. All four are now implemented and
tested:

- `backtest/risk.py` — `RiskConfig`/`RiskManager`: position sizing
  (fraction / volatility-target), stop-loss, take-profit, drawdown kill-switch;
  wired into the engine via `Backtest(..., risk=RiskConfig(...))`.
- `backtest/optimize.py` — `grid_search` + `walk_forward`; `yq optimize … [--walk-forward N]`.
- `metrics/performance.py` — Sortino, Calmar, annualized volatility, and
  per-trade stats (avg win/loss, best/worst) alongside the existing headline set.
- `data/sources/ccxt_source.py` — `CCXTSource` for 100+ exchanges.

**Deliberately out of scope (for now).** Rust-level latency (nautilus's niche),
options/futures instruments, and a closed paid live plugin. These don't fit a
personal, Claude-Code-operated crypto cockpit; revisit if the use case grows.
