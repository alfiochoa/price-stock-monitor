"""CLI: python -m pricemon run|export|mock-serve"""
from __future__ import annotations

import argparse
import sys
import time

from .alerts import Alerter
from .config import load_sites
from .export import export
from .fetch import Fetcher
from .scrape import scrape_site
from .store import Store, now_iso


def run_once(sites, store: Store, fetcher: Fetcher, alerter: Alerter, ts: str | None = None, min_pct: float = 1.0) -> dict:
    ts = ts or now_iso()
    summary = {}
    for cfg in sites:
        res = scrape_site(cfg, fetcher)
        events = store.record(cfg.name, res.items, ts=ts, min_pct=min_pct)
        store.log_run(cfg.name, ts, len(res.items), res.pages, len(res.breakages), len(res.errors))
        alerter.price_stock(events)
        alerter.breakage(res.breakages + res.errors)
        summary[cfg.name] = {"items": len(res.items), "pages": res.pages, "events": len(events),
                             "breakages": len(res.breakages), "errors": len(res.errors)}
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pricemon")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="scrape sites once, store, detect changes, alert")
    r.add_argument("--sites-dir", default="sites")
    r.add_argument("--only", help="comma-separated site names")
    r.add_argument("--db", default="pricemon.db")
    r.add_argument("--min-pct", type=float, default=1.0, help="ignore price moves smaller than this %%")
    r.add_argument("--cache-ttl", type=float, default=3600)
    r.add_argument("--no-cache", action="store_true")
    e = sub.add_parser("export", help="write CSV (latest snapshot) or XLSX (latest+history+events)")
    e.add_argument("path")
    e.add_argument("--db", default="pricemon.db")
    m = sub.add_parser("mock-serve", help="serve the local mock competitor store")
    m.add_argument("--port", type=int, default=8765)
    m.add_argument("--day", type=int, default=0)
    a = ap.parse_args(argv)

    if a.cmd == "run":
        sites = load_sites(a.sites_dir)
        names = a.only.split(",") if a.only else list(sites)
        unknown = [n for n in names if n not in sites]
        if unknown:
            print(f"unknown sites: {unknown}; available: {list(sites)}", file=sys.stderr)
            return 2
        summary = run_once([sites[n] for n in names], Store(a.db),
                           Fetcher(cache_ttl=a.cache_ttl, ignore_cache=a.no_cache), Alerter(), min_pct=a.min_pct)
        for n, s in summary.items():
            print(f"{n}: {s}")
        return 1 if any(s["breakages"] or s["errors"] for s in summary.values()) else 0
    if a.cmd == "export":
        print("wrote", export(Store(a.db), a.path))
        return 0
    from .mockstore import MockServer
    srv = MockServer(a.port, a.day).start()
    print(f"mock store on http://127.0.0.1:{srv.port} (day {a.day}); Ctrl-C to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        srv.stop()
    return 0
