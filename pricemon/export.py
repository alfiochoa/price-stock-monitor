"""CSV / XLSX export of the latest snapshot and the full history."""
from __future__ import annotations

import pandas as pd

from .store import Store

LATEST = """SELECT o.site, o.sku, p.name, o.price, o.currency, o.availability, o.ts, p.url
FROM observations o JOIN products p USING(site, sku)
WHERE o.id = (SELECT id FROM observations WHERE site=o.site AND sku=o.sku ORDER BY ts DESC, id DESC LIMIT 1)
ORDER BY o.site, p.name"""
HISTORY = """SELECT o.site, o.sku, p.name, o.ts, o.price, o.currency, o.availability
FROM observations o JOIN products p USING(site, sku) ORDER BY o.site, o.sku, o.ts"""


def frames(store: Store) -> dict[str, pd.DataFrame]:
    q = lambda sql: pd.read_sql_query(sql, store.db)
    return {"latest": q(LATEST), "history": q(HISTORY), "events": q("SELECT * FROM events ORDER BY ts DESC")}


def export(store: Store, path: str) -> str:
    fr = frames(store)
    if path.endswith(".xlsx"):
        with pd.ExcelWriter(path) as xw:
            for name, df in fr.items():
                df.to_excel(xw, sheet_name=name, index=False)
    else:  # CSV: latest snapshot
        fr["latest"].to_csv(path, index=False)
    return path
