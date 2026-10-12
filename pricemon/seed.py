"""Self-seeding synthetic demo DB: replays the mock store over 6 simulated days, fully offline (no sockets, no scraping)."""
from __future__ import annotations

import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .alerts import Alerter
from .cli import run_once
from .config import load_site
from .mockstore import render_page
from .store import Store

SITE = Path(__file__).resolve().parent.parent / "sites" / "mock_store.yaml"


class MockFetcher:
    """Duck-typed Fetcher that renders the local mock store for a given simulated day."""

    def __init__(self, day: int):
        self.day, self.rate_limit = day, 0

    def get(self, url: str) -> str:
        page = int(re.search(r"page-(\d+)", url).group(1))
        return render_page(self.day, page) or ""


def seed_demo(db_path: str | None = None, days: int = 6) -> str:
    db_path = db_path or str(Path(tempfile.mkdtemp(prefix="pricemon-")) / "demo.db")
    store, cfg, alerter = Store(db_path), load_site(SITE), Alerter(url="", log_path=None)
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=days - 1)
    for day in range(days):
        run_once([cfg], store, MockFetcher(day), alerter, ts=(start + timedelta(days=day)).isoformat())
    return db_path
