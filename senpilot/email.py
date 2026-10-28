"""Receive requests, prepare replies, and optionally send through dedicated Gmail."""

import argparse
from hashlib import sha256
import math
from pathlib import Path
import sys
import time

from .messages import mailbox
from .queue import JobQueue, worker_lock
from .worker import prepare_pending, send_prepared


def show_status(queue):
    rows = queue.rows()
    if queue.site_paused():
        print("Site retrieval is paused; inspect the access block before using --resume-site.", file=sys.stderr)
    for job in rows:
        print(f"{job['id']} {job['state']} {job['info'].get('attachment', '')}", flush=True)
        if job["state"] == "prepared":
            print(f"Reply preview: {queue.root / job['info']['reply_path']}", flush=True)
        if job["info"].get("error"):
            print(job["info"]["error"], file=sys.stderr)
    unsuccessful = any(row["state"] in {"failed", "processing", "sending", "send_uncertain"}
                       or row["info"].get("attachment") == "oversized"
                       or row["info"].get("retrieval_status") not in {None, "complete", "empty"}
                       for row in rows)
    return 2 if queue.site_paused() or unsuccessful else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Process email requests with a durable local queue")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--eml", type=Path, help="Import a local request without connecting to Gmail")
    source.add_argument("--gmail", action="store_true", help="Poll the dedicated Gmail inbox once")
    source.add_argument("--status", action="store_true", help="List queue state without processing or sending")
    source.add_argument("--retry-job", help="Retry a failed job or interrupted processing job by its full ID")
    parser.add_argument("--agent", help="Agent address for local .eml mode; Gmail mode uses the authorized profile")
    parser.add_argument("--allow-sender", action="append", default=[], help="Accepted requester; repeat for more addresses")
    parser.add_argument("--state", type=Path, default=Path("artifacts/email"))
    parser.add_argument("--token", type=Path, default=Path("artifacts/oauth/token.json"))
    parser.add_argument("--extractor", choices=("deepseek", "exact"), default="deepseek")
    parser.add_argument("--saved-report", type=Path, help="Use a matching saved retrieval, only with --eml")
    parser.add_argument("--max-message-bytes", type=int, default=20_000_000)
    parser.add_argument("--interval", type=float, default=5, help="Seconds between queued jobs, minimum 5")
    parser.add_argument("--send", action="store_true", help="Send prepared replies; requires --gmail")
    parser.add_argument("--watch", action="store_true", help="Continue polling until stopped; requires --gmail")
    parser.add_argument("--poll-seconds", type=float, default=60, help="Seconds between inbox polls, minimum 30")
    parser.add_argument("--resume-site", action="store_true", help="Clear a local pause after resolving a website access block")
    parser.add_argument("--recover-processing", action="store_true", help="Recover interrupted processing, never uncertain sends; requires --gmail")
    args = parser.parse_args(argv)
    if args.send and not args.gmail:
        parser.error("--send requires --gmail")
    if args.watch and not args.gmail:
        parser.error("--watch requires --gmail")
    if args.recover_processing and not args.gmail:
        parser.error("--recover-processing requires --gmail")
    if args.status and args.resume_site:
        parser.error("--status does not change the site pause; use --resume-site with a processing mode")
    if args.saved_report and not args.eml:
        parser.error("--saved-report requires --eml")
    if not args.status and (not args.allow_sender or (not args.gmail and not args.agent)):
        parser.error("Processing requires --allow-sender and local mode also requires --agent")
    if (not math.isfinite(args.interval) or args.interval < 5 or not math.isfinite(args.poll_seconds)
            or args.poll_seconds < 30 or not 100_000 <= args.max_message_bytes <= 25_000_000):
        parser.error("Use finite intervals: --interval at least 5, --poll-seconds at least 30, and a message limit from 100000 to 25000000")
    queue = None
    try:
        with worker_lock(args.state):
            queue = JobQueue(args.state)
            if args.resume_site:
                queue.resume_site()
            if args.status:
                return show_status(queue)
            if args.recover_processing:
                recovery = queue.recover_interrupted()
                print(f"Processing recovery: {recovery}", flush=True)
                if queue.rows("send_uncertain"):
                    print("Sending requires reconciliation before automatic operation can continue.", file=sys.stderr)
                    return 2
            allowed = {mailbox(value).casefold() for value in args.allow_sender}
            provider = None
            if args.gmail:
                from .gmail import Gmail
                provider = Gmail(args.token)
                agent = mailbox(provider.address)
                if args.agent and agent.casefold() != args.agent.casefold():
                    raise ValueError("The authorized Gmail account differs from --agent")
            else:
                agent = mailbox(args.agent)
                if args.eml:
                    if args.eml.stat().st_size > 1024 * 1024:
                        raise ValueError("Incoming message exceeds 1 MB")
                    raw = args.eml.read_bytes()
                    queue.enqueue("eml:" + sha256(raw).hexdigest(), raw)
                else:
                    queue.retry(args.retry_job)
            while True:
                if provider is not None:
                    known = {row["source_id"] for row in queue.rows()}
                    for source_id, raw, thread_id in provider.incoming(known, allowed_senders=allowed):
                        queue.enqueue(source_id, raw, thread_id)
                prepare_pending(queue, agent, allowed, extractor=args.extractor, saved_report=args.saved_report,
                                max_message_bytes=args.max_message_bytes, interval=args.interval)
                if args.send:
                    send_prepared(queue, provider, agent, allowed)
                result = show_status(queue)
                if not args.watch or queue.site_paused():
                    return result
                time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("Email worker stopped; queue state was preserved.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Email workflow failed: {type(error).__name__}", file=sys.stderr)
        print("Check docs/email-setup.md and the queue status; provider response bodies are omitted.", file=sys.stderr)
        if queue is not None:
            show_status(queue)
        return 2
    finally:
        if queue is not None:
            queue.close()


if __name__ == "__main__":
    raise SystemExit(main())
