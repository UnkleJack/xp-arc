# Releasing XP-Arc

This is a short, practical runbook for cutting a release. Read it once when the
version is a moving target for a PR; skim it when you actually need to ship a tag.

## 1. Cut a version

1. Bump `version` in `pyproject.toml` (e.g. `0.3.0` -> `0.3.1`). This is the
   single source of truth for the package version.
2. Commit that change on `main` (normal PR review, no special process).
3. Tag the commit with an **annotated** tag matching `vX.Y.Z` — the leading
   `v` plus the exact `pyproject.toml` version:

   ```bash
   git tag -a v0.3.1 -m "xp-arc 0.3.1"
   git push origin v0.3.1
   ```

   Use an annotated tag (`-a`), not a lightweight one — it carries a message,
   tagger, and date, which is what you want for a durable release marker.

That push is the only trigger. There is no manual "run release" button;
pushing the tag *is* cutting the release.

## 2. What the `release.yml` workflow does

Defined in `.github/workflows/release.yml`, triggered on `push: tags: v*`:

1. **`test`** — installs `.[dev]` and runs the full pytest suite plus a
   Bandit security scan. Publishing cannot proceed if this fails.
2. **`verify-tag-matches-version`** — reads the pushed tag (`vX.Y.Z`) and
   compares `X.Y.Z` against `project.version` in `pyproject.toml`. If they
   don't match, the workflow fails immediately with an explicit error. This
   is what stops you from accidentally tagging `v0.4.0` when `pyproject.toml`
   still says `0.3.1` (or vice versa).
3. **`build`** — runs `python -m build --sdist --wheel --outdir dist/` and
   uploads the resulting `dist/` directory as a workflow artifact, so you can
   inspect exactly what would be published even before it hits PyPI.
4. **`publish`** — only runs after `build` (and transitively `test` and the
   tag check) succeed. Publishes the built sdist/wheel to PyPI using
   [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC) via
   `pypa/gh-action-pypi-publish` — there is no PyPI API token stored anywhere
   in this repo or its GitHub Actions secrets.

If any job fails, nothing is published. Fix the issue, delete the bad tag
locally and on the remote (`git tag -d vX.Y.Z && git push origin :refs/tags/vX.Y.Z`),
and re-tag once the fix is in.

## 3. One-time PyPI setup (Trusted Publishing)

This only needs to be done once per PyPI project (and again if the repo is
renamed or moves owners):

1. Log into PyPI and go to the `xp-arc` project's **Publishing** settings
   (or, for a brand-new project, https://pypi.org/manage/account/publishing/
   to pre-register a "pending" trusted publisher before the first release).
2. Add a new trusted publisher with:
   - **Owner**: the GitHub org/user hosting this repo
   - **Repository name**: this repo's name
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi` (matches the `environment: name: pypi` in
     the workflow — this lets you additionally require manual approval or
     restrict which branches/tags can deploy via GitHub's environment
     protection rules, if you want that extra gate)
3. Save. No credentials are copied anywhere — GitHub Actions proves its
   identity to PyPI via short-lived OIDC tokens issued per workflow run,
   scoped to that exact repo + workflow + environment.

If the trusted publisher isn't configured yet, the `publish` job will fail
with an authentication error from PyPI — that's expected until step 2 above
is done.

## 4. Building and running the Docker image locally

The `Dockerfile` builds a wheel in a builder stage and installs it into a
slim runtime image running as a non-root user.

```bash
# Build
docker build -t xp-arc:local .

# Run directly
docker run --rm \
  -e XP_ARC_API_KEY=... \
  -e XP_ARC_ABOYEUR_KEY=... \
  -e XP_ARC_MASTER_KEY=... \
  -v xp-arc-pool-data:/data \
  -p 8089:8089 \
  xp-arc:local

# Or via Compose (reads XP_ARC_API_KEY / XP_ARC_ABOYEUR_KEY / XP_ARC_MASTER_KEY
# from your shell environment or an untracked .env file — never hardcode them
# in docker-compose.yml)
export XP_ARC_API_KEY=...
export XP_ARC_ABOYEUR_KEY=...
export XP_ARC_MASTER_KEY=...
docker compose up --build
```

The pool database and DRAGON export JSON live under `/data` inside the
container, backed by the `xp-arc-pool-data` named volume, so they survive
container recreation.

**Known limitation:** `run_persistent.py` currently hardcodes
`web.run_app(app, host='127.0.0.1', ...)` with no `--host`/env override. That
means the HTTP/WebSocket API binds to the container's loopback interface
only, and a normal `-p 8089:8089` port publish will **not** reach it from
outside the container — Docker forwards published ports to the bridge
interface, not loopback. The `HEALTHCHECK` in the Dockerfile still works
because it runs *inside* the container's network namespace. Until
`run_persistent.py` is updated to bind `0.0.0.0` (or read an `XP_ARC_HOST`
env var), the practical options for reaching the API from the host are:

- run the container with `network_mode: host` (Linux only; commented out in
  `docker-compose.yml`), or
- fix the bind address upstream in `run_persistent.py` (tracked as a
  follow-up, intentionally out of scope for this release-infrastructure
  change set).
