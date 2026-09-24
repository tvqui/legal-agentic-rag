from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timezone

class PlaywrightFetcher:
    """Optional deterministic browser boundary with auditable planned actions."""

    def __init__(self, *args, **kwargs):
        self.action_log: list[dict] = []
        self._available = False
        try:
            import playwright  # noqa: F401
            self._available = True
        except ImportError:
            pass

    def plan_download(self, url: str, selector: str) -> dict:
        action = {"action": "click", "selector": selector, "url": url}
        self.action_log.append(action)
        return action

    def fetch(self, url: str, selector: str, target: str) -> dict:
        self.action_log = []
        self.plan_download(url, selector)
        if not selector:
            raise RuntimeError("PLAYWRIGHT_SELECTOR_NOT_PROVEN")
        if not self._available:
            raise RuntimeError("PLAYWRIGHT_NOT_INSTALLED")
        destination = Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        browser = None
        temp = destination.with_name(f".resolver-{destination.name}.tmp")
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(accept_downloads=True)
                started = datetime.now(timezone.utc).isoformat()
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                with page.expect_download(timeout=30_000) as download_info:
                    page.locator(selector).click(timeout=10_000)
                download = download_info.value
                download.save_as(str(temp))
                os.replace(str(temp), str(destination))
                result = {
                    "page_requested_url": url, "page_final_url": page.url,
                    "requested_url": download.url, "final_url": download.url,
                    "status": 200, "content_type": "",
                    "download_content_type": "",
                    "size_bytes": destination.stat().st_size,
                    "suggested_filename": download.suggested_filename,
                    "download_url": download.url,
                    "action_log": self.action_log + [{
                        "action": "download", "selector": selector, "started_at": started,
                        "final_url": page.url,
                    }],
                }
                return result
        except Exception as exc:
            self.action_log.append({"action": "error", "url": url,
                                    "selector": selector, "error": str(exc)})
            if destination.exists():
                destination.unlink()
            if temp.exists():
                temp.unlink()
            raise
        finally:
            if browser is not None:
                browser.close()
