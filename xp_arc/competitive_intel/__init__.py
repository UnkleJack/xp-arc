"""
XP-Arc Competitive Intelligence Station Package
"""

from .station import CompetitiveIntelStation, PROJECT_ROOT
from .config import load_station_config, load_watchlist_config, load_all_configs

__all__ = [
    "CompetitiveIntelStation",
    "PROJECT_ROOT",
    "load_station_config",
    "load_watchlist_config",
    "load_all_configs",
]

__version__ = "0.1.0"