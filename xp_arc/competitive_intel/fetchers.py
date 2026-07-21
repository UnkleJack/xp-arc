"""
Fetchers for Competitive Intelligence Station.
Handles data collection from various sources.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import feedparser
import httpx

logger = logging.getLogger(__name__)


class BaseFetcher:
    """Base class for all fetchers."""

    def __init__(self, station):
        self.station = station
        self.config = station.config

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fetch data and return list of raw events."""
        raise NotImplementedError


class GitHubFetcher(BaseFetcher):
    """Fetch GitHub releases, pushes, issues for watched repositories."""

    def __init__(self, station):
        super().__init__(station)
        self.token = self.config.get("env", {}).get("GITHUB_TOKEN", "")
        self.base_url = "https://api.github.com"
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}" if self.token else "",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        watchlist = source_config.get("watchlist", [])
        events_config = source_config.get("events", [])

        for repo in watchlist:
            try:
                repo_events = await self._fetch_repo_events(repo, events_config)
                events.extend(repo_events)
            except Exception as e:
                logger.error(f"Error fetching GitHub events for {repo}: {e}")

        return events

    async def _fetch_repo_events(
        self, repo: str, event_types: List[str]
    ) -> List[Dict[str, Any]]:
        events = []

        if "release" in event_types:
            releases = await self._fetch_releases(repo)
            events.extend(releases)

        if "push" in event_types:
            pushes = await self._fetch_pushes(repo)
            events.extend(pushes)

        if "issue" in event_types:
            issues = await self._fetch_issues(repo)
            events.extend(issues)

        if "pull_request" in event_types:
            prs = await self._fetch_pull_requests(repo)
            events.extend(prs)

        return events

    async def _fetch_releases(self, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/releases"
        response = await self.client.get(url, params={"per_page": 10})
        response.raise_for_status()
        releases = response.json()

        events = []
        for release in releases:
            events.append(
                {
                    "source": "github",
                    "source_type": "release",
                    "competitor": self._normalize_competitor(repo),
                    "timestamp": release.get("published_at") or release.get("created_at"),
                    "title": f"Release: {release.get('tag_name', 'unknown')}",
                    "summary": release.get("body", "")[:500] if release.get("body") else "",
                    "url": release.get("html_url"),
                    "raw_payload": release,
                    "tags": ["release", "github"],
                }
            )
        return events

    async def _fetch_pushes(self, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/commits"
        response = await self.client.get(url, params={"per_page": 20})
        response.raise_for_status()
        commits = response.json()

        events = []
        for commit in commits[:5]:
            commit_data = commit.get("commit", {})
            events.append(
                {
                    "source": "github",
                    "source_type": "push",
                    "competitor": self._normalize_competitor(repo),
                    "timestamp": commit_data.get("author", {}).get("date"),
                    "title": f"Commit: {commit_data.get('message', '').split(chr(10))[0][:80]}",
                    "summary": commit_data.get("message", "")[:500],
                    "url": commit.get("html_url"),
                    "raw_payload": commit,
                    "tags": ["push", "github", "commit"],
                }
            )
        return events

    async def _fetch_issues(self, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/issues"
        response = await self.client.get(
            url, params={"state": "open", "per_page": 20, "sort": "created", "direction": "desc"}
        )
        response.raise_for_status()
        issues = response.json()

        events = []
        for issue in issues:
            if issue.get("pull_request"):
                continue
            events.append(
                {
                    "source": "github",
                    "source_type": "issue",
                    "competitor": self._normalize_competitor(repo),
                    "timestamp": issue.get("created_at"),
                    "title": f"Issue: {issue.get('title', '')[:80]}",
                    "summary": issue.get("body", "")[:500] if issue.get("body") else "",
                    "url": issue.get("html_url"),
                    "raw_payload": issue,
                    "tags": ["issue", "github"] + [l.get("name") for l in issue.get("labels", [])],
                }
            )
        return events

    async def _fetch_pull_requests(self, repo: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/repos/{repo}/pulls"
        response = await self.client.get(
            url, params={"state": "all", "per_page": 20, "sort": "created", "direction": "desc"}
        )
        response.raise_for_status()
        prs = response.json()

        events = []
        for pr in prs:
            events.append(
                {
                    "source": "github",
                    "source_type": "pull_request",
                    "competitor": self._normalize_competitor(repo),
                    "timestamp": pr.get("created_at"),
                    "title": f"PR: {pr.get('title', '')[:80]}",
                    "summary": pr.get("body", "")[:500] if pr.get("body") else "",
                    "url": pr.get("html_url"),
                    "raw_payload": pr,
                    "tags": ["pull_request", "github"],
                }
            )
        return events

    def _normalize_competitor(self, repo: str) -> str:
        competitor_map = {
            "langchain-ai/langgraph": "langgraph",
            "langchain-ai/langgraphjs": "langgraph",
            "langchain-ai/langgraph-cloud": "langgraph-platform",
            "microsoft/autogen": "autogen",
            "microsoft/autogen.net": "autogen",
            "microsoft/autogen-java": "autogen",
            "crewaiinc/crewai": "crewai",
            "crewaiinc/crewai-examples": "crewai",
            "crewaiinc/crewai-tools": "crewai",
            "significant-gravitas/autogpt": "autogpt",
            "significant-gravitas/autogpt-frontend": "autogpt",
            "significant-gravitas/autogpt-server": "autogpt",
            "geekan/metagpt": "metagpt",
            "openai/swarm": "swarm",
            "agno-agi/agno": "agno",
            "browser-use/browser-use": "browser-use",
            "langchain-ai/langchain": "langchain",
            "langchain-ai/langchainjs": "langchain",
            "langchain-ai/langchain-python": "langchain",
            "run-llama/llama-index": "llama-index",
            "run-llama/llama-index-core": "llama-index",
            "run-llama/llama-index-llms": "llama-index",
            "vercel/ai": "vercel-ai",
            "vercel/ai-chatbot": "vercel-ai",
            "vercel/ai-sdk": "vercel-ai",
        }
        return competitor_map.get(repo, repo.split("/")[-1].lower().replace("-", ""))


class RSSFetcher(BaseFetcher):
    """Fetch RSS/Atom feeds from competitor websites."""

    def __init__(self, station):
        super().__init__(station)
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={
                "User-Agent": "XP-Arc Competitive Intel Bot/0.1 (+https://github.com/unklejack/xp-arc)"
            },
        )

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        feeds = source_config.get("feeds", [])

        for feed_url in feeds:
            try:
                feed_events = await self._fetch_feed(feed_url)
                events.extend(feed_events)
            except Exception as e:
                logger.error(f"Error fetching feed {feed_url}: {e}")

        return events

    async def _fetch_feed(self, feed_url: str) -> List[Dict[str, Any]]:
        response = await self.client.get(feed_url)
        response.raise_for_status()

        feed = feedparser.parse(response.text)
        events = []
        competitor = self._identify_competitor(feed_url)

        for entry in feed.entries[:20]:
            published = self._parse_date(entry)
            if published and published < datetime.now() - timedelta(days=30):
                continue

            events.append(
                {
                    "source": "website",
                    "source_type": "blog_post",
                    "competitor": competitor,
                    "timestamp": published.isoformat() if published else datetime.now().isoformat(),
                    "title": f"Blog: {entry.get('title', 'Untitled')[:100]}",
                    "summary": self._clean_html(entry.get("summary", entry.get("description", "")))[:500],
                    "url": entry.get("link", ""),
                    "raw_payload": {
                        "feed_url": feed_url,
                        "entry_id": entry.get("id", ""),
                        "author": entry.get("author", ""),
                        "tags": [t.get("term", "") for t in entry.get("tags", [])],
                    },
                    "tags": ["blog", "rss", competitor],
                }
            )

        return events

    def _identify_competitor(self, feed_url: str) -> str:
        domain = urlparse(feed_url).netloc.lower()
        competitor_map = {
            "blog.langchain.dev": "langchain",
            "blog.crewai.com": "crewai",
            "www.anthropic.com": "anthropic",
            "openai.com": "openai",
            "aws.amazon.com": "bedrock-agents",
            "azure.microsoft.com": "azure-ai-agents",
            "cloud.google.com": "vertex-ai-agents",
            "huggingface.co": "huggingface",
            "blog.phidata.com": "agno",
        }
        for key, value in competitor_map.items():
            if key in domain:
                return value
        return domain.replace("www.", "").replace(".com", "").replace(".dev", "")

    def _parse_date(self, entry) -> Optional[datetime]:
        for field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if hasattr(entry, field) and getattr(entry, field):
                try:
                    return datetime(*getattr(entry, field)[:6])
                except Exception:
                    pass
        return None

    def _clean_html(self, text: str) -> str:
        if not text:
            return ""
        clean = re.sub(r"<[^>]+>", "", text)
        clean = clean.replace("&nbsp;", " ").replace("&", "&").replace("<", "<").replace(">", ">")
        clean = clean.replace(chr(8220), '"').replace(chr(8221), '"').replace(chr(8216), "'").replace(chr(8217), "'")
        return " ".join(clean.split())


class PyPIFetcher(BaseFetcher):
    """Fetch package releases from PyPI."""

    def __init__(self, station):
        super().__init__(station)
        self.client = httpx.AsyncClient(timeout=15.0)
        self.base_url = "https://pypi.org/pypi"

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        packages = source_config.get("packages", [])

        for package in packages:
            try:
                pkg_events = await self._fetch_package(package)
                events.extend(pkg_events)
            except Exception as e:
                logger.error(f"Error fetching PyPI package {package}: {e}")

        return events

    async def _fetch_package(self, package: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/{package}/json"
        response = await self.client.get(url)
        if response.status_code == 404:
            return []
        response.raise_for_status()

        data = response.json()
        releases = data.get("releases", {})
        info = data.get("info", {})

        events = []
        for version in sorted(releases.keys(), reverse=True)[:5]:
            release_files = releases[version]
            if not release_files:
                continue

            upload_time = release_files[0].get("upload_time_iso_8601", "")
            events.append(
                {
                    "source": "pypi",
                    "source_type": "release",
                    "competitor": self._normalize_package(package),
                    "timestamp": upload_time or datetime.now().isoformat(),
                    "title": f"PyPI Release: {package} {version}",
                    "summary": info.get("summary", "")[:500],
                    "url": f"https://pypi.org/project/{package}/{version}/",
                    "raw_payload": {
                        "package": package,
                        "version": version,
                        "files": len(release_files),
                        "requires_python": info.get("requires_python", ""),
                    },
                    "tags": ["pypi", "release", "python"],
                }
            )

        return events

    def _normalize_package(self, package: str) -> str:
        pkg_map = {
            "langgraph": "langgraph",
            "autogen-agentchat": "autogen",
            "autogen-core": "autogen",
            "autogen-ext": "autogen",
            "crewai": "crewai",
            "crewai-tools": "crewai",
            "autogpt": "autogpt",
            "metagpt": "metagpt",
            "swarm": "swarm",
            "agno": "agno",
            "browser-use": "browser-use",
            "langchain": "langchain",
            "langchain-core": "langchain",
            "langchain-community": "langchain",
            "llama-index": "llama-index",
            "llama-index-core": "llama-index",
            "llama-index-llms": "llama-index",
        }
        return pkg_map.get(package, package.replace("-", "").lower())


class NPMFetcher(BaseFetcher):
    """Fetch package releases from npm registry."""

    def __init__(self, station):
        super().__init__(station)
        self.client = httpx.AsyncClient(timeout=15.0)
        self.base_url = "https://registry.npmjs.org"

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        packages = source_config.get("packages", [])

        for package in packages:
            try:
                pkg_events = await self._fetch_package(package)
                events.extend(pkg_events)
            except Exception as e:
                logger.error(f"Error fetching npm package {package}: {e}")

        return events

    async def _fetch_package(self, package: str) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/{package}"
        response = await self.client.get(url)
        if response.status_code == 404:
            return []
        response.raise_for_status()

        data = response.json()
        versions = data.get("versions", {})
        time_data = data.get("time", {})

        events = []
        for version in sorted(versions.keys(), key=lambda v: time_data.get(v, ""), reverse=True)[:5]:
            ver_data = versions[version]
            publish_time = time_data.get(version, "")
            events.append(
                {
                    "source": "npm",
                    "source_type": "release",
                    "competitor": self._normalize_package(package),
                    "timestamp": publish_time,
                    "title": f"npm Release: {package}@{version}",
                    "summary": ver_data.get("description", "")[:500],
                    "url": f"https://www.npmjs.com/package/{package}/v/{version}",
                    "raw_payload": {
                        "package": package,
                        "version": version,
                        "dependencies": list(ver_data.get("dependencies", {}).keys()),
                        "license": ver_data.get("license", ""),
                    },
                    "tags": ["npm", "release", "javascript"],
                }
            )

        return events

    def _normalize_package(self, package: str) -> str:
        pkg_map = {
            "@langchain/langgraph": "langgraph",
            "autogen": "autogen",
            "crewai": "crewai",
            "swarm": "swarm",
            "langchain": "langchain",
            "llamaindex": "llama-index",
            "@vercel/ai": "vercel-ai",
            "ai": "vercel-ai",
            "@ai-sdk/react": "vercel-ai",
            "@ai-sdk/openai": "vercel-ai",
        }
        return pkg_map.get(package, package.replace("@", "").replace("/", "-").lower())


class HackerNewsFetcher(BaseFetcher):
    """Fetch Hacker News stories matching keywords."""

    def __init__(self, station):
        super().__init__(station)
        self.client = httpx.AsyncClient(timeout=15.0)
        self.base_url = "https://hacker-news.firebaseio.com/v0"

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        keywords = source_config.get("keywords", [])

        for endpoint in ["topstories", "newstories"]:
            story_ids = await self._get_story_ids(endpoint)
            if not story_ids:
                continue

            for story_id in story_ids[:50]:
                try:
                    story = await self._get_story(story_id)
                    if story and self._matches_keywords(story, keywords):
                        events.append(self._story_to_event(story))
                except Exception as e:
                    logger.error(f"Error fetching HN story {story_id}: {e}")

        return events

    async def _get_story_ids(self, endpoint: str) -> List[int]:
        url = f"{self.base_url}/{endpoint}.json"
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def _get_story(self, story_id: int) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/item/{story_id}.json"
        response = await self.client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()

    def _matches_keywords(self, story: Dict[str, Any], keywords: List[str]) -> bool:
        text = f"{story.get('title', '')} {story.get('text', '')}".lower()
        return any(kw.lower() in text for kw in keywords)

    def _story_to_event(self, story: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "source": "hackernews",
            "source_type": "story",
            "competitor": "hackernews",
            "timestamp": datetime.fromtimestamp(story.get("time", 0)).isoformat(),
            "title": f"HN: {story.get('title', '')[:100]}",
            "summary": story.get("text", "")[:500] if story.get("text") else "",
            "url": story.get("url", f"https://news.ycombinator.com/item?id={story.get('id')}"),
            "raw_payload": story,
            "tags": ["hackernews", "discussion"],
        }


class RedditFetcher(BaseFetcher):
    """Fetch Reddit posts from relevant subreddits."""

    def __init__(self, station):
        super().__init__(station)
        self.client = httpx.AsyncClient(timeout=15.0)

    async def fetch(self, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        events = []
        subreddits = source_config.get("subreddits", [])
        keywords = source_config.get("keywords", [])

        for subreddit in subreddits:
            try:
                posts = await self._fetch_subreddit(subreddit, keywords)
                events.extend(posts)
            except Exception as e:
                logger.error(f"Error fetching r/{subreddit}: {e}")

        return events

    async def _fetch_subreddit(self, subreddit: str, keywords: List[str]) -> List[Dict[str, Any]]:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        params = {"limit": 25, "raw_json": 1}
        headers = {"User-Agent": "XP-Arc Competitive Intel Bot/0.1"}

        response = await self.client.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        events = []
        for post in data.get("data", {}).get("children", []):
            post_data = post.get("data", {})
            title = post_data.get("title", "")
            selftext = post_data.get("selftext", "")

            if keywords and not self._matches_keywords(f"{title} {selftext}", keywords):
                continue

            events.append(
                {
                    "source": "reddit",
                    "source_type": "post",
                    "competitor": "reddit",
                    "timestamp": datetime.fromtimestamp(post_data.get("created_utc", 0)).isoformat(),
                    "title": f"Reddit r/{subreddit}: {title[:100]}",
                    "summary": selftext[:500] if selftext else "",
                    "url": f"https://reddit.com{post_data.get('permalink', '')}",
                    "raw_payload": post_data,
                    "tags": ["reddit", subreddit],
                }
            )

        return events

    def _matches_keywords(self, text: str, keywords: List[str]) -> bool:
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in keywords)


async def create_fetcher(station, source_id: str) -> Optional[BaseFetcher]:
    """Factory function to create appropriate fetcher."""
    fetcher_map = {
        "github": GitHubFetcher,
        "pypi": PyPIFetcher,
        "npm": NPMFetcher,
        "crates_io": None,
        "websites": RSSFetcher,
        "x_twitter": None,
        "linkedin": None,
        "hackernews": HackerNewsFetcher,
        "reddit": RedditFetcher,
        "custom_watchlist": None,
    }

    fetcher_class = fetcher_map.get(source_id)
    if fetcher_class:
        return fetcher_class(station)
    return None