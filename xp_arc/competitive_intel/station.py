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

from .fetchers import create_fetcher
from .detection import DetectionEngine, GapAnalyzer

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

        # Initialize sub-modules
        self.detection_engine = DetectionEngine(self)
        self.gap_analyzer = GapAnalyzer(self)

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
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Error fetching from source {list(sources.keys())[i]}: {result}")

    async def fetch_source(self, source_id: str):
        """Fetch data from a specific source using the fetcher factory."""
        logger.info(f"Fetching from source: {source_id}")

        source_config = self.config.get("sources", {}).get(source_id, {})
        if not source_config.get("enabled", False):
            logger.warning(f"Source {source_id} is not enabled")
            return

        # Merge watchlist data into source config for fetchers that need it
        source_config = self._enrich_source_config(source_id, source_config)

        # Create fetcher using factory
        fetcher = await create_fetcher(self, source_id)
        if fetcher:
            try:
                events = await fetcher.fetch(source_config)
                logger.info(f"Fetched {len(events)} events from {source_id}")

                # Store raw events
                for event in events:
                    self.emit_raw_event(event)

                # Run detection on these events
                signals = await self.detection_engine.process_events(events)
                logger.info(f"Generated {len(signals)} signals from {source_id}")

            except Exception as e:
                logger.error(f"Error fetching from {source_id}: {e}")
        else:
            logger.warning(f"No fetcher available for source: {source_id}")

    def _enrich_source_config(self, source_id: str, source_config: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich source config with watchlist data."""
        enriched = source_config.copy()
        watchlist = self.watchlist.get("competitors", [])

        if source_id == "github":
            # Build watchlist from competitor github_repos with org prefix
            repos = []
            for comp in watchlist:
                org = comp.get("github_org", "")
                for repo in comp.get("github_repos", []):
                    if org and not repo.startswith(org + "/"):
                        repos.append(f"{org}/{repo}")
                    else:
                        repos.append(repo)
            enriched["watchlist"] = repos
            enriched["events"] = ["release", "push", "issue", "pull_request"]

        elif source_id == "pypi":
            packages = []
            for comp in watchlist:
                packages.extend(comp.get("pypi_packages", []))
            enriched["packages"] = packages

        elif source_id == "npm":
            packages = []
            for comp in watchlist:
                packages.extend(comp.get("npm_packages", []))
            enriched["packages"] = packages

        elif source_id == "crates_io":
            packages = []
            for comp in watchlist:
                packages.extend(comp.get("crates_packages", []))
            enriched["packages"] = packages

        elif source_id == "websites":
            feeds = []
            for comp in watchlist:
                feeds.extend(comp.get("rss_feeds", []))
            enriched["feeds"] = feeds

        elif source_id == "x_twitter":
            accounts = []
            for comp in watchlist:
                accounts.extend(comp.get("x_accounts", []))
            enriched["accounts"] = accounts

        elif source_id == "linkedin":
            companies = []
            for comp in watchlist:
                if comp.get("linkedin_company"):
                    companies.append(comp["linkedin_company"])
            enriched["company_pages"] = companies

        elif source_id == "hackernews":
            # Use keyword sets from watchlist
            enriched["keywords"] = self.watchlist.get("keyword_sets", {}).get("multi_agent_orchestration", []) + \
                                   self.watchlist.get("keyword_sets", {}).get("ai_agents_general", []) + \
                                   self.watchlist.get("keyword_sets", {}).get("xp_arc_specific", []) + \
                                   self.watchlist.get("keyword_sets", {}).get("market_signals", [])

        elif source_id == "reddit":
            subreddits = self.watchlist.get("source_overrides", {}).get("reddit", {}).get("extra_subreddits", [])
            # Also add default subreddits
            defaults = ["MachineLearning", "LangChain", "AutoGPT", "LocalLLaMA", "AI_Agents"]
            enriched["subreddits"] = list(set(subreddits + defaults))
            enriched["keywords"] = self.watchlist.get("keyword_sets", {}).get("multi_agent_orchestration", [])

        return enriched

    async def detect_all(self):
        """Run detection on all unprocessed events in database."""
        logger.info("Running detection on all unprocessed events")

        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM raw_events 
                WHERE processed = 0 
                ORDER BY fetched_at DESC
                LIMIT 1000
            """)
            events = [dict(row) for row in cursor.fetchall()]

            if events:
                signals = await self.detection_engine.process_events(events)
                logger.info(f"Generated {len(signals)} signals from stored events")

                # Mark as processed
                event_ids = [e["id"] for e in events]
                placeholders = ",".join("?" * len(event_ids))
                conn.execute(  # nosec B608
                    f"UPDATE raw_events SET processed = 1 WHERE id IN ({placeholders})",  # nosec B608 - placeholders derive only from fetched integer IDs
                    event_ids
                )
                conn.commit()

                # Run gap analysis on accumulated signals
                gaps = await self.gap_analyzer.identify_gaps(days=30)
                if gaps:
                    await self.gap_analyzer.update_gap_database(gaps)
                    logger.info(f"Identified {len(gaps)} gaps")
        finally:
            conn.close()

    def emit_raw_event(self, event: Dict[str, Any]):
        """Store a raw event in the database."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would emit raw event: {event.get('title')}")
            return

        import uuid
        conn = self.get_connection()
        try:
            conn.execute("""
                INSERT INTO raw_events (id, source, source_type, competitor, fetched_at, timestamp, title, summary, url, raw_payload, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()),
                event.get("source"),
                event.get("source_type"),
                event.get("competitor"),
                datetime.now().isoformat(),
                event.get("timestamp"),
                event.get("title"),
                event.get("summary"),
                event.get("url"),
                json.dumps(event.get("raw_payload", {})),
                json.dumps(event.get("tags", [])),
            ))
            conn.commit()
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
                INSERT INTO events (event_id, timestamp, source, competitor, category, signal_type, severity, title, summary, url, raw_payload, tags)
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

    async def run_once(self):
        """Run the full pipeline once: fetch -> detect -> report."""
        logger.info("Running full pipeline once")
        await self.fetch_all_sources()
        await self.detect_all()
        if self._should_generate_weekly_report():
            await self.generate_weekly_report()

    async def run_daemon(self):
        """Run as a daemon with scheduled tasks."""
        logger.info("Starting daemon mode")
        schedule = self.config.get("schedule", {})

        while True:
            now = datetime.now()
            for name, cron_expr in schedule.items():
                if self._should_run_cron(cron_expr, now):
                    logger.info(f"Running scheduled task: {name}")
                    if name == "high_frequency":
                        await self.fetch_all_sources()
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

            await asyncio.sleep(60)

    def _should_run_cron(self, cron_expr: str, now: datetime) -> bool:
        """Check if a cron expression matches now (simplified)."""
        # This is a simplified check - real implementation would use croniter
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

        report_path = Path("reports/competitive/weekly") / f"{week}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run:
            template_path = Path(self.config.get("reports", {}).get("template", "templates/competitive-weekly-report.md"))
            if template_path.exists():
                with open(template_path, "r") as f:
                    template = f.read()
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
        # Implementation would query current state and store in competitor_snapshots

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


def load_config(station_config_path: str, watchlist_path: str) -> Dict[str, Any]:
    """Load station configuration and watchlist."""
    config = {}

    # Load station config
    station_path = Path(station_config_path)
    if not station_path.exists():
        station_path = PROJECT_ROOT / station_config_path

    if station_path.exists():
        with open(station_path, "r") as f:
            config = yaml.safe_load(f) or {}
    else:
        logger.warning(f"Station config not found at {station_config_path}")

    # Load watchlist
    watchlist_path_obj = Path(watchlist_path)
    if not watchlist_path_obj.exists():
        watchlist_path_obj = PROJECT_ROOT / watchlist_path

    if watchlist_path_obj.exists():
        with open(watchlist_path_obj, "r") as f:
            watchlist = yaml.safe_load(f) or {}
        config["watchlist"] = watchlist
    else:
        logger.warning(f"Watchlist not found at {watchlist_path}")

    return config