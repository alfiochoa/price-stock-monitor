"""Local mock competitor store whose prices/stock evolve per simulated day.

Lets us demo change detection and breakage alerts without touching any real business.
Day 4 simulates a site redesign (price class renamed) to exercise the breakage detector.
"""
from __future__ import annotations

import http.server
import threading

PRODUCTS = [  # sku, name, base price, category
    ("MK-100", "Trail Runner Shoes", 89.90, "footwear"), ("MK-101", "Wool Hiking Socks", 14.50, "footwear"),
    ("MK-102", "Ultralight Tent 2P", 249.00, "camping"), ("MK-103", "Down Sleeping Bag", 179.00, "camping"),
    ("MK-104", "Titanium Camp Mug", 22.00, "camping"), ("MK-105", "Waterproof Shell Jacket", 139.00, "apparel"),
    ("MK-106", "Merino Base Layer", 64.00, "apparel"), ("MK-107", "Trekking Poles (pair)", 59.90, "gear"),
    ("MK-108", "Headlamp 400lm", 34.90, "gear"), ("MK-109", "Hydration Pack 12L", 74.50, "gear"),
    ("MK-110", "Compact Stove", 41.00, "camping"), ("MK-111", "Insulated Bottle 1L", 27.90, "gear"),
]
PER_PAGE = 5
BREAKAGE_DAY = 4
# day -> sku -> (price multiplier, in_stock)
SCRIPT = {
    1: {"MK-100": (0.90, True), "MK-102": (1.0, False)},
    2: {"MK-100": (0.90, True), "MK-102": (1.0, True), "MK-105": (1.08, True)},
    3: {"MK-103": (0.85, True), "MK-108": (1.0, False), "MK-100": (0.90, True)},
    4: {"MK-103": (0.85, True), "MK-108": (1.0, True), "MK-110": (0.95, True)},
    5: {"MK-103": (0.85, True), "MK-110": (0.95, True), "MK-111": (1.12, False)},
}


def state(day: int) -> list[dict]:
    mods: dict = {}
    for d in sorted(SCRIPT):
        if d <= day:
            mods.update(SCRIPT[d])
    out = []
    for sku, name, price, cat in PRODUCTS:
        mult, stock = mods.get(sku, (1.0, True))
        out.append({"sku": sku, "name": name, "price": round(price * mult, 2), "stock": stock, "cat": cat})
    return out


def render_page(day: int, page: int) -> str | None:
    items = state(day)
    chunk = items[(page - 1) * PER_PAGE: page * PER_PAGE]
    if not chunk:
        return None
    price_cls = "cost" if day >= BREAKAGE_DAY and page == 1 else "price"  # redesign hits page 1 only
    cards = "\n".join(
        f'<div class="product" data-sku="{p["sku"]}"><h2 class="name"><a href="/p/{p["sku"]}.html">{p["name"]}</a></h2>'
        f'<span class="{price_cls}">€{p["price"]:,.2f}</span>'
        f'<span class="stock">{"In stock" if p["stock"] else "Sold out"}</span></div>' for p in chunk)
    nxt = f'<a class="next" href="/catalog/page-{page + 1}.html">Next</a>' if page * PER_PAGE < len(items) else ""
    return f"<!doctype html><html><head><title>MockOutdoor</title></head><body><h1>MockOutdoor catalog</h1>{cards}{nxt}</body></html>"


class _Handler(http.server.BaseHTTPRequestHandler):
    day = 0

    def do_GET(self):
        if self.path == "/robots.txt":
            body, code = "User-agent: *\nDisallow: /admin/\n", 200
        elif self.path.startswith("/catalog/page-"):
            body = render_page(type(self).day, int(self.path.split("page-")[1].split(".")[0])) or ""
            code = 200 if body else 404
        else:
            body, code = "", 404
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *a):
        pass


class MockServer:
    def __init__(self, port: int = 8765, day: int = 0):
        self.handler = type("H", (_Handler,), {"day": day})
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), self.handler)
        self.port = self.httpd.server_address[1]

    def set_day(self, day: int) -> None:
        self.handler.day = day

    def start(self) -> MockServer:
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self.httpd.shutdown()
