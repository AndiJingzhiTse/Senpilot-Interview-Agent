from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path

from playwright.sync_api import Error, expect, sync_playwright

from .access import AccessMonitor
from .browser import matter_metadata
from .catalog import read_catalog
from .downloads import download_document, error_message
from .models import CATEGORIES, Document, DownloadError, MatterNotFound, RetrievalError, SiteAccessBlocked, selection_order
from .transfer import DownloadMonitor


def write_report(output: Path, report: dict) -> None:
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    temporary.replace(output / "report.json")


def collect_files(documents: list[Document], limit: int, download, report: dict, checkpoint) -> None:
    """Count successful files, skip unavailable entries, and retain individual failures."""
    if not 0 <= limit <= 10:
        raise ValueError("The download limit must be between zero and ten")
    report["unavailable"] = [
        {"document_key": doc.key, "source_id": doc.source_id, "title": doc.title,
         "security": doc.security, "reason": f"Skipped source security label: {doc.security or 'not provided'}"}
        for doc in documents if not doc.available
    ]
    eligible = [doc for doc in selection_order(documents) if doc.available]
    report["eligible_entries"] = len(eligible)
    checkpoint()
    for document in eligible:
        if len(report["downloads"]) == limit:
            break
        try:
            report["downloads"].append(download(document))
        except DownloadError as error:
            report["failures"].append({"document_key": document.key, "source_id": document.source_id,
                                       "title": document.title, "error": error_message(error)})
        report["downloaded_count"] = len(report["downloads"])
        checkpoint()
    report["not_attempted_eligible"] = len(eligible) - len(report["downloads"]) - len(report["failures"])
    report["validation_warning_count"] = sum(
        bool(item.get("validation", {}).get("warning") or item.get("validation", {}).get("parser_warning")
             or item.get("validation", {}).get("extension_mismatch")) for item in report["downloads"])
    report["goal_met"] = len(report["downloads"]) == min(limit, len(eligible))
    report["status"] = "complete" if report["goal_met"] else "partial"
    if limit == 0:
        report["status"] = "metadata_only"
    elif not documents:
        report["status"] = "empty"
    elif not eligible:
        report["status"] = "unavailable"
    checkpoint()


def retrieve(matter: str, category: str, output: Path, limit: int = 10, progress=print) -> dict:
    if category not in CATEGORIES or not 0 <= limit <= 10:
        raise ValueError("Invalid category or download limit")
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "started_utc": datetime.now(timezone.utc).isoformat(), "request": {
            "matter": matter, "category": category, "limit": limit}, "status": "running",
        "transport": "browser_download", "matter": None, "catalog": [], "downloads": [],
        "downloaded_count": 0, "failures": [], "unavailable": [],
        "selection_policy": "Date descending, source identifier or title lexically ascending, then occurrence and document key",
    }
    checkpoint = lambda: write_report(output, report)
    checkpoint()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome", headless=True, downloads_path=str((output / "incomplete" / "browser").resolve()))
            monitor = None
            try:
                page = browser.new_page(accept_downloads=True, viewport={"width": 1600, "height": 1000})
                page.set_default_timeout(30000)
                expect.set_options(timeout=30000)
                access = AccessMonitor(page)
                def checked(action):
                    try:
                        return action()
                    finally:
                        access.check(page)
                monitor = DownloadMonitor(browser, page, output / "incomplete" / "browser")
                report["download_policy"] = {"idle_seconds": monitor.idle_seconds,
                                              "maximum_seconds": monitor.maximum_seconds,
                                              "attempts_per_file": 2}
                progress(f"Looking up {matter}")
                report["matter"] = checked(lambda: matter_metadata(page, matter))
                checkpoint()
                count = report["matter"]["category_counts"][category]
                progress(f"Enumerating {count} {category} entries")
                documents = checked(lambda: read_catalog(page, category, count))
                report["catalog"] = [{"document_key": doc.key, **asdict(doc)} for doc in documents]
                report["duplicate_metadata_entries"] = len(documents) - len({doc.fingerprint for doc in documents})
                report["identity_note"] = "Keys describe source metadata and occurrence within this captured list, not global file IDs."
                def download(doc):
                    progress(f"Downloading {doc.source_id or doc.title}")
                    return checked(lambda: download_document(page, doc, output, matter, monitor,
                                                              check_access=lambda: access.check(page)))
                collect_files(documents, limit, download, report, checkpoint)
            finally:
                try:
                    if monitor is not None:
                        monitor.close()
                finally:
                    browser.close()
    except Exception as error:
        status = "access_blocked" if isinstance(error, SiteAccessBlocked) else "not_found" if isinstance(error, MatterNotFound) else "error"
        report.update({"status": status,
                       "error": {"type": type(error).__name__, "message": error_message(error)}})
        if getattr(error, "details", None) is not None:
            report["error"]["details"] = error.details
        if not isinstance(error, (RetrievalError, Error, OSError, ValueError)):
            raise
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    return report
