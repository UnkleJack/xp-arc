# XP-Arc Security Recommendations

## Overview
XP-Arc runs a persistent daemon that writes to a local SQLite database and optionally exposes an HTTP API (`/api/dragon`, `/api/seed`, `/metrics`).  Because this daemon can be a target for injection or denial‑of‑service attacks, the following hardening steps are recommended for production deployments.

## 1. Run behind a TLS‑terminating reverse proxy
- Use **nginx**, **Caddy**, **Traefik**, or any TLS‑aware reverse proxy.
- Proxy only the API port (default 8089) and optionally the static DRAGON dashboard.
- Example nginx snippet:
  ```nginx
  server {
      listen 443 ssl;
      server_name xp-arc.example.com;

      ssl_certificate /etc/letsencrypt/live/xp-arc.example.com/fullchain.pem;
      ssl_certificate_key /etc/letsencrypt/live/xp-arc.example.com/privkey.pem;

      location / {
          proxy_pass http://127.0.0.1:8089/;
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
      }
  }
  ```

## 2. Bind the API to localhost (default) unless external access is required
- The daemon binds to `127.0.0.1` by default. `--host` / `XP_ARC_HOST` changes this; binding to `0.0.0.0` without `XP_ARC_API_KEY` prints a startup warning.
- **Set `XP_ARC_API_KEY` whenever the API is reachable beyond localhost.** It protects the REST API, `/ws` and `/metrics`; only `/api/health` is open. Open DRAGON with `http://host:8089/#token=KEY` (the fragment is never sent to the server; access logs redact `?token`).
- `POST /api/seed` validates URLs (public http/https only, 2048-char cap) and is rate-limited to 30 requests/minute per client. Seeds are refused with 503 during a safe halt and its veto window.
- If you need remote access, restrict it with a firewall (e.g. `ufw allow from 192.168.1.0/24 to any port 8089`).

## 3. Secure the SQLite database file
- Store the DB in a directory owned by the daemon user only.
- Set permissions to `600` (read/write for owner only):
  ```bash
  chmod 600 $XP_ARC_DB
  ```
- Avoid mounting the DB directory into containers as a shared volume unless you also enforce file permissions inside the container.

## 4. Logging hygiene
- Use the built‑in logging configuration (`XP_ARC_LOG_LEVEL` and `XP_ARC_LOG`). Access logs redact the `?token` query parameter.
- Rotate log files regularly (e.g. via `logrotate`).
- Do **not** log raw entity payloads if they may contain sensitive URLs.

## 5. Dependency security scanning
- The CI workflow runs the test suite and **Bandit** (`bandit -r xp_arc -ll`) on every push and pull request; a separate Gauntlet workflow runs the red-team harness. Run locally as well:
  ```bash
  bandit -r xp_arc -ll
  ```
- Ruff is available in the `dev` extra but is not run in CI.
- Keep dependencies up‑to‑date (`pip list --outdated`).

## 6. Resource limits
- The daemon is a single asyncio process; consider using `cgroups` or Docker resource limits to bound CPU and memory.
- Example Docker run with limits:
  ```bash
  docker run -d --cpus="1.0" --memory="512m" xp-arc
  ```

## 7. Regular backups
- Periodically copy the SQLite DB to a backup location (e.g. `rsync` to a remote server).
- Use `sqlite3` `VACUUM` to compact the DB after large deletions.

## 8. Graceful shutdown
- The daemon handles `SIGTERM`.  When using systemd, ensure `KillSignal=SIGTERM` and `TimeoutStopSec=` are set appropriately.

## 9. Auditing
- All critical actions (seed injection, safe‑halt recommendations, stop/start events) are logged in the `events` table of the pool.
- Periodically query `SELECT * FROM events ORDER BY id DESC LIMIT 100;` for an audit trail.

---

**Reference**: `run_persistent.py` contains the logging configuration, authentication middleware and the `/api/seed` handler. Adjust `XP_ARC_LOG_LEVEL` and `XP_ARC_LOG` to fit your operational policy.

## 10. Secrets and station keys
- Station HMAC keys are held by the Pool and never exported (test: `tests/test_hmac_key_exposure.py`). Do not commit key files such as `station_keys.json`.
- GRC stations (opt-in `--grc`) require `XP_ARC_CISO_TOKEN`; there is no fallback credential.
- Keys that appear in git history from earlier test and development databases are random per-database values and are no longer in use. See `docs/audits/2026-07-14.md`.
