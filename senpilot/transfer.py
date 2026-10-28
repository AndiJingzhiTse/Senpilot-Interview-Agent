"""Observe Chromium downloads so stalled transfers have a bounded wait."""

from pathlib import Path
from time import monotonic

from .models import DownloadError


class DownloadMonitor:
    def __init__(self, browser, page, directory: Path, idle_seconds=30, maximum_seconds=900):
        directory.mkdir(parents=True, exist_ok=True)
        target = page.context.new_cdp_session(page)
        try:
            context_id = target.send("Target.getTargetInfo")["targetInfo"]["browserContextId"]
        finally:
            target.detach()
        self.session = browser.new_browser_cdp_session()
        self.session.send("Browser.setDownloadBehavior", {
            "behavior": "allowAndName", "browserContextId": context_id,
            "downloadPath": str(directory.resolve()), "eventsEnabled": True,
        })
        self.idle_seconds, self.maximum_seconds = idle_seconds, maximum_seconds
        self.session.on("Browser.downloadWillBegin", self._begin)
        self.session.on("Browser.downloadProgress", self._progress)
        self.reset()

    def reset(self):
        self.guid, self.state = None, "waiting"
        self.received, self.total = 0, 0
        self.started = self.last_progress = monotonic()

    def _begin(self, event):
        self.guid = event["guid"]
        self.state = "inProgress"
        self.last_progress = monotonic()

    def _progress(self, event):
        if event["guid"] != self.guid:
            return
        if event["receivedBytes"] > self.received:
            self.last_progress = monotonic()
        self.received, self.total = event["receivedBytes"], event["totalBytes"]
        self.state = event["state"]

    def wait(self, page, download):
        while self.state != "completed":
            if self.state == "canceled":
                raise DownloadError("The browser canceled the file transfer")
            now = monotonic()
            if now - self.last_progress >= self.idle_seconds or now - self.started >= self.maximum_seconds:
                download.cancel()
                expected = str(int(self.total)) if self.total > 0 else "unknown"
                raise DownloadError(f"Transfer timed out after receiving {int(self.received)} bytes (expected total: {expected})")
            page.wait_for_timeout(100)
        return {"received_bytes": int(self.received), "expected_bytes": int(self.total) if self.total > 0 else None}

    def close(self):
        self.session.detach()
