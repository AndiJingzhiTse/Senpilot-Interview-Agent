"""Recognize explicit access blocks without attempting to bypass them."""

from urllib.parse import urlsplit

from .browser import SITE
from .models import SiteAccessBlocked


class AccessMonitor:
    def __init__(self, page):
        self.blocked = None
        page.on("response", self.observe)

    def observe(self, response):
        if response.status in {403, 429} and urlsplit(response.url).hostname == urlsplit(SITE).hostname:
            self.blocked = {"http_status": response.status,
                            "retry_after": response.headers.get("retry-after")}

    def check(self, page):
        if self.blocked is None:
            title = page.title().strip().casefold()
            challenged = title in {"just a moment...", "access denied", "too many requests", "verify you are human"}
            challenged = challenged or page.locator("iframe[src*='challenges.cloudflare.com']").first.is_visible()
            if challenged:
                self.blocked = {"challenge_page": True}
        if self.blocked is not None:
            error = SiteAccessBlocked("The website blocked access or requires human interaction; retrieval stopped")
            error.details = self.blocked
            raise error
