"""Streamlit dashboard / Community Cloud entry point. Uses PRICEMON_DB or pricemon.db if present; otherwise self-seeds
synthetic data from the bundled mock store (offline, no scraping, no secrets)."""
import os
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

from pricemon.seed import seed_demo

st.set_page_config(page_title="Price & Stock Monitor", layout="wide")


@st.cache_resource(show_spinner="Seeding synthetic demo data...")
def get_db() -> str:
    return os.getenv("PRICEMON_DB") or ("pricemon.db" if os.path.exists("pricemon.db") else seed_demo())


db = get_db()
con = sqlite3.connect(db, check_same_thread=False)
q = lambda sql, p=(): pd.read_sql_query(sql, con, params=p)

st.title("Price & Stock Monitor")
st.caption("Competitor price & stock tracking · **Demo on synthetic data** (local mock store, 6 simulated days; no real sites scraped)")

obs = q("SELECT o.site, o.sku, p.name, o.ts, o.price, o.currency, o.availability "
        "FROM observations o JOIN products p USING(site, sku)")
if obs.empty:
    st.warning("No data yet. Run `python -m pricemon run`.")
    st.stop()
obs["ts"] = pd.to_datetime(obs["ts"], format="ISO8601")
sites = sorted(obs.site.unique())
site = st.sidebar.selectbox("Site", sites, index=sites.index("mock_store") if "mock_store" in sites else 0)
o = obs[obs.site == site]
o = o.sort_values("ts")
latest = o.groupby("sku").tail(1).drop(columns=["price", "currency"])
# a breakage run stores no price; show the last known price instead of blanks
last_price = o.dropna(subset=["price"]).groupby("sku").tail(1)[["sku", "price", "currency"]]
latest = latest.merge(last_price, on="sku", how="left")
events = q("SELECT ts, kind, name, old, new, pct FROM events WHERE site=? ORDER BY ts DESC", (site,))
runs = q("SELECT ts, items, pages, breakages, errors FROM runs WHERE site=? ORDER BY ts DESC", (site,))

c = st.columns(4)
c[0].metric("Products tracked", len(latest))
c[1].metric("In stock", int((latest.availability == "in_stock").sum()), help="Unknown availability not counted")
c[2].metric("Price changes", int(events.kind.str.startswith("price").sum()))
c[3].metric("Scraper breakages", int(runs.breakages.sum()), delta_color="inverse")

left, right = st.columns([3, 2])
with left:
    st.subheader("Price history")
    names = sorted(o.name.unique())
    pe = events[events.kind.str.startswith("price")]
    default = [n for n in pe.name.unique() if n in names][:4] or names[:3]
    picked = st.multiselect("Products", names, default=default)
    d = o[o.name.isin(picked)]
    if not d.empty:
        fig = px.line(d, x="ts", y="price", color="name", markers=True, line_shape="hv",
                      labels={"ts": "", "price": f"Price ({d.currency.dropna().iloc[0] if d.currency.notna().any() else ''})", "name": ""})
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig, width="stretch")
with right:
    st.subheader("Recent changes")
    ev = events.copy()
    ev["change"] = ev.apply(lambda r: f"{r.pct:+.1f}%" if pd.notna(r.pct) else r.kind.replace("_", " "), axis=1)
    ev["ts"] = ev.ts.str[:10]
    st.dataframe(ev[["ts", "name", "change"]], hide_index=True, height=380, width="stretch")

st.subheader("Scrape health")
runs["ts"] = runs.ts.str[:16].str.replace("T", " ")
runs["status"] = runs.apply(lambda r: "⚠️ breakage" if r.breakages else ("❌ errors" if r.errors else "✅ ok"), axis=1)
st.dataframe(runs[["ts", "status", "items", "pages", "breakages", "errors"]], hide_index=True, width="stretch")

st.subheader("Current snapshot")
snap = latest[["name", "price", "currency", "availability", "ts"]].sort_values("name")
st.dataframe(snap, hide_index=True, width="stretch")
st.download_button("Download snapshot (CSV)", snap.to_csv(index=False), "snapshot.csv", "text/csv")
