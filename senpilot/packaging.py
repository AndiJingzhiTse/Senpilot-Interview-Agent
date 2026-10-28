"""Package only the completed files recorded by a finished retrieval."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile


CHUNK_SIZE = 1024 * 1024
TERMINAL_STATUSES = {"complete", "partial", "empty", "unavailable", "metadata_only",
                     "not_found", "error", "interrupted", "access_blocked"}


class PackagingError(Exception):
    """The report or its completed files cannot produce a verified package."""


def measure(stream) -> tuple[int, str]:
    digest, size = sha256(), 0
    for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def write_summary(output: Path, summary: dict) -> None:
    temporary = output / "package.json.tmp"
    temporary.write_bytes(json_bytes(summary))
    temporary.replace(output / "package.json")


def build_manifest(report: dict) -> dict:
    if not isinstance(report, dict) or report.get("status") not in TERMINAL_STATUSES:
        raise PackagingError("The report must describe a finished retrieval")
    for name in ("downloads", "catalog", "failures", "unavailable"):
        if not isinstance(report.get(name), list):
            raise PackagingError(f"Report field {name} must be a list")
    count = report.get("downloaded_count")
    if type(count) is not int or count != len(report["downloads"]) or not 0 <= count <= 10:
        raise PackagingError("Completed file count must match the report and be between zero and ten")
    if not isinstance(report.get("request"), dict):
        raise PackagingError("The report must include the original request")
    if count and (not isinstance(report.get("matter"), dict)
                  or report["status"] in {"empty", "unavailable", "metadata_only", "not_found"}):
        raise PackagingError("Completed files conflict with the retrieval status or missing matter metadata")
    catalog = {}
    for source in report["catalog"]:
        if not isinstance(source, dict) or not isinstance(source.get("document_key"), str):
            raise PackagingError("The source catalog contains an invalid identity")
        key = source["document_key"]
        if key in catalog:
            raise PackagingError("The source catalog contains duplicate identities")
        catalog[key] = source
    files, names, keys = [], set(), set()
    for item in report["downloads"]:
        if not isinstance(item, dict) or not isinstance(item.get("document_key"), str):
            raise PackagingError("A completed file is missing its source identity")
        key, relative = item["document_key"], item.get("local_path")
        if key not in catalog or key in keys:
            raise PackagingError("A completed file has an unknown or duplicate source identity")
        if (not isinstance(relative, str) or any(char in relative for char in '\\:<>"|?*')
                or any(ord(char) < 32 for char in relative)):
            raise PackagingError("A completed file has an unsafe local path")
        path = PurePosixPath(relative)
        if len(path.parts) != 2 or path.parts[0] != "files" or path.as_posix() != relative:
            raise PackagingError("Completed files must be direct children of files/")
        if path.name.endswith((".", " ")) or relative.casefold() in names:
            raise PackagingError("Completed filenames must be distinct and safe")
        validation = item.get("validation")
        if (not isinstance(validation, dict) or type(validation.get("bytes")) is not int
                or validation["bytes"] <= 0 or not isinstance(validation.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", validation["sha256"]) is None):
            raise PackagingError("A completed file is missing its recorded size or SHA256")
        if not isinstance(item.get("original_filename"), str):
            raise PackagingError("A completed file is missing its original filename")
        files.append({**item, "archive_path": relative, "source": catalog[key]})
        names.add(relative.casefold())
        keys.add(key)
    return {
        "schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "request": report["request"], "matter": report.get("matter"),
        "retrieval_status": report["status"], "retrieval_started_utc": report.get("started_utc"),
        "retrieval_finished_utc": report.get("finished_utc"), "goal_met": report.get("goal_met"),
        "selection_policy": report.get("selection_policy"), "identity_note": report.get("identity_note"),
        "file_count": count, "uncompressed_file_bytes": sum(item["validation"]["bytes"] for item in files),
        "failures": report["failures"], "unavailable": report["unavailable"],
        "retrieval_error": report.get("error"), "files": files,
    }


def source_path(root: Path, relative: str) -> Path:
    path = root / relative
    resolved = path.resolve(strict=True)
    files = (root / "files").resolve(strict=True)
    if not files.is_relative_to(root) or not resolved.is_relative_to(files) or not resolved.is_file():
        raise PackagingError("A completed file resolves outside the retrieval files directory")
    return resolved


def write_archive(path: Path, root: Path, manifest: dict, contents: bytes) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        archive.writestr("manifest.json", contents)
        for item in manifest["files"]:
            expected = item["validation"]
            digest, size = sha256(), 0
            with source_path(root, item["local_path"]).open("rb") as source:
                with archive.open(item["archive_path"], "w", force_zip64=True) as destination:
                    for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                        destination.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
            if size != expected["bytes"] or digest.hexdigest() != expected["sha256"]:
                raise PackagingError(f"Completed file changed since retrieval: {item['local_path']}")


def verify_archive(path: Path, manifest: dict, contents: bytes) -> None:
    """Read every member back, checking its CRC, file count, size, and SHA256."""
    with ZipFile(path) as archive:
        expected_names = ["manifest.json"] + [item["archive_path"] for item in manifest["files"]]
        if archive.namelist() != expected_names or archive.read("manifest.json") != contents:
            raise PackagingError("Archive members or manifest do not match the completed file list")
        for item in manifest["files"]:
            with archive.open(item["archive_path"]) as stream:
                size, digest = measure(stream)
            if size != item["validation"]["bytes"] or digest != item["validation"]["sha256"]:
                raise PackagingError(f"Archive verification failed: {item['archive_path']}")


def package_report(report_path: Path, output: Path | None = None) -> dict:
    """Create a fresh package directory; never change the retrieval report or files."""
    report_path = report_path.resolve(strict=True)
    root = report_path.parent
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        manifest = build_manifest(report)
    except (ValueError, TypeError) as error:
        raise PackagingError(f"Invalid retrieval report: {error}") from error
    output = output or root / "package"
    output.mkdir(parents=True, exist_ok=False)
    summary = {"status": "building", "source_report": str(report_path),
               "source_status": report["status"], "manifest": manifest, "archive": None}
    temporary, archive = output / "documents.zip.part", output / "documents.zip"
    try:
        if not manifest["file_count"]:
            summary["status"] = "no_files"
        else:
            write_summary(output, summary)
            contents = json_bytes(manifest)
            write_archive(temporary, root, manifest, contents)
            verify_archive(temporary, manifest, contents)
            with temporary.open("rb") as stream:
                size, digest = measure(stream)
            temporary.rename(archive)
            summary["status"] = "ready" if report["status"] == "complete" else "partial"
            summary["archive"] = {"path": archive.name, "bytes": size, "sha256": digest,
                                  "document_count": manifest["file_count"],
                                  "entry_count": manifest["file_count"] + 1, "verified": True}
        write_summary(output, summary)
    except (PackagingError, OSError, BadZipFile, RuntimeError) as error:
        temporary.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        summary.update(status="error", archive=None, error=str(error))
        write_summary(output, summary)
        raise PackagingError(str(error)) from error
    return summary
