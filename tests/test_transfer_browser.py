from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import monotonic
import unittest

from playwright.sync_api import sync_playwright

from senpilot.models import DownloadError
from senpilot.transfer import DownloadMonitor


class TransferTests(unittest.TestCase):
    def check_transfer(self, stalled):
        stop = Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", "attachment; filename=sample.bin")
                self.send_header("Content-Length", "65536" if stalled else "32768")
                self.end_headers()
                self.wfile.write(b"x" * 32768)
                self.wfile.flush()
                if stalled:
                    stop.wait(10)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with TemporaryDirectory() as directory, sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    channel="chrome", headless=True, downloads_path=str(Path(directory) / "browser"))
                page = browser.new_page(accept_downloads=True)
                monitor = DownloadMonitor(browser, page, Path(directory) / "browser", idle_seconds=0.7)
                try:
                    page.set_content(f'<a href="http://127.0.0.1:{server.server_port}/file">Download</a>')
                    monitor.reset()
                    with page.expect_download() as event:
                        page.get_by_role("link", name="Download").click()
                    download = event.value
                    if stalled:
                        started = monotonic()
                        with self.assertRaises(DownloadError):
                            monitor.wait(page, download)
                        self.assertLess(monotonic() - started, 5)
                    else:
                        details = monitor.wait(page, download)
                        download.save_as(Path(directory) / "saved.bin")
                        self.assertEqual(details["received_bytes"], 32768)
                        self.assertEqual((Path(directory) / "saved.bin").stat().st_size, 32768)
                finally:
                    monitor.close()
                    browser.close()
        finally:
            stop.set()
            server.shutdown()
            server.server_close()
            thread.join()

    def test_completed_transfer_is_saved_through_playwright(self):
        self.check_transfer(stalled=False)

    def test_stalled_transfer_is_canceled_instead_of_waiting_forever(self):
        self.check_transfer(stalled=True)


if __name__ == "__main__":
    unittest.main()
