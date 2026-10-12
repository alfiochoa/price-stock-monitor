"""Polite HTTP: robots.txt, User-Agent, per-host rate limit, disk cache, retries with backoff."""
from __future__ import annotations

import hashlib
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

import requests

from . import USER_AGENT

RETRY_STATUS = {429, 500, 502, 503, 504}


class RobotsDisallowed(Exception):
    pass


class FetchError(Exception):
    pass


class Fetcher:
    def __init__(self, cache_dir: str | Path | None = ".cache", cache_ttl: float = 3600,
                 rate_limit: float = 1.0, retries: int = 3, backoff: float = 1.0,
                 session=None, sleep=time.sleep, clock=time.monotonic, ignore_cache: bool = False):
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_ttl, self.rate_limit, self.retries, self.backoff = cache_ttl, rate_limit, retries, backoff
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.sleep, self.clock, self.ignore_cache = sleep, clock, ignore_cache
        self._robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last: dict[str, float] = {}
        self.stats = {"network": 0, "cache_hits": 0, "retries": 0}

    # --- robots -------------------------------------------------------
    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        rp = self._robots.get(origin)
        if rp is None:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.session.get(origin + "/robots.txt", timeout=15)
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                else:  # no robots.txt (4xx) -> allowed; 5xx -> be conservative
                    rp.parse(["User-agent: *", "Disallow: /" if r.status_code >= 500 else "Allow: /"])
            except requests.RequestException:
                rp.parse(["User-agent: *", "Disallow: /"])
            self._robots[origin] = rp
        return rp.can_fetch(USER_AGENT, url)

    # --- cache --------------------------------------------------------
    def _cache_path(self, url: str) -> Path | None:
        return self.cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".html") if self.cache_dir else None

    def _cache_get(self, url: str) -> str | None:
        p = self._cache_path(url)
        if p and not self.ignore_cache and p.exists() and time.time() - p.stat().st_mtime < self.cache_ttl:
            return p.read_text()
        return None

    def _cache_put(self, url: str, text: str) -> None:
        p = self._cache_path(url)
        if p:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)

    # --- fetch --------------------------------------------------------
    def _throttle(self, host: str) -> None:
        wait = self._last.get(host, -1e9) + self.rate_limit - self.clock()
        if wait > 0:
            self.sleep(wait)
        self._last[host] = self.clock()

    def get(self, url: str) -> str:
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        cached = self._cache_get(url)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        host = urlsplit(url).netloc
        last_err: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle(host)
            self.stats["network"] += 1
            try:
                r = self.session.get(url, timeout=20)
                if r.status_code in RETRY_STATUS:
                    last_err = FetchError(f"HTTP {r.status_code} for {url}")
                    delay = float(r.headers.get("Retry-After", 0) or 0)
                else:
                    r.raise_for_status()
                    self._cache_put(url, r.text)
                    return r.text
            except requests.HTTPError as e:  # non-retryable 4xx
                raise FetchError(str(e)) from e
            except requests.RequestException as e:
                last_err, delay = e, 0.0
            if attempt < self.retries:
                self.stats["retries"] += 1
                self.sleep(max(delay, self.backoff * 2**attempt))
        raise FetchError(f"giving up on {url}: {last_err}")

    def render(self, url: str, wait_for: str | None = None) -> str:
        """JS-rendered pages via Playwright (same robots/cache/rate-limit rules)."""
        if not self.allowed(url):
            raise RobotsDisallowed(url)
        cached = self._cache_get(url)
        if cached is not None:
            self.stats["cache_hits"] += 1
            return cached
        from playwright.sync_api import sync_playwright

        self._throttle(urlsplit(url).netloc)
        self.stats["network"] += 1
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=30000)
            if wait_for:
                page.wait_for_selector(wait_for, timeout=15000)
            html = page.content()
            browser.close()
        self._cache_put(url, html)
        return html
