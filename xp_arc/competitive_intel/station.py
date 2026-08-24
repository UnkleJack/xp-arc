"""
XP-Arc Competitive Intelligence Station - Core Module
"""

import asyncio
import json
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
from jinja2 import Template

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
                    f"UPDATE raw_events SET processed = 1 WHERE id IN ({placeholders})",
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

    async def detect_source(self, source_id: str):
        """Run detection on unprocessed events from a specific source only.

        Mirrors detect_all() but scopes the raw_events query and the
        processed-flag update to a single source, so `station_main.py`'s
        `detect --source X` CLI path has a real target to call.
        """
        logger.info(f"Running detection for source: {source_id}")

        conn = self.get_connection()
        try:
            cursor = conn.execute("""
                SELECT * FROM raw_events
                WHERE processed = 0 AND source = ?
                ORDER BY fetched_at DESC
                LIMIT 1000
            """, (source_id,))
            events = [dict(row) for row in cursor.fetchall()]

            if events:
                signals = await self.detection_engine.process_events(events)
                logger.info(f"Generated {len(signals)} signals from {source_id}")

                event_ids = [e["id"] for e in events]
                placeholders = ",".join("?" * len(event_ids))
                conn.execute(  # nosec B608
                    f"UPDATE raw_events SET processed = 1 WHERE id IN ({placeholders})",
                    event_ids
                )
                conn.commit()

                gaps = await self.gap_analyzer.identify_gaps(days=30)
                if gaps:
                    await self.gap_analyzer.update_gap_database(gaps)
                    logger.info(f"Identified {len(gaps)} gaps from {source_id}")
            else:
                logger.info(f"No unprocessed events for source: {source_id}")
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

    def _build_weekly_report_context(self, week: str) -> Dict[str, Any]:
        """Gather real data from the gaps DB for the weekly report template.

        Populates every variable the template references. Sections with no
        backing table yet (competitor_moves narrative framing, threats
        beyond flagged conflict events) render from the closest real data
        we have rather than being fabricated; anything genuinely absent
        renders as an empty list so Jinja emits nothing instead of leaking
        `{{ }}` / `{% %}` syntax into the shipped report.
        """
        year_str, week_num_str = week.split("-W")
        year = int(year_str)
        week_num = int(week_num_str)

        # ISO week -> date range
        start_date = datetime.fromisocalendar(year, week_num, 1)
        end_date = start_date + timedelta(days=6)
        start_iso = start_date.strftime("%Y-%m-%d")
        end_iso = end_date.strftime("%Y-%m-%d")

        conn = self.get_connection()
        try:
            total_events = conn.execute(
                "SELECT COUNT(*) FROM raw_events WHERE fetched_at >= ? AND fetched_at < ?",
                (start_iso, end_date.strftime("%Y-%m-%d") + "T23:59:59")
            ).fetchone()[0]

            emitted_events = conn.execute(
                "SELECT COUNT(*) FROM events WHERE timestamp >= ? AND timestamp < ?",
                (start_iso, end_date.strftime("%Y-%m-%d") + "T23:59:59")
            ).fetchone()[0]

            new_gaps = conn.execute(
                "SELECT COUNT(*) FROM gaps WHERE first_seen >= ? AND first_seen < ?",
                (start_iso, end_date.strftime("%Y-%m-%d") + "T23:59:59")
            ).fetchone()[0]

            promoted_gaps = conn.execute(
                "SELECT COUNT(*) FROM gaps WHERE status = 'investigating' AND updated_at >= ? AND updated_at < ?",
                (start_iso, end_date.strftime("%Y-%m-%d") + "T23:59:59")
            ).fetchone()[0]

            muted_sources = conn.execute(
                "SELECT COUNT(DISTINCT source) FROM source_health WHERE is_muted = 1"
            ).fetchone()[0]

            competitor_count = len(self.watchlist.get("competitors", []))

            # Competitor moves: events this week, framed as moves
            move_rows = conn.execute(
                """SELECT competitor, title AS action, category, severity, url
                   FROM events WHERE timestamp >= ? AND timestamp < ?
                   ORDER BY timestamp DESC LIMIT 25""",
                (start_iso, end_date.strftime("%Y-%m-%d") + "T23:59:59")
            ).fetchall()
            competitor_moves = [
                {
                    "competitor": r["competitor"],
                    "action": r["action"],
                    "category": r["category"],
                    "impact": r["severity"],
                    "response": "",
                }
                for r in move_rows
            ]

            # Gap opportunities: open gaps, most recently seen first
            gap_rows = conn.execute(
                """SELECT description, competitor, evidence_urls, severity, status
                   FROM gaps WHERE status = 'open'
                   ORDER BY last_seen DESC LIMIT 25"""
            ).fetchall()
            gap_opportunities = [
                {
                    "description": r["description"],
                    "competitor": r["competitor"],
                    "evidence": r["evidence_urls"] or "",
                    "effort": "",
                    "priority": r["severity"],
                    "status": r["status"],
                }
                for r in gap_rows
            ]

            # Threats: high/critical conflict-category events this week
            threat_rows = conn.execute(
                """SELECT competitor, title, severity, summary FROM events
                   WHERE category = 'conflict' AND severity IN ('critical', 'high')
                   AND timestamp >= ? AND timestamp < ?
                   ORDER BY severity DESC, timestamp DESC LIMIT 25""",
                (start_iso, end_date.strftime("%Y-%m-%d") + "T23:59:59")
            ).fetchall()
            threats = [
                {
                    "description": r["title"],
                    "competitor": r["competitor"],
                    "likelihood": r["severity"],
                    "impact": r["severity"],
                    "mitigation": r["summary"] or "",
                }
                for r in threat_rows
            ]

            # Competitor snapshots: most recent per competitor
            snapshot_rows = conn.execute(
                """SELECT competitor, version, pricing_tier, key_features, market_position
                   FROM competitor_snapshots cs
                   WHERE snapshot_date = (
                       SELECT MAX(snapshot_date) FROM competitor_snapshots
                       WHERE competitor = cs.competitor
                   )
                   ORDER BY competitor"""
            ).fetchall()
            competitor_snapshots = [
                {
                    "competitor": r["competitor"],
                    "version": r["version"] or "",
                    "pricing": r["pricing_tier"] or "",
                    "changes": r["key_features"] or "",
                    "position": r["market_position"] or "",
                }
                for r in snapshot_rows
            ]

            # Noise filter: low-SNR sources this week
            noise_rows = conn.execute(
                """SELECT source, events_collected, events_emitted, signal_to_noise_ratio, is_muted
                   FROM source_health WHERE date >= ? AND date < ?
                   ORDER BY signal_to_noise_ratio ASC LIMIT 25""",
                (start_iso, end_iso)
            ).fetchall()
            noise_filter = [
                {
                    "source": r["source"],
                    "collected": r["events_collected"],
                    "emitted": r["events_emitted"],
                    "snr": round((r["signal_to_noise_ratio"] or 0) * 100, 1),
                    "action": "muted" if r["is_muted"] else "monitor",
                }
                for r in noise_rows
            ]

            snr = round((emitted_events / total_events * 100), 1) if total_events else 0.0

            action_items = [
                f"Review {t['competitor']} threat: {t['description']}" for t in threats
            ] or ["No action items this week."]

            executive_summary = (
                f"{total_events} events collected, {new_gaps} new gaps identified, "
                f"{len(threats)} high-priority threats this week."
            )

            return {
                "year": year,
                "week": f"{week_num:02d}",
                "start_date": start_iso,
                "end_date": end_iso,
                "generated_at": datetime.now().isoformat(),
                "station_version": "0.3.0",
                "total_events": total_events,
                "emitted_events": emitted_events,
                "snr": snr,
                "competitor_count": competitor_count,
                "new_gaps": new_gaps,
                "promoted_gaps": promoted_gaps,
                "muted_sources": muted_sources,
                "executive_summary": executive_summary,
                "competitor_moves": competitor_moves,
                "gap_opportunities": gap_opportunities,
                "threats": threats,
                "competitor_snapshots": competitor_snapshots,
                "noise_filter": noise_filter,
                "action_items": action_items,
                "raw_events_summary": f"{total_events} raw events collected this week.",
                "source_health_table": f"{muted_sources} sources muted; see noise filter above.",
                "config_changes": "No tracked configuration changes this week.",
            }
        finally:
            conn.close()

    async def generate_weekly_report(self, week: Optional[str] = None):
        """Generate weekly competitive intelligence report.

        Renders templates/competitive-weekly-report.md through Jinja2 with
        real data pulled from the gaps DB. The previous implementation only
        did two naive str.replace() calls, leaving every {% for %} loop and
        the other ~15 {{ variable }} placeholders in the Jinja template to
        leak verbatim into the shipped report.
        """
        if week is None:
            week = self.get_current_week()

        logger.info(f"Generating weekly report for {week}")

        report_path = Path("reports/competitive/weekly") / f"{week}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run:
            template_path = Path(self.config.get("reports", {}).get("template", "templates/competitive-weekly-report.md"))
            if not template_path.exists():
                template_path = PROJECT_ROOT / template_path

            if template_path.exists():
                with open(template_path, "r") as f:
                    template_source = f.read()
                context = self._build_weekly_report_context(week)
                report_content = Template(template_source).render(**context)
            else:
                report_content = f"# Weekly Report {week}\n\nNo template found."

            with open(report_path, "w") as f:
                f.write(report_content)

        logger.info(f"Report generated at {report_path}")

    async def snapshot_competitor(self, competitor_id: str):
        """Create a point-in-time snapshot row for one competitor.

        Was a stub that logged and stored nothing, which is why
        competitor_snapshots rendered empty in every weekly report.

        The snapshot is assembled from two sources: static profile fields the
        operator declared in the watchlist (pricing tier, market position,
        funding stage, team size), and live metrics derived from raw_events
        already collected this cycle. Nothing here performs a network fetch —
        fetch_all_sources() owns that, and duplicating it would double every
        competitor's API rate-limit consumption.

        Idempotent per day: the schema declares UNIQUE(competitor, snapshot_date),
        so re-running on the same date updates that day's row rather than
        appending a duplicate.
        """
        profile = {}
        for comp in self.watchlist.get("competitors", []):
            if comp.get("id") == competitor_id:
                profile = comp
                break

        if not profile:
            logger.warning("No watchlist entry for competitor %s; skipping snapshot",
                           competitor_id)
            return None

        if self.dry_run:
            logger.info(f"[DRY RUN] Would snapshot {competitor_id}")
            return None

        snapshot_date = datetime.now(timezone.utc).date().isoformat()
        conn = self.get_connection()
        try:
            # Latest release-shaped event gives the current version.
            row = conn.execute(
                """SELECT title FROM raw_events
                   WHERE competitor = ? AND source_type IN ('release', 'tag')
                   ORDER BY timestamp DESC LIMIT 1""",
                (competitor_id,),
            ).fetchone()
            version = row["title"] if row else None

            metrics = conn.execute(
                """SELECT COUNT(*) AS events_30d
                   FROM raw_events
                   WHERE competitor = ? AND fetched_at >= datetime('now', '-30 days')""",
                (competitor_id,),
            ).fetchone()

            features = profile.get("key_features") or []
            notes = (f"Auto-snapshot. {metrics['events_30d']} raw events collected "
                     f"in the trailing 30 days.")

            conn.execute(
                """INSERT INTO competitor_snapshots
                       (competitor, snapshot_date, version, pricing_tier,
                        pricing_details, key_features, market_position,
                        funding_stage, team_size, github_stars, github_forks,
                        pypi_downloads_monthly, npm_downloads_weekly, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(competitor, snapshot_date) DO UPDATE SET
                       version = excluded.version,
                       pricing_tier = excluded.pricing_tier,
                       pricing_details = excluded.pricing_details,
                       key_features = excluded.key_features,
                       market_position = excluded.market_position,
                       funding_stage = excluded.funding_stage,
                       team_size = excluded.team_size,
                       github_stars = excluded.github_stars,
                       github_forks = excluded.github_forks,
                       pypi_downloads_monthly = excluded.pypi_downloads_monthly,
                       npm_downloads_weekly = excluded.npm_downloads_weekly,
                       notes = excluded.notes""",
                (
                    competitor_id, snapshot_date, version,
                    profile.get("pricing_tier"),
                    json.dumps(profile.get("pricing_details") or {}),
                    json.dumps(features),
                    profile.get("market_position"),
                    profile.get("funding_stage"),
                    profile.get("team_size"),
                    profile.get("github_stars"),
                    profile.get("github_forks"),
                    profile.get("pypi_downloads_monthly"),
                    profile.get("npm_downloads_weekly"),
                    notes,
                ),
            )
            conn.commit()
            logger.info("Snapshot recorded for %s on %s", competitor_id, snapshot_date)
            return snapshot_date
        finally:
            conn.close()

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
