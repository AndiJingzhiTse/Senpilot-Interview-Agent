from pathlib import Path
import re
from time import perf_counter
from uuid import uuid4

from playwright.sync_api import Error, Page, expect

from .browser import close_exports, prepare_export
from .catalog import locate_document
from .files import safe_filename, unique_path, validate_file
from .models import Document, DownloadError


def error_message(error: Exception) -> str:
    message = str(error).splitlines()[0] if str(error) else type(error).__name__
    return re.sub(r"https?://\S+", "[URL omitted]", message)[:400]


def download_once(page: Page, document: Document, output: Path, matter: str, monitor) -> dict:
    row = locate_document(page, document)
    dialog, button, export_name = prepare_export(page, row)
    started = perf_counter()
    monitor.reset()
    with page.expect_download(timeout=60000) as event:
        button.click()
    download = event.value
    transfer = monitor.wait(page, download)
    original = export_name["original"] if export_name else download.suggested_filename
    temporary = output / "incomplete" / f"{uuid4().hex}.part"
    temporary.parent.mkdir(exist_ok=True)
    download.save_as(temporary)
    failure = download.failure()
    if failure:
        raise DownloadError(f"Browser download failed: {failure}")
    validation = validate_file(temporary, download.suggested_filename, matter)
    files = output / "files"
    files.mkdir(exist_ok=True)
    destination = unique_path(files, f"{document.key[:12]}_{safe_filename(original)}")
    dialog.get_by_role("button", name="Close", exact=True).click()
    expect(dialog).not_to_be_visible()
    temporary.rename(destination)
    return {
        "document_key": document.key, "source_id": document.source_id,
        "original_filename": original, "browser_filename": download.suggested_filename,
        "export_filename": export_name, "local_path": destination.relative_to(output).as_posix(),
        "validation": validation, "transfer_seconds": round(perf_counter() - started, 4),
        "browser_transfer": transfer,
    }


def download_document(page: Page, document: Document, output: Path, matter: str, monitor, check_access=None) -> dict:
    """Retry one failed file using a fresh export after cleaning known dialogs."""
    errors = []
    for attempt in range(1, 3):
        if check_access is not None:
            check_access()
        try:
            result = download_once(page, document, output, matter, monitor)
            result.update({"attempts": attempt, "previous_errors": errors})
            return result
        except (Error, DownloadError, OSError) as error:
            errors.append(error_message(error))
            if check_access is not None:
                check_access()
            close_exports(page)
    raise DownloadError("; ".join(errors))
