"""Simulate 6 days against the local mock store (+ optional live sandbox runs). Writes demo.db."""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pricemon.alerts import Alerter
from pricemon.cli import run_once
from pricemon.config import load_sites
from pricemon.fetch import Fetcher
from pricemon.mockstore import MockServer
from pricemon.store import Store

DB = "demo.db"
for f in (DB, "alerts.log"):
    if os.path.exists(f):
        os.remove(f)
sites = load_sites("sites")
srv = MockServer(8765).start()
store, alerter = Store(DB), Alerter(url="")
start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=5)
for day in range(6):
    srv.set_day(day)
    ts = (start + timedelta(days=day)).isoformat()
    print(f"\n=== simulated day {day} ({ts[:10]}) ===")
    print(run_once([sites["mock_store"]], store, Fetcher(cache_dir=None, rate_limit=0.01), alerter, ts=ts))
if "--live" in sys.argv:  # real (sandbox) sites: books.toscrape.com + webscraper.io test sites, polite & cached
    print("\n=== live sandbox sites ===")
    names = ["books_toscrape", "webscraper_static", "webscraper_js"]
    print(run_once([sites[n] for n in names], store, Fetcher(cache_dir=".cache"), alerter))
srv.stop()
