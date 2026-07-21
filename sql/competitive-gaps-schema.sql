-- XP-Arc Competitive Intelligence Gap Database Schema
-- SQLite schema for tracking competitive gaps and opportunities

-- ============================================================================
-- RAW EVENTS TABLE
-- Raw events before detection processing
-- ============================================================================
CREATE TABLE IF NOT EXISTS raw_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,  -- github, pypi, npm, website, x_twitter, linkedin, hackernews, reddit, custom
    source_type TEXT NOT NULL,  -- release, push, issue, pull_request, blog_post, story, post, etc.
    competitor TEXT NOT NULL,
    fetched_at TEXT NOT NULL,  -- ISO8601 when we fetched it
    timestamp TEXT NOT NULL,   -- ISO8601 when the event occurred
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    raw_payload TEXT,  -- JSON
    tags TEXT,  -- JSON array
    processed BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_raw_events_fetched_at ON raw_events(fetched_at);
CREATE INDEX IF NOT EXISTS idx_raw_events_competitor ON raw_events(competitor);
CREATE INDEX IF NOT EXISTS idx_raw_events_source ON raw_events(source);
CREATE INDEX IF NOT EXISTS idx_raw_events_processed ON raw_events(processed);

-- ============================================================================
-- GAPS TABLE
-- Core table tracking identified gaps in competitor offerings
-- ============================================================================
CREATE TABLE IF NOT EXISTS gaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor TEXT NOT NULL,
    gap_type TEXT NOT NULL,  -- missing_integration, performance, dx, lockin, pricing, feature, other
    description TEXT NOT NULL,
    evidence_urls TEXT,  -- JSON array of URLs
    first_seen TEXT NOT NULL,  -- ISO8601
    last_seen TEXT NOT NULL,   -- ISO8601
    frequency INTEGER DEFAULT 1,
    severity TEXT NOT NULL,  -- critical, high, medium, low
    status TEXT NOT NULL DEFAULT 'open',  -- open, investigating, prototyping, shipped, wont_fix, duplicate
    xp_arc_ticket TEXT,  -- Link to XP-Arc issue/PR/ticket
    assigned_to TEXT,    -- XP-Arc entity/agent assigned
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_gaps_competitor ON gaps(competitor);
CREATE INDEX IF NOT EXISTS idx_gaps_status ON gaps(status);
CREATE INDEX IF NOT EXISTS idx_gaps_severity ON gaps(severity);
CREATE INDEX IF NOT EXISTS idx_gaps_gap_type ON gaps(gap_type);
CREATE INDEX IF NOT EXISTS idx_gaps_first_seen ON gaps(first_seen);
CREATE INDEX IF NOT EXISTS idx_gaps_last_seen ON gaps(last_seen);

-- ============================================================================
-- COMPETITOR SNAPSHOTS TABLE
-- Periodic snapshots of competitor state (version, pricing, features, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS competitor_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competitor TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,  -- ISO8601 date (YYYY-MM-DD)
    version TEXT,  -- Latest version at snapshot time
    pricing_tier TEXT,  -- free, freemium, paid, enterprise, custom
    pricing_details TEXT,  -- JSON with details
    key_features TEXT,  -- JSON array of features
    market_position TEXT,  -- leader, challenger, niche, declining
    funding_stage TEXT,  -- seed, series_a, series_b, series_c, public, bootstrapped, unknown
    team_size INTEGER,
    github_stars INTEGER,
    github_forks INTEGER,
    pypi_downloads_monthly INTEGER,
    npm_downloads_weekly INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(competitor, snapshot_date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_competitor ON competitor_snapshots(competitor);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON competitor_snapshots(snapshot_date);

-- ============================================================================
-- EVENTS TABLE
-- Raw competitive intelligence events for audit trail
-- ============================================================================
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,  -- UUID
    timestamp TEXT NOT NULL,  -- ISO8601
    source TEXT NOT NULL,  -- github, pypi, npm, website, x_twitter, linkedin, hackernews, reddit, custom
    competitor TEXT NOT NULL,
    category TEXT NOT NULL,  -- conflict, gap, intel
    signal_type TEXT NOT NULL,  -- e.g., api_breaking_change, missing_integration
    severity TEXT NOT NULL,  -- critical, high, medium, low
    title TEXT NOT NULL,
    summary TEXT,
    url TEXT,
    raw_payload TEXT,  -- JSON
    tags TEXT,  -- JSON array
    processed BOOLEAN DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_competitor ON events(competitor);
CREATE INDEX IF NOT EXISTS idx_events_category ON events(category);
CREATE INDEX IF NOT EXISTS idx_events_severity ON events(severity);
CREATE INDEX IF NOT EXISTS idx_events_signal_type ON events(signal_type);

-- ============================================================================
-- SOURCE HEALTH TABLE
-- Track health/signal quality of each source over time
-- ============================================================================
CREATE TABLE IF NOT EXISTS source_health (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,  -- e.g., github:langchain-ai/langgraph, x_twitter:langchain
    competitor TEXT,
    date TEXT NOT NULL,  -- YYYY-MM-DD
    events_collected INTEGER DEFAULT 0,
    events_emitted INTEGER DEFAULT 0,
    signal_to_noise_ratio REAL,  -- events_emitted / events_collected
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    last_success TEXT,
    is_muted BOOLEAN DEFAULT 0,
    mute_reason TEXT,
    mute_until TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source, competitor, date)
);

CREATE INDEX IF NOT EXISTS idx_source_health_date ON source_health(date);
CREATE INDEX IF NOT EXISTS idx_source_health_source ON source_health(source);

-- ============================================================================
-- NOISE OVERRIDES TABLE
-- Manual noise reduction rules
-- ============================================================================
CREATE TABLE IF NOT EXISTS noise_overrides (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_type TEXT NOT NULL,  -- exclude_competitor, exclude_source, exclude_keyword, mute_source
    pattern TEXT NOT NULL,  -- competitor ID, source ID, keyword, etc.
    reason TEXT,
    created_by TEXT,  -- user or agent ID
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,  -- Optional expiration
    is_active BOOLEAN DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_noise_overrides_active ON noise_overrides(is_active);
CREATE INDEX IF NOT EXISTS idx_noise_overrides_type ON noise_overrides(rule_type);

-- ============================================================================
-- WEEKLY REPORTS TABLE
-- Track generated reports
-- ============================================================================
CREATE TABLE IF NOT EXISTS weekly_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    week INTEGER NOT NULL,  -- ISO week number
    report_path TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    event_count INTEGER,
    gap_count INTEGER,
    competitor_count INTEGER,
    UNIQUE(year, week)
);

CREATE INDEX IF NOT EXISTS idx_weekly_reports_year_week ON weekly_reports(year, week);

-- ============================================================================
-- TRIGGERS
-- ============================================================================

-- Auto-update updated_at on gaps table
CREATE TRIGGER IF NOT EXISTS trigger_gaps_updated_at
AFTER UPDATE ON gaps
BEGIN
    UPDATE gaps SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Auto-calculate signal_to_noise_ratio on source_health insert/update
CREATE TRIGGER IF NOT EXISTS trigger_source_health_snr
AFTER INSERT ON source_health
BEGIN
    UPDATE source_health
    SET signal_to_noise_ratio = CAST(events_emitted AS REAL) / NULLIF(events_collected, 0)
    WHERE id = NEW.id;
END;

CREATE TRIGGER IF NOT EXISTS trigger_source_health_snr_update
AFTER UPDATE OF events_collected, events_emitted ON source_health
BEGIN
    UPDATE source_health
    SET signal_to_noise_ratio = CAST(events_emitted AS REAL) / NULLIF(events_collected, 0)
    WHERE id = NEW.id;
END;

-- ============================================================================
-- VIEWS
-- ============================================================================

-- Open gaps by competitor
CREATE VIEW IF NOT EXISTS v_open_gaps AS
SELECT
    competitor,
    gap_type,
    COUNT(*) as gap_count,
    SUM(CASE WHEN severity = 'critical' THEN 1 ELSE 0 END) as critical_count,
    SUM(CASE WHEN severity = 'high' THEN 1 ELSE 0 END) as high_count,
    SUM(CASE WHEN severity = 'medium' THEN 1 ELSE 0 END) as medium_count,
    SUM(CASE WHEN severity = 'low' THEN 1 ELSE 0 END) as low_count
FROM gaps
WHERE status = 'open'
GROUP BY competitor, gap_type
ORDER BY competitor, gap_count DESC;

-- Recent high-severity events
CREATE VIEW IF NOT EXISTS v_recent_high_severity_events AS
SELECT
    event_id,
    timestamp,
    source,
    competitor,
    signal_type,
    severity,
    title,
    url
FROM events
WHERE severity IN ('critical', 'high')
  AND timestamp >= datetime('now', '-7 days')
ORDER BY timestamp DESC;

-- Competitor activity summary (last 30 days)
CREATE VIEW IF NOT EXISTS v_competitor_activity_30d AS
SELECT
    competitor,
    COUNT(*) as total_events,
    SUM(CASE WHEN category = 'conflict' THEN 1 ELSE 0 END) as conflict_events,
    SUM(CASE WHEN category = 'gap' THEN 1 ELSE 0 END) as gap_events,
    SUM(CASE WHEN category = 'intel' THEN 1 ELSE 0 END) as intel_events,
    MAX(timestamp) as last_event
FROM events
WHERE timestamp >= datetime('now', '-30 days')
GROUP BY competitor
ORDER BY total_events DESC;

-- Source signal quality (last 30 days)
CREATE VIEW IF NOT EXISTS v_source_quality_30d AS
SELECT
    source,
    competitor,
    SUM(events_collected) as total_collected,
    SUM(events_emitted) as total_emitted,
    AVG(signal_to_noise_ratio) as avg_snr,
    SUM(error_count) as total_errors
FROM source_health
WHERE date >= date('now', '-30 days')
GROUP BY source, competitor
ORDER BY avg_snr DESC;

-- ============================================================================
-- INITIAL DATA
-- ============================================================================

-- Insert known competitors for reference
INSERT OR IGNORE INTO competitor_snapshots (competitor, snapshot_date, market_position, funding_stage)
VALUES
    ('langgraph', date('now'), 'leader', 'series_b'),
    ('autogen', date('now'), 'challenger', 'big_tech'),
    ('crewai', date('now'), 'challenger', 'series_a'),
    ('autogpt', date('now'), 'niche', 'seed'),
    ('metagpt', date('now'), 'niche', 'academic'),
    ('swarm', date('now'), 'niche', 'big_tech'),
    ('agno', date('now'), 'niche', 'seed'),
    ('browser-use', date('now'), 'niche', 'seed'),
    ('langchain', date('now'), 'leader', 'series_b'),
    ('llama-index', date('now'), 'challenger', 'series_a'),
    ('vercel-ai', date('now'), 'leader', 'series_b'),
    ('langsmith', date('now'), 'leader', 'series_b'),
    ('langgraph-platform', date('now'), 'challenger', 'series_b'),
    ('crewai-enterprise', date('now'), 'challenger', 'series_a'),
    ('autogpt-cloud', date('now'), 'niche', 'seed'),
    ('bedrock-agents', date('now'), 'leader', 'big_tech'),
    ('azure-ai-agents', date('now'), 'leader', 'big_tech'),
    ('vertex-ai-agents', date('now'), 'leader', 'big_tech');