"""Turn messy scraped strings into a price + ISO currency + availability enum."""
from __future__ import annotations

import re

SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY", "₹": "INR"}
CODES = {"GBP", "USD", "EUR", "JPY", "INR", "CAD", "AUD"}

IN_STOCK = re.compile(r"\b(in stock|available|add to (cart|basket)|ready to ship)\b", re.IGNORECASE)
OUT_OF_STOCK = re.compile(r"\b(out of stock|sold out|unavailable|no stock|currently unavailable)\b", re.IGNORECASE)


def parse_price(text: str | None, default_currency: str | None = None) -> tuple[float | None, str | None]:
    if not text:
        return None, default_currency
    currency = default_currency
    for sym, code in SYMBOLS.items():
        if sym in text:
            currency = code
    m = re.search(r"\b([A-Z]{3})\b", text)
    if m and m.group(1) in CODES:
        currency = m.group(1)
    num = re.search(r"\d[\d.,\s]*", text)
    if not num:
        return None, currency
    s = num.group().strip().replace(" ", "")
    if "," in s and "." in s:  # whichever comes last is the decimal separator
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = f"{head.replace(',', '')}.{tail}" if len(tail) in (1, 2) else s.replace(",", "")
    try:
        return round(float(s), 2), currency
    except ValueError:
        return None, currency


def parse_availability(text: str | None) -> str:
    """-> 'in_stock' | 'out_of_stock' | 'unknown'. Out-of-stock wins ('not available' etc.)."""
    if not text:
        return "unknown"
    if OUT_OF_STOCK.search(text) or re.search(r"\bnot available\b", text, re.IGNORECASE):
        return "out_of_stock"
    if IN_STOCK.search(text):
        return "in_stock"
    return "unknown"
