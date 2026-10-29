"""Process queued requests sequentially; never automatically repeat uncertain sends."""

from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from .delivery import DeliveryError, prepare_reply
from .messages import MessageError, document_request_candidate, read_message, reply_message
from .packaging import PackagingError, package_report
from .requests import ExtractionError, RequestError, extract_request


def process_job(queue, job: dict, agent_address: str, allowed_senders: set[str] | None, *, extractor="deepseek",
                saved_report: Path | None = None, max_message_bytes=20_000_000, retrieve=None):
    info = job["info"]
    info["extractor"] = extractor
    if extractor == "deepseek":
        info["extraction_model"] = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    if saved_report is None and info.get("saved_report"):
        saved_report = Path(info["saved_report"])
    if saved_report is not None:
        info["saved_report"] = str(saved_report.resolve())
    try:
        incoming = read_message(job["raw"], agent_address)
        if allowed_senders is not None and incoming.sender.casefold() not in {sender.casefold() for sender in allowed_senders}:
            raise MessageError("The sender is not in the configured sender list")
        if allowed_senders is None and not document_request_candidate(incoming.text):
            raise MessageError("The message has no document request cues")
    except MessageError as error:
        queue.finish(job["id"], "ignored", {**info, "reason": str(error)})
        return
    directory = queue.root / "jobs" / job["id"][:24] / f"a{job['attempts']}"
    blocked = False
    try:
        directory.mkdir(parents=True, exist_ok=False)
        try:
            request = extract_request(incoming.text, extractor)
        except RequestError as error:
            raw = reply_message(incoming, agent_address, f"Hello,\n\n{error}\n\nSenpilot document agent").as_bytes()
            delivery = {"attachment": "clarification", "message_bytes": len(raw),
                        "message_sha256": sha256(raw).hexdigest(), "file_count": 0}
        else:
            info["request"] = asdict(request)
            if saved_report is not None:
                report_path = saved_report
                report = json.loads(report_path.read_text(encoding="utf-8"))
                if any(report["request"].get(name) != value for name, value in asdict(request).items()):
                    raise ValueError("The saved retrieval does not match the email request")
            else:
                if retrieve is None:
                    from .retrieval import retrieve
                report = retrieve(request.matter, request.category, directory / "retrieval")
                report_path = directory / "retrieval" / "report.json"
            blocked = report.get("status") == "access_blocked"
            if blocked:
                info["site_access_blocked"] = True
                queue.pause_site(report.get("error") or {"status": "access_blocked"})
            package_path = report_path.parent / "package" / "package.json"
            if not package_path.exists():
                package_report(report_path)
            raw, delivery = prepare_reply(package_path, incoming, agent_address, max_message_bytes)
        if len(raw) > max_message_bytes:
            raise ValueError("The reply exceeds the configured message size limit")
        reply_path = directory / "reply.eml"
        reply_path.write_bytes(raw)
        queue.finish(job["id"], "prepared", {**info, **delivery, "recipient": incoming.sender,
                                             "agent_address": agent_address,
                                             "reply_path": reply_path.relative_to(queue.root).as_posix()})
        return blocked
    except Exception as error:
        # Do not record provider exception bodies, which can contain headers or credentials.
        safe_message = str(error) if isinstance(error, (ExtractionError, DeliveryError, PackagingError)) else "Processing failed; inspect the job and configuration."
        queue.finish(job["id"], "failed", {**info, "error_type": type(error).__name__, "error": safe_message})
        raise


def prepare_pending(queue, agent_address, allowed_senders, *, interval=5, maximum_jobs=None, **kwargs):
    if queue.site_paused():
        print("Site retrieval is paused after an access block; pending requests were not started.", flush=True)
        return
    processed = 0
    while (maximum_jobs is None or processed < maximum_jobs) and (job := queue.claim()) is not None:
        if processed:
            time.sleep(interval)
        try:
            if process_job(queue, job, agent_address, allowed_senders, **kwargs):
                print("Site access was blocked; remaining queued requests were not started.", flush=True)
                break
        except Exception as error:
            print(f"Job {job['id'][:12]} failed: {type(error).__name__}", flush=True)
            if queue.site_paused():
                break
        processed += 1


def send_prepared(queue, provider, agent_address, allowed_senders):
    for job in queue.rows("prepared"):
        info = job["info"]
        if info["agent_address"].casefold() != agent_address.casefold():
            raise ValueError("A prepared reply belongs to a different agent mailbox")
        if allowed_senders is not None and info["recipient"].casefold() not in {value.casefold() for value in allowed_senders}:
            continue
        path = (queue.root / info["reply_path"]).resolve(strict=True)
        if not path.is_relative_to(queue.root.resolve()):
            raise ValueError("The prepared reply path is outside the queue")
        raw = path.read_bytes()
        if sha256(raw).hexdigest() != info["message_sha256"]:
            raise ValueError("The prepared reply changed after validation")
        queue.finish(job["id"], "sending", info)
        try:
            result = provider.send(raw, info.get("thread_id"))
            if not isinstance(result.get("id"), str) or not result["id"]:
                raise RuntimeError("The provider did not return a sent message ID")
        except Exception as error:
            queue.finish(job["id"], "send_uncertain", {**info, "error_type": type(error).__name__})
            raise RuntimeError("Sending did not return confirmation; inspect Sent mail before any retry") from error
        queue.finish(job["id"], "sent", {**info, "sent_message_id": result["id"]})
