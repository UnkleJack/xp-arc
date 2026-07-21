"""
XP-Arc Competitive Intelligence Station - Core Module
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

logger = logging.getLogger(__name__)

# Module-level reference to project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


class CompetitiveIntelStation:
    """
    Competitive Intelligence Station for XP-Arc.
    Monitors competitive landscape, detects conflicts/gaps, produces actionable intelligence.
    """

    def __init__(self, config: Dict[str, Any], dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.station_config = config.get("station", {})
        self.watchlist = config.get("watchlist", {})
        self.db_path = Path(self.config.get("database", {}).get("path", "data/competitive/gaps.db"))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def init_database(self):
        """Initialize the SQLite database with schema."""
        schema_path = Path(self.config.get("database", {}).get("schema", "sql/competitive-gaps-schema.sql"))
        if not schema_path.exists():
            # Try relative to project root
            schema_path = PROJECT_ROOT / schema_path

        with open(schema_path, "r") as f:
            schema_sql = f.read()

        if self.dry_run:
            logger.info(f"[DRY RUN] Would initialize database at {self.db_path}")
            return

        conn = sqlite3.connect(self.db_path)
        conn.executescript(schema_sql)
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    async def fetch_all_sources(self):
        """Fetch data from all enabled sources."""
        sources = self.config.get("sources", {})
        tasks = []

        for source_id, source_config in sources.items():
            if source_config.get("enabled", False):
                tasks.append(self.fetch_source(source_id))

        if tasks:
            await asyncio.gather(*tasks)

    async def fetch_source(self, source_id: str):
        """Fetch data from a specific source."""
        logger.info(f"Fetching from source: {source_id}")

        source_config = self.config.get("sources", {}).get(source_id, {})
        if not source_config.get("enabled", False):
            logger.warning(f"Source {source_id} is not enabled")
            return

        # This is a placeholder - actual implementation would use specific fetchers
        # for each source type (GitHub API, PyPI, NPM, RSS, etc.)
        fetchers = {
            "github": self._fetch_github,
            "pypi": self._fetch_pypi,
            "npm": self._fetch_npm,
            "crates_io": self._fetch_crates_io,
            "websites": self._fetch_websites,
            "x_twitter": self._fetch_x_twitter,
            "linkedin": self._fetch_linkedin,
            "hackernews": self._fetch_hackernews,
            "reddit": self._fetch_reddit,
            "custom_watchlist": self._fetch_custom_watchlist,
        }

        fetcher = fetchers.get(source_id)
        if fetcher:
            await fetcher(source_config)
        else:
            logger.warning(f"No fetcher implemented for source: {source_id}")

    async def _fetch_github(self, config: Dict[str, Any]):
        """Fetch GitHub events for watched repos."""
        # Placeholder for actual GitHub API integration
        logger.info("GitHub fetcher - not yet implemented")
        pass

    async def _fetch_pypi(self, config: Dict[str, Any]):
        """Fetch PyPI package releases."""
        logger.info("PyPI fetcher - not yet implemented")
        pass

    async def _fetch_npm(self, config: Dict[str, Any]):
        """Fetch NPM package releases."""
        logger.info("NPM fetcher - not yet implemented")
        pass

    async def _fetch_crates_io(self, config: Dict[str, Any]):
        """Fetch crates.io package releases."""
        logger.info("crates.io fetcher - not yet implemented")
        pass

    async def _fetch_websites(self, config: Dict[str, Any]):
        """Fetch RSS/Atom feeds from competitor websites."""
        logger.info("Website/RSS fetcher - not yet implemented")
        pass

    async def _fetch_x_twitter(self, config: Dict[str, Any]):
        """Fetch X/Twitter posts from competitor accounts."""
        logger.info("X/Twitter fetcher - not yet implemented")
        pass

    async def _fetch_linkedin(self, config: Dict[str, Any]):
        """Fetch LinkedIn company updates."""
        logger.info("LinkedIn fetcher - not yet implemented")
        pass

    async def _fetch_hackernews(self, config: Dict[str, Any]):
        """Fetch HackerNews stories matching keywords."""
        logger.info("HackerNews fetcher - not yet implemented")
        pass

    async def _fetch_reddit(self, config: Dict[str, Any]):
        """Fetch Reddit posts from relevant subreddits."""
        logger.info("Reddit fetcher - not yet implemented")
        pass

    async def _fetch_custom_watchlist(self, config: Dict[str, Any]):
        """Process custom watchlist entries."""
        logger.info("Custom watchlist fetcher - not yet implemented")
        pass

    async def detect_all(self):
        """Run detection on all fetched events."""
        logger.info("Running detection on all sources")
        # Placeholder - would query unprocessed events and run detection rules
        pass

    async def detect_source(self, source_id: str):
        """Run detection for a specific source."""
        logger.info(f"Running detection for source: {source_id}")
        pass

    async def run_once(self):
        """Run the full pipeline once: fetch -> detect -> report."""
        logger.info("Running full pipeline once")
        await self.fetch_all_sources()
        await self.detect_all()
        # Check if it's time for weekly report
        if self._should_generate_weekly_report():
            await self.generate_weekly_report()

    async def run_daemon(self):
        """Run as a daemon with scheduled tasks."""
        logger.info("Starting daemon mode")
        schedule = self.config.get("schedule", {})

        while True:
            now = datetime.now()
            # Check each schedule
            for name, cron_expr in schedule.items():
                if self._should_run_cron(cron_expr, now):
                    logger.info(f"Running scheduled task: {name}")
                    if name == "high_frequency":
                        await self.fetch_all_sources()  # Just high-freq sources
                        await self.detect_all()
                    elif name == "daily":
                        await self.fetch_all_sources()
                        await self.detect_all()
                    elif name == "weekly":
                        await self.fetch_all_sources()
                        await self.detect_all()
                        await self.generate_weekly_report()
                    elif name == "monthly":
                        await self.snapshot_all_competitors()

            # Sleep until next minute
            await asyncio.sleep(60)

    def _should_run_cron(self, cron_expr: str, now: datetime) -> bool:
        """Check if a cron expression matches now (simplified)."""
        # This is a simplified check - real implementation would use croniter
        # For now, just check hourly/daily/weekly/monthly patterns
        return False

    def _should_generate_weekly_report(self) -> bool:
        """Check if it's time for weekly report (Monday)."""
        return datetime.now().weekday() == 0  # Monday

    def get_current_week(self) -> str:
        """Get current ISO week as YYYY-WNN."""
        now = datetime.now()
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"

    async def generate_weekly_report(self, week: Optional[str] = None):
        """Generate weekly competitive intelligence report."""
        if week is None:
            week = self.get_current_week()

        logger.info(f"Generating weekly report for {week}")

        # Placeholder - would query database and render template
        report_path = Path("reports/competitive/weekly") / f"{week}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run:
            # Render template with data
            template_path = Path(self.config.get("reports", {}).get("template", "templates/competitive-weekly-report.md"))
            if template_path.exists():
                with open(template_path, "r") as f:
                    template = f.read()
                # Would render with actual data
                report_content = template.replace("{{ week }}", week)
                report_content = report_content.replace("{{ year }}", week.split("-W")[0])
            else:
                report_content = f"# Weekly Report {week}\n\nNo template found."

            with open(report_path, "w") as f:
                f.write(report_content)

        logger.info(f"Report generated at {report_path}")

    async def snapshot_competitor(self, competitor_id: str):
        """Create a snapshot for a specific competitor."""
        logger.info(f"Creating snapshot for {competitor_id}")
        pass

    async def snapshot_all_competitors(self):
        """Create snapshots for all competitors."""
        logger.info("Creating snapshots for all competitors")
        competitors = self.watchlist.get("competitors", [])
        for comp in competitors:
            await self.snapshot_competitor(comp["id"])

    async def query_gaps(
        self,
        competitor: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        since: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Query gaps from the database."""
        conn = self.get_connection()
        try:
            query = "SELECT * FROM gaps WHERE 1=1"
            params = []

            if competitor:
                query += " AND competitor = ?"
                params.append(competitor)
            if status:
                query += " AND status = ?"
                params.append(status)
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if since:
                query += " AND first_seen >= ?"
                params.append(since)

            query += " ORDER BY last_seen DESC"

            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    async def check_source_health(self) -> List[Dict[str, Any]]:
        """Check health of all sources."""
        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT source, competitor,
                       SUM(events_collected) as total_collected,
                       SUM(events_emitted) as total_emitted,
                       AVG(signal_to_noise_ratio) as avg_snr,
                       SUM(error_count) as total_errors,
                       MAX(is_muted) as is_muted
                FROM source_health
                WHERE date >= date('now', '-30 days')
                GROUP BY source, competitor
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def emit_event(self, event: Dict[str, Any]):
        """Emit a competitive intelligence event to the database."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would emit event: {event.get('title')}")
            return

        conn = self.get_connection()
        try:
            conn.execute("""
                INSERT INTO events (event_id, timestamp, source, competitor, category,
                                   signal_type, severity, title, summary, url, raw_payload, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.get("event_id", str(uuid.uuid4())),
                event.get("timestamp", datetime.now().isoformat()),
                event.get("source"),
                event.get("competitor"),
                event.get("category"),
                event.get("signal_type"),
                event.get("severity"),
                event.get("title"),
                event.get("summary"),
                event.get("url"),
                json.dumps(event.get("raw_payload", {})),
                json.dumps(event.get("tags", [])),
            ))
            conn.commit()
        finally:
            conn.close()


def load_config(station_config_path: str, watchlist_path: str) -> Dict[str, Any]:
    """Load station configuration and watchlist."""
    config = {}

    # Load station config
    station_path = Path(station_config_path)
    if not station_path.exists():
        # Try relative to project root
        station_path = PROJECT_ROOT / station_config_path

    if station_path.exists():
        with open(station_path, "r") as f:
            config = yaml.safe_load(f)
    else:
        logger.warning(f"Station config not found at {station_config_path}")

    # Load watchlist
    watchlist_path_obj = Path(watchlist_path)
    if not watchlist_path_obj.exists():
        watchlist_path_obj = PROJECT_ROOT / watchlist_path

    if watchlist_path_obj.exists():
        with open(watchlist_path_obj, "r") as f:
            watchlist = yaml.safe_load(f)
        config["watchlist"] = watchlist
    else:
        logger.warning(f"Watchlist not found at {watchlist_path}")

    return config