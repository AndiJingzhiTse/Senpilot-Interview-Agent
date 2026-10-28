"""Prepare MIME replies with a measured size limit and verified attachments."""

from hashlib import sha256
import json
from pathlib import Path

from .messages import IncomingMessage, reply_message, result_text
from .packaging import measure


class DeliveryError(RuntimeError):
    pass


def prepare_reply(package_path: Path, incoming: IncomingMessage, agent_address: str,
                  max_message_bytes: int = 20_000_000) -> tuple[bytes, dict]:
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package.get("status") not in {"ready", "partial", "no_files"}:
        raise DeliveryError("The package is not ready for a reply")
    archive = package.get("archive")
    state, payload = "no_files", None
    if archive:
        if archive.get("verified") is not True or archive.get("path") != "documents.zip":
            raise DeliveryError("The ZIP has not been verified or has an unexpected path")
        path = (package_path.parent / "documents.zip").resolve(strict=True)
        if path.parent != package_path.parent.resolve():
            raise DeliveryError("The ZIP resolves outside its package directory")
        with path.open("rb") as stream:
            size, digest = measure(stream)
        if size != archive["bytes"] or digest != archive["sha256"]:
            raise DeliveryError("The ZIP changed after packaging")
        encoded = ((size + 2) // 3) * 4
        estimated_mime = encoded + ((encoded + 75) // 76) * 2 + 65536
        state = "attached" if estimated_mime <= max_message_bytes else "oversized"
        if state == "attached":
            with path.open("rb") as stream:
                payload = stream.read(max_message_bytes + 1)
            if len(payload) != size or sha256(payload).hexdigest() != digest:
                raise DeliveryError("The ZIP changed while preparing the attachment")
    message = reply_message(incoming, agent_address, result_text(package, state))
    if payload is not None:
        message.add_attachment(payload, maintype="application", subtype="zip", filename="documents.zip")
    raw = message.as_bytes()
    if len(raw) > max_message_bytes:
        raise DeliveryError("The encoded email exceeds the configured message size limit")
    return raw, {"attachment": state, "message_bytes": len(raw), "message_sha256": sha256(raw).hexdigest(),
                 "zip_bytes": archive["bytes"] if archive else None,
                 "retrieval_status": package["source_status"], "file_count": package["manifest"]["file_count"]}
