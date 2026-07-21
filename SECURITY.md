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
- Start the daemon without `--port` (or `--port 0`) to disable the HTTP API entirely.
- If you need remote access, restrict it with a firewall (e.g. `ufw allow from 192.168.1.0/24 to any port 8089`).

## 3. Secure the SQLite database file
- Store the DB in a directory owned by the daemon user only.
- Set permissions to `600` (read/write for owner only):
  ```bash
  chmod 600 $XP_ARC_DB
  ```
- Avoid mounting the DB directory into containers as a shared volume unless you also enforce file permissions inside the container.

## 4. Logging hygiene
- Use the built‑in logging configuration (`XP_ARC_LOG_LEVEL` and `XP_ARC_LOG`).
- Rotate log files regularly (e.g. via `logrotate`).
- Do **not** log raw entity payloads if they may contain sensitive URLs.

## 5. Dependency security scanning
- The CI workflow runs **Bandit** on every push.  Run locally as well:
  ```bash
  bandit -r xp_arc
  ```
- Keep dependencies up‑to‑date (`pip list --outdated`).

## 6. Resource limits
- The daemon is single‑threaded; consider using `cgroups` or Docker resource limits to bound CPU and memory.
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

**Reference**: The `run_persistent.py` source contains the logging configuration and the `SeedAPIHandler` implementation.  Adjust the environment variables `XP_ARC_LOG_LEVEL` and `XP_ARC_LOG` to fit your operational policy.
