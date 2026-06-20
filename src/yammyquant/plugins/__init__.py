"""Self-improvement layer — let the operator grow its own toolbox.

Claude Code can author new **strategies** and **indicators** (plus Claude Code
**skills**), save them as files, and have them auto-loaded into the live
registries so they're immediately usable from the CLI and dashboard. Because the
files live in the repo, they persist across the operator's (ephemeral) sessions —
the platform keeps developing itself.

Layout (default ``./user_plugins``, override with ``YQ_PLUGINS_DIR``)::

    user_plugins/
      strategies/<name>.py     # @strategy("<name>") class ...(Strategy)
      indicators/<name>.py     # @indicator def <name>(candle, ...)
    .claude/skills/<name>/SKILL.md   # operator playbooks

Workflow::

    yq new strategy my_edge      # scaffold from a template
    # ...edit user_plugins/strategies/my_edge.py...
    yq backtest BTCUSDT 1d my_edge   # works immediately (auto-loaded)
    yq plugins                   # list what's been loaded
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

__all__ = ["strategy", "indicator", "load_plugins", "plugins_dir", "new_plugin"]


def plugins_dir(base: str | os.PathLike | None = None) -> Path:
    if base is not None:
        return Path(base)
    return Path(os.getenv("YQ_PLUGINS_DIR") or (Path.cwd() / "user_plugins"))


def _slug(name: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", name.strip()).strip("_").lower()
    if not s or not re.match(r"[a-z_]", s):
        raise ValueError(f"invalid plugin name: {name!r}")
    return s


def _camel(slug: str) -> str:
    return "".join(p.capitalize() for p in slug.split("_")) or "Plugin"


# -- registration decorators (used inside plugin files) ----------------------
def strategy(name: str):
    """Class decorator: register a :class:`Strategy` under ``name``."""
    slug = _slug(name)

    def deco(cls):
        from yammyquant.ops import operator as ops

        ops.STRATEGIES[slug] = cls
        ops.DEFAULT_GRIDS.setdefault(slug, {})
        return cls

    return deco


def indicator(fn=None, *, name: str | None = None):
    """Function decorator: register an indicator into the Candle accessor."""
    from yammyquant.data import indicators as ind

    def deco(f):
        ind.REGISTRY[name or f.__name__] = f
        return f

    return deco(fn) if fn is not None else deco


# -- loading -----------------------------------------------------------------
def _import_file(path: Path) -> None:
    mod_name = f"yq_plugin_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)


def load_plugins(base: str | os.PathLike | None = None) -> dict:
    """Import every plugin file, registering its strategies/indicators.

    Returns the names newly registered and any per-file errors. Safe to call
    repeatedly and safe when the directory is missing.
    """
    from yammyquant.ops import operator as ops
    from yammyquant.data import indicators as ind

    root = plugins_dir(base)
    before_s, before_i = set(ops.STRATEGIES), set(ind.REGISTRY)
    errors: list[str] = []
    for sub in ("indicators", "strategies"):
        directory = root / sub
        if not directory.is_dir():
            continue
        for file in sorted(directory.glob("*.py")):
            if file.name.startswith("_"):
                continue
            try:
                _import_file(file)
            except Exception as exc:  # one bad plugin must not break the others
                errors.append(f"{sub}/{file.name}: {type(exc).__name__}: {exc}")
    return {
        "dir": str(root),
        "strategies": sorted(set(ops.STRATEGIES) - before_s),
        "indicators": sorted(set(ind.REGISTRY) - before_i),
        "errors": errors,
    }


# -- scaffolding -------------------------------------------------------------
def new_plugin(kind: str, name: str, base: str | os.PathLike | None = None) -> Path:
    """Scaffold a strategy/indicator/skill from a template; return the new path."""
    from yammyquant.plugins import templates

    slug = _slug(name)
    if kind == "skill":
        path = Path(".claude/skills") / slug / "SKILL.md"
        content = templates.SKILL.format(name=slug, title=_camel(slug))
    elif kind in ("strategy", "indicator"):
        sub = "strategies" if kind == "strategy" else "indicators"
        path = plugins_dir(base) / sub / f"{slug}.py"
        tmpl = templates.STRATEGY if kind == "strategy" else templates.INDICATOR
        content = tmpl.format(name=slug, cls=_camel(slug))
    else:
        raise ValueError(f"unknown kind {kind!r}; choose strategy/indicator/skill")

    if path.exists():
        raise FileExistsError(str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path
