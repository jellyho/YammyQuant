# user_plugins — the operator's self-built toolbox

Files here are **auto-loaded** by `yq` on every run, so anything you (Claude Code)
author is immediately usable and **persists across sessions** (commit it!).

```bash
yq new strategy my_edge      # → user_plugins/strategies/my_edge.py (from a template)
yq new indicator my_signal   # → user_plugins/indicators/my_signal.py
yq new skill my_playbook     # → .claude/skills/my_playbook/SKILL.md
yq plugins                   # list what's loaded (+ any load errors)
```

- `strategies/<name>.py` — a `@strategy("<name>")`-decorated `Strategy` subclass.
  Use it anywhere a built-in works: `yq backtest SYM 1d <name>`, `yq optimize`,
  `yq scan`, `yq decide`, the dashboard toggle.
- `indicators/<name>.py` — an `@indicator` function, callable via
  `candle.ind.<name>(...)`.

Override the location with `YQ_PLUGINS_DIR`. Skills live under `.claude/skills/`.
