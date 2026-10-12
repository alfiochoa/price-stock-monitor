"""Per-site YAML selector configs: new sites need no code."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REQUIRED_FIELDS = ("sku", "name", "price")


@dataclass
class Field:
    selector: str
    attr: str | None = None
    regex: str | None = None
    default: str | None = None


@dataclass
class SiteConfig:
    name: str
    base_url: str
    start_urls: list[str]
    item: str
    fields: dict[str, Field]
    render: str = "static"  # static | js
    wait_for: str | None = None  # js only: selector to wait for
    next_page: str | None = None  # selector of the "next" link
    max_pages: int = 3
    currency: str | None = None  # fallback when the price string has no symbol
    rate_limit: float = 1.0  # seconds between requests to this host
    min_fill: float = 0.8  # breakage: share of items that must yield each required field
    extra: dict = field(default_factory=dict)


def load_site(path: str | Path) -> SiteConfig:
    raw = yaml.safe_load(Path(path).read_text())
    fields = {k: Field(**(v if isinstance(v, dict) else {"selector": v})) for k, v in raw["fields"].items()}
    missing = [f for f in REQUIRED_FIELDS if f not in fields]
    if missing:
        raise ValueError(f"{path}: missing required fields {missing}")
    return SiteConfig(
        name=raw["name"], base_url=raw["base_url"], start_urls=raw["start_urls"],
        item=raw["item"], fields=fields, render=raw.get("render", "static"),
        wait_for=raw.get("wait_for"), next_page=raw.get("next_page"),
        max_pages=raw.get("max_pages", 3), currency=raw.get("currency"),
        rate_limit=raw.get("rate_limit", 1.0), min_fill=raw.get("min_fill", 0.8),
    )


def load_sites(directory: str | Path) -> dict[str, SiteConfig]:
    sites = [load_site(p) for p in sorted(Path(directory).glob("*.yaml"))]
    return {s.name: s for s in sites}
