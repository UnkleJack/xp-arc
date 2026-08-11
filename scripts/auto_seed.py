#!/usr/bin/env python3
"""Auto‑seed XP‑Arc with fresh entities.

This script runs as a background cron job. It generates a handful of fresh
seed URLs (both real news/tech sites and random subdomains) and injects
them into the running XP‑Arc daemon via its HTTP ``/api/seed`` endpoint.
The daemon is expected to be running on ``localhost:$XP_ARC_PORT`` (default
8089). Adjust the ``SEED_COUNT`` constant or the ``PORT`` environment
variable as needed.
"""
import os
import json
import random
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration – tweak these values to control behaviour
# ---------------------------------------------------------------------------
SEED_COUNT = 10  # Number of seeds to inject each run
PORT = os.getenv("XP_ARC_PORT", "8089")
ENDPOINT = f"http://localhost:{PORT}/api/seed"

# A small list of real URLs – feel free to extend or source from a file.
REAL_URLS = [
    "https://news.ycombinator.com",
    "https://github.com",
    "https://arxiv.org",
    "https://openai.com",
    "https://huggingface.co",
    "https://techcrunch.com",
    "https://developer.mozilla.org",
    "https://stackoverflow.com",
    "https://gizmodo.com",
    "https://www.reuters.com",
]

# ---------------------------------------------------------------------------
def random_subdomain():
    """Create a plausible random sub‑domain like ``foo.bar.example``.
    The function picks a random base domain from ``REAL_URLS`` (stripping the
    scheme) and prepends a short random label.
    """
    base = random.choice([urllib.parse.urlparse(u).netloc for u in REAL_URLS])
    label = "".join(random.choices("abcdefghijklmnopqrstuvwxyz", k=random.randint(5, 10)))
    return f"https://{label}.{base}"

def generate_seeds(count: int):
    seeds = []
    # Mix real URLs and random subdomains for diversity
    for _ in range(count // 2):
        seeds.append(random.choice(REAL_URLS))
    for _ in range(count - len(seeds)):
        seeds.append(random_subdomain())
    random.shuffle(seeds)
    return seeds

def post_seed(url: str):
    data = json.dumps({"url": url}).encode("utf-8")
    req = urllib.request.Request(ENDPOINT, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "details": e.read().decode("utf-8", errors="ignore")}
    except Exception as e:
        return {"error": str(e)}

def main():
    seeds = generate_seeds(SEED_COUNT)
    results = []
    for url in seeds:
        res = post_seed(url)
        res["seed_url"] = url
        results.append(res)
    # Log a concise JSON line to stdout – the cron job can capture this.
    timestamp = datetime.utcnow().isoformat() + "Z"
    print(json.dumps({"timestamp": timestamp, "results": results}))

if __name__ == "__main__":
    main()
