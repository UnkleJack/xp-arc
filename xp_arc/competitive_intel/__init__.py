"""
XP-Arc Competitive Intelligence Station Package

Imports in this package are LAZY (PEP 562). Reason:

    station.py  -> jinja2, yaml      (report rendering)
    config.py   -> yaml              (watchlist parsing)
    fetchers.py -> feedparser, httpx (network collection)

Those are declared in the ``competitive-intel`` extra, not in the base
install (CONSTITUTION Article XII: Tier 1 must remain stdlib-only and an
optional extra must degrade rather than break the core).

Two modules in this package are pool-side and deliberately dependency-free:

    bridge.py   -> json, logging, ..core.sanitization
    analyst.py  -> json, ..core.station

An eager ``from .station import ...`` here made it impossible to import the
pool-side half without the report renderer's template engine installed. That
broke ``tests/test_competitive_bridge.py`` at collection time in any
environment that had not installed the ``competitive-intel`` extra -- which
is what CI installs (``.[dev]`` / ``.[gauntlet]``), so the whole unit-test
job failed in under a second on an ImportError unrelated to the code under
test.

Submodule imports (``from xp_arc.competitive_intel.bridge import X``) are
unaffected by this file and remain the recommended form.
"""

import importlib

__all__ = [
    "CompetitiveIntelStation",
    "CompetitiveIntelBridge",
    "CompetitiveGapAnalyst",
    "MAX_GAPS_PER_SCAN",
    "PROJECT_ROOT",
    "load_station_config",
    "load_watchlist_config",
    "load_all_configs",
]

__version__ = "0.1.0"

# attribute name -> submodule that actually defines it
_LAZY_ATTRS = {
    "CompetitiveIntelStation": ".station",
    "PROJECT_ROOT": ".station",
    "load_station_config": ".config",
    "load_watchlist_config": ".config",
    "load_all_configs": ".config",
    "CompetitiveIntelBridge": ".bridge",
    "MAX_GAPS_PER_SCAN": ".bridge",
    "CompetitiveGapAnalyst": ".analyst",
}

# third-party modules that each submodule needs, for the error message only
_EXTRA_HINT = "pip install 'xp-arc[competitive-intel]'"


def __getattr__(name):
    """Resolve package attributes on first access instead of at import time."""
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    submodule = _LAZY_ATTRS[name]
    try:
        module = importlib.import_module(submodule, __name__)
    except ImportError as exc:
        missing = getattr(exc, "name", None) or str(exc)
        raise ImportError(
            f"xp_arc.competitive_intel.{submodule.lstrip('.')} requires {missing}, "
            f"which is an optional dependency. Install it with: {_EXTRA_HINT}. "
            f"The pool-side modules (bridge, analyst) do not need it -- import them "
            f"directly, e.g. 'from xp_arc.competitive_intel.bridge import "
            f"CompetitiveIntelBridge'."
        ) from exc

    value = getattr(module, name)
    globals()[name] = value  # cache so __getattr__ is not re-entered
    return value


def __dir__():
    return sorted(set(globals()) | set(_LAZY_ATTRS))
