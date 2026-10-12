"""SQLite history + change detection (price drop/rise %, back in stock / out of stock)."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from .scrape import Item

SCHEMA = """
CREATE TABLE IF NOT EXISTS products(site TEXT, sku TEXT, name TEXT, url TEXT, first_seen TEXT,
  PRIMARY KEY(site, sku));
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY, site TEXT, sku TEXT, ts TEXT,
  price REAL, currency TEXT, availability TEXT);
CREATE INDEX IF NOT EXISTS obs_idx ON observations(site, sku, ts);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, site TEXT, sku TEXT, name TEXT, ts TEXT,
  kind TEXT, old TEXT, new TEXT, pct REAL);
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, site TEXT, ts TEXT, items INTEGER,
  pages INTEGER, breakages INTEGER, errors INTEGER);
"""


@dataclass
class Event:
    site: str
    sku: str
    name: str
    ts: str
    kind: str  # price_drop | price_rise | back_in_stock | out_of_stock
    old: str | None
    new: str | None
    pct: float | None = None

    def describe(self) -> str:
        if self.kind in ("price_drop", "price_rise"):
            arrow = "📉" if self.kind == "price_drop" else "📈"
            return f"{arrow} [{self.site}] {self.name}: {self.old} → {self.new} ({self.pct:+.1f}%)"
        icon = "✅" if self.kind == "back_in_stock" else "⛔"
        return f"{icon} [{self.site}] {self.name}: {self.kind.replace('_', ' ')}"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str = "pricemon.db"):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    def record(self, site: str, items: list[Item], ts: str | None = None, min_pct: float = 1.0) -> list[Event]:
        """Insert one observation per item; return change events vs the previous observation."""
        ts = ts or now_iso()
        events: list[Event] = []
        for it in items:
            prev = self.db.execute(
                "SELECT price, availability FROM observations WHERE site=? AND sku=? ORDER BY ts DESC, id DESC LIMIT 1",
                (site, it.sku)).fetchone()
            self.db.execute("INSERT OR IGNORE INTO products VALUES(?,?,?,?,?)", (site, it.sku, it.name, it.url, ts))
            self.db.execute("INSERT INTO observations(site,sku,ts,price,currency,availability) VALUES(?,?,?,?,?,?)",
                            (site, it.sku, ts, it.price, it.currency, it.availability))
            if prev is None:
                continue
            cur = it.currency or ""
            if prev["price"] and it.price and prev["price"] != it.price:
                pct = (it.price - prev["price"]) / prev["price"] * 100
                if abs(pct) >= min_pct:
                    events.append(Event(site, it.sku, it.name, ts, "price_drop" if pct < 0 else "price_rise",
                                        f"{prev['price']:.2f} {cur}".strip(), f"{it.price:.2f} {cur}".strip(), round(pct, 2)))
            a, b = prev["availability"], it.availability
            if a != b and "unknown" not in (a, b):
                events.append(Event(site, it.sku, it.name, ts, "back_in_stock" if b == "in_stock" else "out_of_stock", a, b))
        for e in events:
            self.db.execute("INSERT INTO events(site,sku,name,ts,kind,old,new,pct) VALUES(?,?,?,?,?,?,?,?)",
                            (e.site, e.sku, e.name, e.ts, e.kind, e.old, e.new, e.pct))
        self.db.commit()
        return events

    def log_run(self, site: str, ts: str, items: int, pages: int, breakages: int, errors: int) -> None:
        self.db.execute("INSERT INTO runs(site,ts,items,pages,breakages,errors) VALUES(?,?,?,?,?,?)",
                        (site, ts, items, pages, breakages, errors))
        self.db.commit()
