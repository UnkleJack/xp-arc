"""
XP-Arc Competitive Intelligence - Configuration Loader
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Module-level reference to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


def load_station_config(config_path: str = "config/competitive-intelligence-station.yaml") -> Dict[str, Any]:
    """Load station configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        path = PROJECT_ROOT / config_path

    if not path.exists():
        logger.warning(f"Station config not found at {config_path}")
        return {}

    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_watchlist_config(watchlist_path: str = "config/competitive-watchlist.yaml") -> Dict[str, Any]:
    """Load watchlist configuration from YAML file."""
    path = Path(watchlist_path)
    if not path.exists():
        path = PROJECT_ROOT / watchlist_path

    if not path.exists():
        logger.warning(f"Watchlist config not found at {watchlist_path}")
        return {}

    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_all_configs(
    station_config_path: str = "config/competitive-intelligence-station.yaml",
    watchlist_path: str = "config/competitive-watchlist.yaml"
) -> Dict[str, Any]:
    """Load both station config and watchlist, merging them."""
    config = load_station_config(station_config_path)
    watchlist = load_watchlist_config(watchlist_path)
    config["watchlist"] = watchlist
    return config