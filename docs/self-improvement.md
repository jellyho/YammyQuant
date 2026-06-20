# Self-improvement — grow your own toolbox

The operator (Claude Code) isn't limited to the built-ins. It can **author its own
strategies, indicators, and skills**, save them as files, and have them
auto-loaded — so the platform keeps developing itself across (ephemeral) sessions.

```
yq new strategy <name>     →  user_plugins/strategies/<name>.py   (from a template)
yq new indicator <name>    →  user_plugins/indicators/<name>.py
yq new skill <name>        →  .claude/skills/<name>/SKILL.md
yq plugins                 →  list what's loaded (+ any load errors)
```

Everything under `user_plugins/` is **auto-loaded on every `yq` run** (and by the
dashboard), so a new strategy/indicator is usable the moment you save it — and
because the files live in the repo, **committing them makes them permanent**.

## Author a strategy

```bash
yq new strategy momentum_pop
```

scaffolds a working `Strategy` subclass decorated with `@strategy("momentum_pop")`:

```python
from yammyquant.backtest.order import Action, Order
from yammyquant.plugins import strategy
from yammyquant.strategy.base import Strategy


@strategy("momentum_pop")
class MomentumPop(Strategy):
    def __init__(self, fast: int = 10, slow: int = 30, size: float = 1.0):
        self.fast, self.slow, self.size = fast, slow, size
        self.warmup = slow + 2

    def on_bar(self, window):
        # ...your rule, using window.ind.<any indicator>...
        return []
```

Edit the rule, then it behaves exactly like a built-in:

```bash
yq backtest BTCUSDT 1d momentum_pop --fast 8 --slow 21
yq optimize BTCUSDT 1d momentum_pop --walk-forward 4
yq scan BTCUSDT ETHUSDT --strategy momentum_pop
yq decide --execute            # picked up if enabled; toggle in the dashboard
```

## Author an indicator

```bash
yq new indicator pulse
```

gives an `@indicator` function callable via the Candle accessor everywhere:

```python
from yammyquant.plugins import indicator


@indicator
def pulse(candle, period: int = 14):
    import pandas as pd
    close = pd.Series(candle.close, index=candle.index)
    return (close / close.rolling(period).mean() - 1.0).rename("pulse")
```

```python
candle.ind.pulse(20)           # works immediately; usable inside your strategies
```

## Author a skill

Skills are the operator's own playbooks (the [Claude Code skill](https://code.claude.com)
format). `yq new skill weekly_review` scaffolds `.claude/skills/weekly_review/SKILL.md`
with frontmatter — write the steps you want future-you to follow.

## …or from the dashboard

The **Plugins** panel in the [dashboard](dashboard.md) does the same without the
CLI: pick a kind + name and hit **new**, then pick the file, edit it in the
in-browser editor, and **save & reload** — the strategy/indicator is registered
live and the load result (or any error) is shown inline.

## The self-improvement loop

1. **Hypothesize** → `yq new strategy <idea>` and edit it.
2. **Validate** → `yq backtest` / `yq optimize --walk-forward`; record a baseline
   with `yq expect`.
3. **Keep or kill** → if it survives out-of-sample, `git commit` it (now permanent
   and live); otherwise delete the file.
4. **Remember** → `yq journal "why <idea> worked/failed" --importance N` so the
   next session builds on it.

!!! note "Configuration"
    Plugins load from `./user_plugins` by default; override with
    `YQ_PLUGINS_DIR`. A broken plugin file is reported by `yq plugins` and skipped
    — it never breaks the rest of the toolbelt.
