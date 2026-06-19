#!/bin/bash
# YammyQuant — Claude Code SessionStart bootstrap.
# Makes the repo plug-and-play: installs the library + operating/test deps so the
# operator (you) can immediately collect, backtest, decide, run the dashboard, and
# run tests/linters. Heavy RL-training deps (torch / stable-baselines3) are left
# out on purpose — run `pip install -e '.[rl]'` on demand if you need `yq train`.
set -euo pipefail

# Only bootstrap in Claude Code on the web (remote) sessions; local devs manage
# their own venv. Remove this guard if you want it to run locally too.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Install is idempotent and benefits from the cached container layer. pip logs go
# to stderr (hook logs) so stdout stays clean for the orientation note below.
{
  python -m pip install --upgrade pip || true   # non-fatal (may be distro-managed)
  pip install -e '.[dev,web,feeds,exchanges,binance,ccxt,optimize,plot]'
  pip install gymnasium            # the RL *env* (ChartFollowingEnv); not training
} 1>&2

# stdout from a SessionStart hook is injected into the session as context.
cat <<'NOTE'
YammyQuant is installed and ready. You are the operator of this quant cockpit.
Start every session by loading your memory, then read the operator guide:

    yq recall        # unread instructions + salient past notes + open positions
    yq doctor        # data freshness / config / account health

See CLAUDE.md for the full toolbelt and the operating loop. Paper trading is the
default; live orders require YQ_ALLOW_LIVE=1 + explicit human approval.
NOTE
