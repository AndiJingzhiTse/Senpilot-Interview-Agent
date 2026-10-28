"""Download one public PDF through the browser, with optional HTTP diagnostics."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
from time import perf_counter

from playwright.sync_api import Error, expect, sync_playwright
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from senpilot.browser import SITE, open_matter, prepare_export
from senpilot.models import CATEGORIES

DOWNLOAD_ROUTE = "https://uarb.novascotia.ca/fmi/webd/APP/connector/**/dl/**"


def select_public_row(page, category, row_text):
    """Probe only an exact, visible row; full list traversal is a separate task."""
    page.get_by_role("button", name=re.compile(rf"^{re.escape(category)}\s*-\s*\d+$")).click()
    row = page.get_by_role("row").filter(has=page.get_by_text(row_text, exact=True))
    expect(row).to_have_count(1)
    expect(row).to_be_visible()
    description = row.inner_text()
    if "Public" not in [line.strip() for line in description.splitlines()]:
        raise ValueError("The probe requires a row explicitly labelled Public")
    return row, description


def browser_baseline(page, button, output, matter):
    start = perf_counter()
    with page.expect_download() as event:
        button.click()
    download = event.value
    download.save_as(output / "browser.pdf")
    elapsed = perf_counter() - start
    data = (output / "browser.pdf").read_bytes()
    if not data.startswith(b"%PDF-"):
        raise ValueError("Browser download was not a PDF")
    reader = PdfReader(BytesIO(data))
    if matter not in (reader.pages[0].extract_text() or ""):
        raise ValueError("Downloaded PDF's first page did not identify the requested matter")
    return data, download.url, {
        "filename": download.suggested_filename, "bytes": len(data),
        "sha256": sha256(data).hexdigest(), "pages": len(reader.pages),
        "seconds": round(elapsed, 4), "matter_verified_in_pdf": True,
    }


def http_result(client, url, baseline, headers=None, destination=None):
    """Record failures explicitly and save bytes only when they match the baseline."""
    start = perf_counter()
    try:
        response = client.get(url, headers=headers, timeout=20000, max_redirects=0)
    except Error as error:
        return {"error_type": type(error).__name__, "matches_browser": False}
    try:
        body = response.body()
        matches = response.status == 200 and body == baseline
        if matches and destination is not None:
            destination.write_bytes(body)
        return {
            "status": response.status, "content_type": response.headers.get("content-type"),
            "bytes": len(body), "matches_browser": matches,
            "sha256": sha256(body).hexdigest() if matches else None,
            "seconds": round(perf_counter() - start, 4),
        }
    finally:
        response.dispose()


def capture_without_browser_transfer(page, button):
    """Abort the browser file request locally, retaining its fresh URL for HTTP."""
    captured = []

    def intercept(route):
        captured.append(route.request.url)
        route.abort()

    page.context.route(DOWNLOAD_ROUTE, intercept)
    try:
        with page.expect_event("requestfailed", predicate=lambda request: request.url in captured):
            button.click()
    finally:
        page.context.unroute(DOWNLOAD_ROUTE, intercept)
    if len(captured) != 1:
        raise RuntimeError("Expected exactly one intercepted browser download request")
    return captured[0]


def compare_transports(playwright, page, row, output, matter):
    dialog, button, export_name = prepare_export(page, row)
    data, url, browser = browser_baseline(page, button, output, matter)
    results = {"browser": browser, "export_filename": export_name}
    results["same_session"] = http_result(page.context.request, url, data)
    results["same_session_with_referer"] = http_result(
        page.context.request, url, data, headers={"Referer": SITE})
    isolated = playwright.request.new_context()
    try:
        results["without_browser_cookies"] = http_result(isolated, url, data)
    finally:
        isolated.dispose()
    dialog.get_by_role("button", name="Close", exact=True).click()
    expect(dialog).not_to_be_visible()
    results["after_export_closed"] = http_result(page.context.request, url, data)
    dialog, button, _ = prepare_export(page, row)
    fresh_url = capture_without_browser_transfer(page, button)
    results["http_instead_of_browser"] = http_result(
        page.context.request, fresh_url, data,
        headers={"Referer": SITE}, destination=output / "http.pdf")
    results["http_instead_of_browser"]["browser_file_request_aborted"] = True
    dialog.get_by_role("button", name="Close", exact=True).click()
    expect(dialog).not_to_be_visible()
    results["usable_transport"] = (
        "browser_plus_http" if results["http_instead_of_browser"]["matches_browser"]
        else "browser_download")
    return results


def download_with_browser(page, row, output, matter):
    """Keep the export open until Playwright has saved and validated the PDF."""
    dialog, button, export_name = prepare_export(page, row)
    _, _, browser = browser_baseline(page, button, output, matter)
    dialog.get_by_role("button", name="Close", exact=True).click()
    expect(dialog).not_to_be_visible()
    return {
        "browser": browser, "export_filename": export_name,
        "usable_transport": "browser_download",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matter", default="M12205")
    parser.add_argument("--category", choices=CATEGORIES[:-1], default="Other Documents")
    parser.add_argument("--row-text", default="102674", help="Exact text in one visible public PDF row")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compare-http", action="store_true", help="Run optional HTTP transport diagnostics")
    args = parser.parse_args()
    if re.fullmatch(r"M\d{5}", args.matter) is None:
        parser.error("--matter must be M followed by five digits")
    started = datetime.now(timezone.utc)
    mode = "transport_comparison" if args.compare_http else "browser_download"
    directory = "transport" if args.compare_http else "browser"
    output = args.output or Path("artifacts") / directory / started.strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            page = browser.new_page(accept_downloads=True, viewport={"width": 1600, "height": 1000})
            page.set_default_timeout(20000)
            counts = open_matter(page, args.matter)
            row, description = select_public_row(page, args.category, args.row_text)
            if args.compare_http:
                results = compare_transports(playwright, page, row, output, args.matter)
            else:
                results = download_with_browser(page, row, output, args.matter)
            result = {
                "started_utc": started.isoformat(), "matter": args.matter, "mode": mode,
                "category": args.category, "row_text": description,
                "category_counts": counts,
                "results": results,
            }
            (output / "report.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
            print(f"Report: {output / 'report.json'}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()
