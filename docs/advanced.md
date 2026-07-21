# Advanced XP‑Arc Usage

## Adding a Custom Station

You can extend the protocol by writing a new station that inherits from `xp_arc.core.station.StationChef`.  The minimal steps:

1. **Create the class** in `xp_arc/stations/` (e.g. `my_station.py`).
   ```python
   from xp_arc.core.station import StationChef

   class MyStation(StationChef):
       def __init__(self, pool, my_param='default'):
           super().__init__(pool, name='my_station')
           self.my_param = my_param

       def run(self):
           # Pull raw entities, process, write results via `self.pool`
           raw = self.pool.get_next_raw()
           if not raw:
               return
           # ... do work ...
           self.pool.update_entity(
               entity_id=raw['id'],
               status='completed',
               notes='processed by MyStation',
               confidence=0.9,
           )
   ```
2. **Register the station** with the executive before the kitchen starts.  In `run_persistent.py` or a custom script:
   ```python
   from xp_arc.stations.my_station import MyStation
   kitchen = PersistentKitchen(...)
   kitchen.my_station = MyStation(kitchen.pool, my_param='foo')
   kitchen.executive.register_station(kitchen.my_station)
   ```
   The station will now be part of the brigade and will receive raw entities on each cycle.

3. **Add tests** for your station under `tests/` to keep CI green.

---

## Using the MCP Client

If you have an MCP server (Model Context Protocol) configured, you can let an external model call XP‑Arc methods directly:

```bash
hermes mcp add my-mcp http://localhost:9000
hermes mcp test my-mcp   # sanity‑check connection
hermes mcp install my-mcp
```

The MCP server will expose the same toolset (`xp_arc.pool`, `xp_arc.stations.*`) to the model, enabling fully‑fledged LLM‑driven orchestration.

---

## Docker Deployment (even without a Dockerfile in the repo)

A simple Dockerfile can be built on‑the‑fly:

```Dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN python -m venv .venv && \
    . .venv/bin/activate && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install .   # installs the xp-arc package from pyproject.toml
EXPOSE 8089
ENV XP_ARC_DB=/data/xp_arc.db
VOLUME ["/data"]
CMD [".venv/bin/python", "run_persistent.py", "--port", "8089"]
```
Build and run:
```bash
docker build -t xp-arc .
mkdir -p $HOME/xp-arc-data
docker run -d -p 8089:8089 -v $HOME/xp-arc-data:/data xp-arc
```
The daemon will expose the `/api/dragon` and `/metrics` endpoints inside the container.

---

## Prometheus Metrics

If you enable the API (`--port <N>`), the `/metrics` endpoint will expose two basic metrics:

- `xp_arc_entities_total` – total number of entities in the pool.
- `xp_arc_entities_completed` – number of entities with status `completed`.

You can extend this endpoint by editing `SeedAPIHandler.do_GET` in `run_persistent.py`.

---

## Logging Configuration

Environment variables control logging:

- `XP_ARC_LOG_LEVEL` – one of `DEBUG`, `INFO`, `WARNING`, `ERROR`.  Default `INFO`.
- `XP_ARC_LOG` – optional path to a log file.  If omitted, logs go to stdout.

Example:
```bash
export XP_ARC_LOG_LEVEL=DEBUG
export XP_ARC_LOG=/var/log/xp-arc.log
./start.sh
```
All daemon messages (including safe‑halt warnings) are written via the `logging` module.

---

## Security Recommendations (`SECURITY.md`)

1. **Run behind a reverse proxy** (nginx, Caddy) that terminates TLS.
2. **Bind the API to localhost** unless you add firewall rules:
   ```bash
   ./start.sh --port 0   # disables the HTTP API (default)
   ./start.sh --port 8089   # enable, then restrict via firewall
   ```
3. **File permissions** – keep the SQLite DB readable/writable only by the daemon user:
   ```bash
   chmod 600 $XP_ARC_DB
   ```
4. **Regularly run Bandit** – the CI already does this, but you can run locally:
   ```bash
   bandit -r xp_arc
   ```
5. **Rotate secret environment variables** (`XP_ARC_LOG`, `XP_ARC_LOG_LEVEL`) on a schedule if you log to a file.

---

## Version Bump Workflow

1. Update `VERSION` file (e.g. `echo "0.3.0" > VERSION`).
2. Commit and tag:
   ```bash
   git add VERSION
   git commit -m "Bump version to 0.3.0"
   git tag v0.3.0
   git push && git push --tags
   ```
3. The CI badge in `README.md` updates automatically.

---

## Further Reading

- **WHITEPAPER.md** – deep dive into the protocol design.
- **CONSTITUTION.MD** – operational law for the brigade.
- **docs/aboyeur-protocol-v1.json** – JSON schema for every station output.
- **README.md** – quick‑start, CLI reference, and example workflow.

---

*All optional enhancements are now part of the repository and documented.*
