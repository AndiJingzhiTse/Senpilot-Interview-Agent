from hashlib import sha256
from pathlib import Path
import re
import wave
from zipfile import BadZipFile, ZipFile

from mutagen.mp3 import MP3, HeaderNotFoundError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .models import DownloadError


def safe_filename(original: str) -> str:
    name = original.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip(". ")
    if not name:
        name = "document"
    suffix = Path(name).suffix[:16]
    return name[:100 - len(suffix)] + suffix if len(name) > 100 else name


def unique_path(directory: Path, filename: str) -> Path:
    """Choose a collision free path; the later rename also refuses overwrites."""
    candidate = directory / safe_filename(filename)
    stem, suffix = candidate.stem, candidate.suffix
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate


def validate_file(path: Path, filename: str, matter: str) -> dict:
    """Inspect a completed browser transfer; retain source level format warnings."""
    size = path.stat().st_size
    with path.open("rb") as stream:
        prefix = stream.read(512)
    if size == 0 or prefix.lstrip(b"\xef\xbb\xbf \r\n\t").lower().startswith((b"<!doctype html", b"<html")):
        raise DownloadError("The download is empty or contains an HTML page")
    suffix = Path(filename).suffix.casefold()
    try:
        if suffix == ".pdf":
            if not prefix.startswith(b"%PDF-"):
                raise DownloadError("A PDF filename was returned without PDF contents")
            reader = PdfReader(path)
            if not len(reader.pages):
                raise DownloadError("The downloaded PDF has no pages")
            marker = matter in (reader.pages[0].extract_text() or "") if not reader.is_encrypted else None
            details = {"kind": "pdf", "pages": len(reader.pages), "matter_marker_on_first_page": marker}
        elif prefix[:4] == b"RIFF" and prefix[8:12] == b"WAVE":
            declared_size = int.from_bytes(prefix[4:8], "little") + 8
            with wave.open(str(path), "rb") as audio:
                duration = audio.getnframes() / audio.getframerate()
                if duration <= 0:
                    raise DownloadError("The WAV file has no audio frames")
                details = {"kind": "wav", "duration_seconds": round(duration, 3) if size >= declared_size else None,
                           "channels": audio.getnchannels(), "sample_rate": audio.getframerate(),
                           "declared_extension": suffix, "extension_mismatch": suffix != ".wav",
                           "declared_riff_bytes": declared_size, "header_length_consistent": size >= declared_size}
                if size < declared_size:
                    details["warning"] = "WAV header declares more bytes than the completed browser transfer contains."
        elif suffix == ".mp3":
            audio = MP3(path).info
            if audio.length <= 0:
                raise DownloadError("The MP3 does not contain a positive audio duration")
            details = {"kind": "mp3", "duration_seconds": round(audio.length, 3),
                       "bitrate": audio.bitrate, "sample_rate": audio.sample_rate,
                       "parser_warning": bool(audio.sketchy)}
        elif suffix in {".zip", ".docx", ".xlsx", ".pptx"}:
            with ZipFile(path) as archive:
                details = {"kind": "zip_container", "container_entries": len(archive.infolist())}
        else:
            details = {"kind": "binary", "note": "Completed nonempty download; format not parsed."}
    except (PdfReadError, HeaderNotFoundError, BadZipFile, ValueError, wave.Error, EOFError) as error:
        raise DownloadError(f"File validation failed: {type(error).__name__}") from error
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": size, "sha256": digest.hexdigest(), **details}
