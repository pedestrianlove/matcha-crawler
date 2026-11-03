"""Stock-change tracking and pluggable user notification backends."""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """Strategy interface for notification backends."""

    @abstractmethod
    def notify(self, title: str, message: str) -> None:
        """Send a notification to the user."""


class PlyerNotifier(Notifier):
    """Desktop notifications via plyer."""

    def __init__(self, app_name: str = "Matcha Crawler", timeout: int = 10) -> None:
        self.app_name = app_name
        self.timeout = timeout

    def notify(self, title: str, message: str) -> None:
        from plyer import notification

        notification.notify(
            title=title,
            message=message,
            app_name=self.app_name,
            timeout=self.timeout,
        )


class StockTracker:
    """Track per-variety stock state across polls and notify on restock.

    A notification is sent only on an out-of-stock -> in-stock transition.
    A variety seen for the first time is treated as previously out of stock.
    Products whose crawl failed are skipped so their last known state is kept.
    """

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier
        self._state: dict[tuple[str, str], bool] = {}

    def update(self, results: list[dict[str, Any]]) -> None:
        """Compare crawl results against stored state; send one summary on restock."""
        restocked = False
        lines: list[str] = []
        for product in results:
            if product.get("status") != "success":
                continue
            product_id = product["product_id"]
            name = product.get("title") or product_id
            for variety in product.get("varieties", []):
                key = (product_id, variety["variety"])
                in_stock = bool(variety["in_stock"])
                was_in_stock = self._state.get(key, False)
                self._state[key] = in_stock
                restocked = restocked or (in_stock and not was_in_stock)
                mark = "IN STOCK" if in_stock else "out of stock"
                lines.append(f"{name} - {variety['variety']}: {mark}")
        if restocked:
            self._send("Back in stock!", "\n".join(lines))

    def _send(self, title: str, message: str) -> None:
        try:
            self._notifier.notify(title, message)
        except Exception:
            logger.exception("Notification failed")
