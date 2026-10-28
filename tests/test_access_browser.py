from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from playwright.sync_api import sync_playwright

from senpilot.access import AccessMonitor
from senpilot.browser import SITE
from senpilot.downloads import download_document
from senpilot.models import DownloadError, SiteAccessBlocked


class AccessTests(unittest.TestCase):
    def test_http_blocks_and_challenge_pages_are_detected_in_real_chrome(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            try:
                for status, title, expected in [(403, "Forbidden", True), (429, "Rate limited", True),
                                                 (200, "Just a moment...", True), (200, "UARB15", False)]:
                    with self.subTest(status=status, title=title):
                        page = browser.new_page()
                        page.route("**/*", lambda route: route.fulfill(status=status,
                                   headers={"Retry-After": "60"}, content_type="text/html",
                                   body=f"<title>{title}</title><p>Local fixture</p>"))
                        monitor = AccessMonitor(page)
                        page.goto(SITE)
                        if expected:
                            with self.assertRaises(SiteAccessBlocked) as captured:
                                monitor.check(page)
                            if status != 200:
                                self.assertEqual(captured.exception.details["http_status"], status)
                                self.assertEqual(captured.exception.details["retry_after"], "60")
                        else:
                            monitor.check(page)
                        page.close()
            finally:
                browser.close()

    def test_explicit_block_stops_a_file_without_retrying_or_more_ui_actions(self):
        guard = Mock(side_effect=[None, SiteAccessBlocked("Blocked")])
        with patch("senpilot.downloads.download_once", side_effect=DownloadError("Forbidden")) as download, \
                patch("senpilot.downloads.close_exports") as close:
            with self.assertRaises(SiteAccessBlocked):
                download_document(Mock(), Mock(), Path("unused"), "M12205", Mock(), check_access=guard)
        download.assert_called_once()
        close.assert_not_called()


if __name__ == "__main__":
    unittest.main()
