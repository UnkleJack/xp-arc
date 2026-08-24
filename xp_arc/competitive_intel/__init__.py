"""
XP-Arc Competitive Intelligence Station Package
"""

from .station import CompetitiveIntelStation, PROJECT_ROOT
from .config import load_station_config, load_watchlist_config, load_all_configs
from .bridge import CompetitiveIntelBridge, MAX_GAPS_PER_SCAN
from .analyst import CompetitiveGapAnalyst

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