# syntax=docker/dockerfile:1
#
# XP-Arc Persistent Kitchen — container image.
#
# KNOWN LIMITATION (read before deploying):
#   run_persistent.py currently calls `web.run_app(app, host='127.0.0.1', ...)`
#   with the bind host hardcoded — there is no CLI flag or environment
#   variable to change it. Binding to 127.0.0.1 *inside* the container means
#   the API/WebSocket/dashboard server is only reachable from within the
#   container's own network namespace: a normal `docker run -p 8089:8089`
#   port mapping will NOT be able to reach it, because the container's
#   loopback interface is not the same as the bridge interface Docker
#   forwards published ports to.
#
#   Until run_persistent.py exposes a configurable bind address (e.g. a
#   `--host`/`XP_ARC_HOST` option defaulting to 0.0.0.0 in-container), the
#   practical ways to reach the service from outside the container are:
#     1. Run the container with `network_mode: host` (Linux only, loses
#        network isolation for the daemon), or
#     2. Patch run_persistent.py upstream to read XP_ARC_HOST (recommended
#        follow-up — out of scope for this change set).
#
#   This Dockerfile still EXPOSEs and documents the port, and plumbs an
#   XP_ARC_HOST environment variable through so that the moment the
#   upstream script honors it, nothing else needs to change here.

# ---- Stage 1: builder ----
FROM python:3.12-slim AS builder

WORKDIR /build

# Build tooling only lives in this stage; the runtime image stays lean.
RUN pip install --no-cache-dir --upgrade pip build

COPY pyproject.toml README.md ./
COPY xp_arc ./xp_arc
COPY gauntlet_pkg ./gauntlet_pkg

# Build a wheel so the runtime stage installs a real package artifact
# instead of copying loose source (keeps the two stages honestly decoupled).
RUN python -m build --wheel --outdir /build/dist .

# ---- Stage 2: runtime ----
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="xp-arc" \
      org.opencontainers.image.description="XP-Arc constitutional multi-agent orchestration protocol — persistent kitchen daemon" \
      org.opencontainers.image.licenses="Apache-2.0"

# curl is only used by the HEALTHCHECK below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user.
RUN groupadd --gid 1000 xparc \
    && useradd --uid 1000 --gid xparc --shell /usr/sbin/nologin --create-home xparc

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/dist/
# aiohttp ships in the base [project.dependencies] already; the security
# posture of the daemon (Aboyeur signing, write authorization, station key
# encryption) lives in xp_arc.core and is part of the base install — there
# is currently no separate "security" extra declared in pyproject.toml, so
# the base package install is what actually runs the daemon end to end.
RUN pip install --no-cache-dir /tmp/dist/*.whl && rm -rf /tmp/dist

# run_persistent.py is the daemon entrypoint and is not currently packaged
# as an installed console-script, so it's shipped alongside the app.
COPY run_persistent.py ./run_persistent.py
COPY dragon ./dragon

# Runtime data: pool DB, DRAGON export JSON, and station key material.
# Mount a named volume at /data in production so this survives container
# recreation; see docker-compose.yml.
RUN mkdir -p /data \
    && chown -R xparc:xparc /app /data

# Defaults — override at `docker run` / compose time. No secrets baked in.
ENV XP_ARC_DB=/data/xp_arc.db \
    XP_ARC_PORT=8089 \
    XP_ARC_POLL=0.5 \
    XP_ARC_MAX=500 \
    XP_ARC_LOG_LEVEL=INFO \
    XP_ARC_HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

EXPOSE 8089

USER xparc

# See the KNOWN LIMITATION note at the top of this file: /api/health is
# served on 127.0.0.1 inside the process today, which is still reachable
# from *within* this same container/network-namespace, so the HEALTHCHECK
# below works even though external port publishing currently does not.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${XP_ARC_PORT}/api/health" || exit 1

# Secrets (XP_ARC_API_KEY, XP_ARC_ABOYEUR_KEY, XP_ARC_MASTER_KEY) must be
# supplied at run time via the environment (or a secrets manager / compose
# `environment:`/`env_file:`) — never baked into this image.
ENTRYPOINT ["python", "run_persistent.py"]
CMD ["--db", "/data/xp_arc.db", "--port", "8089"]
