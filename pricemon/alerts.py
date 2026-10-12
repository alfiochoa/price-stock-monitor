"""Webhook alerts. Slack ('text') and Discord ('content') accept the same JSON; mock by default."""
from __future__ import annotations

import json
import os

import requests

from .store import Event


class Alerter:
    def __init__(self, url: str | None = None, kind: str | None = None, log_path: str | None = "alerts.log"):
        self.url = url if url is not None else os.getenv("ALERT_WEBHOOK_URL")
        self.kind = kind or os.getenv("ALERT_WEBHOOK_KIND", "slack")  # slack | discord
        self.log_path = log_path
        self.sent: list[str] = []

    @property
    def mock(self) -> bool:
        return not self.url

    def send(self, text: str) -> None:
        self.sent.append(text)
        if self.mock:  # default: never leaves the machine
            print(f"[mock-alert] {text}")
            if self.log_path:
                with open(self.log_path, "a") as f:
                    f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
            return
        body = {"content": text} if self.kind == "discord" else {"text": text}
        requests.post(self.url, json=body, timeout=10).raise_for_status()

    def price_stock(self, events: list[Event]) -> None:
        if events:
            self.send("*Price/stock changes*\n" + "\n".join(e.describe() for e in events))

    def breakage(self, findings: list[str]) -> None:
        if findings:
            self.send("🚨 *Scraper breakage detected* — selectors need attention\n" + "\n".join(f"• {f}" for f in findings))
