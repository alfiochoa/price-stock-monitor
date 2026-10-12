"""Selector-config driven extraction + pagination + scraper-breakage detection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import REQUIRED_FIELDS, SiteConfig
from .fetch import Fetcher
from .normalize import parse_availability, parse_price


@dataclass
class Item:
    sku: str
    name: str
    price: float | None
    currency: str | None
    availability: str
    url: str | None = None


@dataclass
class ScrapeResult:
    site: str
    items: list[Item] = field(default_factory=list)
    pages: int = 0
    breakages: list[str] = field(default_factory=list)  # human-readable detector findings
    errors: list[str] = field(default_factory=list)


def _extract(node, spec) -> str | None:
    el = node.select_one(spec.selector) if spec.selector != "." else node
    if el is None:
        return spec.default
    val = el.get(spec.attr) if spec.attr else el.get_text(" ", strip=True)
    if val is None:
        return spec.default
    val = " ".join(val.split()) if isinstance(val, str) else val
    if spec.regex:
        m = re.search(spec.regex, val)
        val = m.group(1 if m.groups() else 0) if m else None
    return val or spec.default


def parse_page(html: str, cfg: SiteConfig, page_url: str) -> tuple[list[Item], dict[str, int], int, str | None]:
    """-> (items, filled-count per field, containers found, next_url)."""
    soup = BeautifulSoup(html, "html.parser")
    nodes = soup.select(cfg.item)
    filled = {f: 0 for f in cfg.fields}
    items = []
    for n in nodes:
        raw = {k: _extract(n, spec) for k, spec in cfg.fields.items()}
        for k, v in raw.items():
            filled[k] += v is not None
        if not raw.get("sku") or not raw.get("name"):
            continue
        price, cur = parse_price(raw.get("price"), cfg.currency)
        url = urljoin(page_url, raw["url"]) if raw.get("url") else None
        items.append(Item(raw["sku"], raw["name"], price, cur, parse_availability(raw.get("availability")), url))
    nxt = None
    if cfg.next_page:
        a = soup.select_one(cfg.next_page)
        if a and a.get("href"):
            nxt = urljoin(page_url, a["href"])
    return items, filled, len(nodes), nxt


def detect_breakage(cfg: SiteConfig, containers: int, filled: dict[str, int], page_url: str) -> list[str]:
    """A selector that silently returns nothing is how scrapers rot; surface it loudly."""
    if containers == 0:
        return [f"{cfg.name}: item selector '{cfg.item}' matched 0 elements on {page_url}"]
    out = []
    for f in REQUIRED_FIELDS:
        if filled[f] / containers < cfg.min_fill:
            out.append(f"{cfg.name}: field '{f}' (selector '{cfg.fields[f].selector}') empty for "
                       f"{containers - filled[f]}/{containers} items on {page_url}")
    return out


def scrape_site(cfg: SiteConfig, fetcher: Fetcher) -> ScrapeResult:
    res = ScrapeResult(cfg.name)
    fetcher.rate_limit = cfg.rate_limit
    seen: set[str] = set()
    for start in cfg.start_urls:
        url: str | None = urljoin(cfg.base_url, start)
        pages = 0
        while url and url not in seen and pages < cfg.max_pages:
            seen.add(url)
            try:
                html = fetcher.render(url, cfg.wait_for) if cfg.render == "js" else fetcher.get(url)
            except Exception as e:  # network/robots problems are reported, not fatal
                res.errors.append(f"{cfg.name}: {type(e).__name__}: {e}")
                break
            items, filled, containers, nxt = parse_page(html, cfg, url)
            res.breakages += detect_breakage(cfg, containers, filled, url)
            res.items += items
            res.pages += 1
            pages += 1
            url = nxt
    return res
