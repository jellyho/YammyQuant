# Memory & persistence

The operator is **ephemeral** — a fresh Claude Code session has no recall of the
last one, and on the web the container is reclaimed after inactivity. So anything
worth keeping must live **outside** the session. YammyQuant uses the same memory
tiers most agentic setups converge on.

## The four tiers

| Tier | Where | Holds |
|---|---|---|
| **Semantic** — stable knowledge | `CLAUDE.md` (committed to git) | Operating procedure, conventions, the toolbelt. Loaded into context every session. |
| **Structured** — facts & config | state DB `settings` table (`yq … set`) | Risk limits, strategy toggles, target weights, flags like `sentiment_gate`. |
| **Episodic** — why you did things | `journal` table (`yq journal`) | Theses, entry/exit rationale, lessons — free-text, tagged, time-ordered. |
| **World state** — what is true now | state DB tables + DuckDB candles | Positions, trades, equity curve, signals, collected news, the inbox. |

!!! tip "The rule of thumb"
    If it should change behavior in **every** future session → `CLAUDE.md`.
    If it's a tunable value → `settings`. If it's a *decision and its reasoning* →
    the `journal`. If it's an observation about the market or account → it's
    already a row in the state DB.

## The memory stream — `yq recall`

Re-reading the whole journal every session doesn't scale, so the journal is a
retrievable **memory stream** (the [Generative Agents](https://arxiv.org/abs/2304.03442)
pattern). Each note can carry an `--importance` (1–10); `yq recall` ranks notes by
**recency × importance × relevance** and bundles unread inbox + open positions into
one session-start digest.

```bash
yq journal "scaled into BTC on breakout, high conviction" --tag thesis --importance 8
yq recall                 # top memories + inbox + positions
yq recall "ETH merge"     # a query biases retrieval toward matching notes
```

| Signal | Meaning |
|---|---|
| **recency** | half-life decay (~14d) — recent notes weigh more. |
| **importance** | operator-set salience (1–10); defaults to mid when unset. |
| **relevance** | term overlap with the query (0 when no query is given). |

The score is `0.45·recency + 0.35·importance + 0.20·relevance`; a query also drops
zero-relevance notes so the digest stays focused.

## How most people manage agent memory

This mirrors common practice with agentic AI:

- **Project memory files** — `CLAUDE.md` / `AGENTS.md`, committed to the repo and
  auto-loaded into context. The agent's long-term instructions.
- **A durable store** the agent reads/writes through tools — a database (here
  SQLite), a vector store for retrieval, or plain notes/markdown. The point is the
  data outlives the chat context.
- **An append-only journal / decision log** the agent re-reads at the start of a
  session — the pattern behind "memory stream" agents.
- **Summaries over raw history** — don't keep every token; persist distilled state
  and reload that.

The anti-pattern is relying on the chat transcript as memory: it's capped, it's
lost when the container is reclaimed, and it isn't shared with the dashboard. In
YammyQuant the transcript is disposable — the SQLite state DB, the DuckDB candles,
and `CLAUDE.md` are the memory.

!!! note "First & last thing each session"
    Start with `yq recall` (memory + inbox + positions) and read `CLAUDE.md`. End
    by writing a `yq journal … --importance N` entry so next-you starts informed.
