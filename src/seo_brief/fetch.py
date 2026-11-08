"""Polite page fetching (robots.txt, custom UA, per-host delay, disk cache) and offline loading."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from . import __version__

USER_AGENT_TOKEN = "seo-brief"
DEFAULT_UA = (
    f"{USER_AGENT_TOKEN}/{__version__} (+https://saizul.com; content research; respects robots.txt)"
)


@dataclass
class FetchResult:
    url: str
    html: str = ""
    status: int = 0
    from_cache: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error and bool(self.html)


class Fetcher:
    def __init__(
        self,
        cache_dir=None,
        delay: float = 2.0,
        user_agent: str = DEFAULT_UA,
        timeout: float = 15.0,
        max_bytes: int = 3_000_000,
        cache_ttl_hours: float = 24 * 7,
        respect_robots: bool = True,
        session=None,
        sleep=time.sleep,
        clock=time.monotonic,
        now=time.time,
    ):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.delay = delay
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.cache_ttl = cache_ttl_hours * 3600
        self.respect_robots = respect_robots
        self.session = session or requests.Session()
        self._sleep = sleep
        self._clock = clock
        self._now = now
        self._last_request: dict = {}
        self._robots: dict = {}

    # -- cache ---------------------------------------------------------
    def _cache_path(self, url: str) -> Path | None:
        if self.cache_dir is None:
            return None
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{digest}.json"

    def _cache_read(self, url: str) -> FetchResult | None:
        path = self._cache_path(url)
        if path is None or not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if self._now() - data.get("fetched_at", 0) > self.cache_ttl:
            return None
        return FetchResult(url, data.get("html", ""), data.get("status", 200), from_cache=True)

    def _cache_write(self, url: str, html: str, status: int) -> None:
        path = self._cache_path(url)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"url": url, "status": status, "fetched_at": self._now(), "html": html}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    # -- politeness ----------------------------------------------------
    def _wait_turn(self, host: str) -> None:
        last = self._last_request.get(host)
        if last is not None:
            remaining = self.delay - (self._clock() - last)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request[host] = self._clock()

    def _headers(self) -> dict:
        return {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}

    def _robots_for(self, url: str) -> RobotFileParser | None:
        """Return a parser for url's host, or None meaning 'everything disallowed'."""
        parts = urlparse(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        robots_url = f"{origin}/robots.txt"
        parser: RobotFileParser | None
        try:
            self._wait_turn(parts.netloc)
            resp = self.session.get(robots_url, headers=self._headers(), timeout=self.timeout)
            status = resp.status_code
            if status == 200:
                parser = RobotFileParser()
                parser.parse(resp.text.splitlines())
            elif 400 <= status < 500:
                parser = RobotFileParser()
                parser.parse([])  # no robots.txt: everything allowed
            else:
                parser = None  # server trouble: be conservative
        except requests.RequestException:
            parser = None
        self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        if parser is None:
            return False
        return parser.can_fetch(USER_AGENT_TOKEN, url)

    # -- main entry ----------------------------------------------------
    def fetch(self, url: str) -> FetchResult:
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            return FetchResult(url, error="unsupported or invalid URL")
        cached = self._cache_read(url)
        if cached is not None:
            return cached
        if not self.allowed(url):
            return FetchResult(url, error="blocked by robots.txt")
        try:
            self._wait_turn(parts.netloc)
            resp = self.session.get(url, headers=self._headers(), timeout=self.timeout)
        except requests.RequestException as exc:
            return FetchResult(url, error=f"request failed: {exc.__class__.__name__}")
        if resp.status_code != 200:
            return FetchResult(url, status=resp.status_code, error=f"HTTP {resp.status_code}")
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if ctype and "html" not in ctype and "xml" not in ctype:
            return FetchResult(url, status=200, error=f"not HTML ({ctype.split(';')[0]})")
        if len(resp.content) > self.max_bytes:
            return FetchResult(url, status=200, error="response too large")
        try:
            html = resp.content.decode("utf-8")
        except UnicodeDecodeError:
            html = resp.text
        self._cache_write(url, html, 200)
        return FetchResult(url, html, 200)


def load_offline(directory) -> list:
    """Read saved *.html / *.htm files; returns [(source_name, html)] sorted by name."""
    folder = Path(directory)
    if not folder.is_dir():
        raise FileNotFoundError(f"offline directory not found: {folder}")
    files = sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".html", ".htm")
    )
    out = []
    for p in files:
        out.append((p.name, p.read_text(encoding="utf-8", errors="replace")))
    return out
