"""Streamlit dashboard: streamlit run dashboard.py  (DB path via PRICEMON_DB, default demo.db / pricemon.db)"""
import os
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Price & Stock Monitor", layout="wide")
db = os.getenv("PRICEMON_DB") or ("pricemon.db" if os.path.exists("pricemon.db") else "demo.db")
con = sqlite3.connect(db)
q = lambda sql, p=(): pd.read_sql_query(sql, con, params=p)

st.title("Price & Stock Monitor")
st.caption(f"Competitor tracking on sandbox + mock sites · database: `{db}`")

obs = q("SELECT o.site, o.sku, p.name, o.ts, o.price, o.currency, o.availability "
        "FROM observations o JOIN products p USING(site, sku)")
if obs.empty:
    st.warning("No data yet. Run `python -m pricemon run` or `python scripts/demo.py`.")
    st.stop()
obs["ts"] = pd.to_datetime(obs["ts"], format="ISO8601")
sites = sorted(obs.site.unique())
site = st.sidebar.selectbox("Site", sites, index=sites.index("mock_store") if "mock_store" in sites else 0)
o = obs[obs.site == site]
latest = o.sort_values("ts").groupby("sku").tail(1)
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
        st.plotly_chart(fig, use_container_width=True)
with right:
    st.subheader("Recent changes")
    ev = events.copy()
    ev["change"] = ev.apply(lambda r: f"{r.pct:+.1f}%" if pd.notna(r.pct) else r.kind.replace("_", " "), axis=1)
    ev["ts"] = ev.ts.str[:10]
    st.dataframe(ev[["ts", "name", "change"]], hide_index=True, height=380, use_container_width=True)

st.subheader("Scrape health")
runs["ts"] = runs.ts.str[:16].str.replace("T", " ")
runs["status"] = runs.apply(lambda r: "⚠️ breakage" if r.breakages else ("❌ errors" if r.errors else "✅ ok"), axis=1)
st.dataframe(runs[["ts", "status", "items", "pages", "breakages", "errors"]], hide_index=True, use_container_width=True)

st.subheader("Current snapshot")
snap = latest[["name", "price", "currency", "availability", "ts"]].sort_values("name")
st.dataframe(snap, hide_index=True, use_container_width=True)
st.download_button("Download snapshot (CSV)", snap.to_csv(index=False), "snapshot.csv", "text/csv")
