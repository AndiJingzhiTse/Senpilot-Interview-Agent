import base64
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from zipfile import ZipFile

from senpilot.delivery import DeliveryError, prepare_reply
from senpilot.email import main as email_main
from senpilot.gmail import Gmail, load_credentials, main as gmail_auth_main
from senpilot.messages import MessageError, read_message
from senpilot.packaging import package_report
from senpilot.queue import JobQueue, worker_lock
from senpilot.requests import DocumentRequest, ExtractionError, RequestError, extract_request, validate_extraction
from senpilot.worker import prepare_pending, process_job, send_prepared


AGENT, SENDER = "agent@example.com", "user@example.com"


def message(text="Please send Other Documents for M12205.", *, sender=SENDER):
    incoming = EmailMessage()
    incoming["From"], incoming["To"], incoming["Subject"] = sender, AGENT, "Document request"
    incoming["Message-ID"] = "<request@example.com>"
    incoming.set_content(text)
    return incoming


class RequestTests(unittest.TestCase):
    def test_exact_request_requires_one_explicit_supported_pair(self):
        self.assertEqual(extract_request("Other Documents for m12205 please", "exact"),
                         DocumentRequest("M12205", "Other Documents"))
        for text in ("M12205", "Other Documents", "Other Documents M12205 M12383",
                     "Other Documents and Exhibits M12205", "Other Documents M122050", "M12205 invoices"):
            with self.subTest(text=text), self.assertRaises(RequestError):
                extract_request(text, "exact")

    def test_model_cannot_invent_request_values_or_delivery_fields(self):
        valid = {"matter": "M12205", "category": "Other Documents", "needs_clarification": False}
        self.assertEqual(validate_extraction(valid, "M12205 Other Documents"), DocumentRequest("M12205", "Other Documents"))
        for data in ({**valid, "matter": "M99999"}, {**valid, "recipient": "attacker@example.com"},
                     {**valid, "category": "Invoices"}, {**valid, "needs_clarification": "false"}):
            with self.subTest(data=data), self.assertRaises(ExtractionError):
                validate_extraction(data, "M12205 Other Documents")
        with self.assertRaises(RequestError):
            validate_extraction({**valid, "needs_clarification": True}, "Do not download M12205 Other Documents")

    def response(self, payload):
        result = Mock()
        result.__enter__ = Mock(return_value=BytesIO(json.dumps(payload).encode()))
        result.__exit__ = Mock(return_value=False)
        return result

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-not-a-real-key", "DEEPSEEK_MODEL": "test-model"})
    def test_structured_api_contract_without_a_live_api_call(self):
        output = {"matter": "M12205", "category": "Other Documents", "needs_clarification": False}
        response = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}]}
        with patch("senpilot.requests.urlopen", return_value=self.response(response)) as call:
            self.assertEqual(extract_request("M12205 Other Documents"), DocumentRequest("M12205", "Other Documents"))
        request = call.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertIn('"additionalProperties": false', payload["messages"][0]["content"])

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-not-a-real-key", "DEEPSEEK_MODEL": "test-model"})
    def test_refusal_incomplete_and_rate_limit_are_not_accepted_as_requests(self):
        for response, error in [({"choices": [{"finish_reason": "length"}]}, ExtractionError),
                                ({"choices": [{"finish_reason": "content_filter"}]}, RequestError),
                                ({"choices": []}, ExtractionError),
                                ({"choices": [{"finish_reason": "stop", "message": {"content": ""}}]}, ExtractionError)]:
            with self.subTest(response=response), patch("senpilot.requests.urlopen", return_value=self.response(response)):
                with self.assertRaises(error):
                    extract_request("M12205 Other Documents")
        with patch("senpilot.requests.urlopen", side_effect=HTTPError("https://api.deepseek.com", 429, "limited", {}, None)):
            with self.assertRaisesRegex(ExtractionError, "HTTP 429"):
                extract_request("M12205 Other Documents")

    def test_missing_api_credentials_never_falls_back_silently(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ExtractionError):
            extract_request("M12205 Other Documents")


class MessageTests(unittest.TestCase):
    def test_plain_body_preferred_and_quoted_requests_and_attachments_ignored(self):
        incoming = message("M12205 Other Documents\n> M12383 Exhibits\nOn Monday someone wrote:\nM99999 Recordings")
        incoming.add_alternative("<p>M99999 Recordings</p>", subtype="html")
        incoming.add_attachment(b"M99999 Recordings", maintype="application", subtype="octet-stream", filename="ignore.txt")
        parsed = read_message(incoming.as_bytes(), AGENT)
        self.assertEqual(extract_request(parsed.text, "exact"), DocumentRequest("M12205", "Other Documents"))

    def test_html_only_body_is_supported_without_executing_scripts(self):
        incoming = message()
        incoming.set_content("<p>M12205 Other Documents</p><script>M99999 Exhibits</script>", subtype="html")
        self.assertEqual(extract_request(read_message(incoming.as_bytes(), AGENT).text, "exact"),
                         DocumentRequest("M12205", "Other Documents"))

    def test_automatic_bulk_self_and_multiple_senders_are_ignored(self):
        for kind in ("automatic", "bulk", "self", "multiple"):
            incoming = message()
            if kind == "automatic":
                incoming["Auto-Submitted"] = "auto-replied"
            elif kind == "bulk":
                incoming["List-Id"] = "list.example.com"
            else:
                incoming.replace_header("From", AGENT if kind == "self" else SENDER + ", second@example.com")
            with self.subTest(kind=kind), self.assertRaises(MessageError):
                read_message(incoming.as_bytes(), AGENT)

    def test_unknown_charset_is_ignored_as_an_invalid_message(self):
        raw = message().as_bytes().replace(b'charset="utf-8"', b'charset="not-a-real-encoding"')
        with self.assertRaises(MessageError):
            read_message(raw, AGENT)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "saved"
        (self.source / "files").mkdir(parents=True)
        self.report_path = self.source / "report.json"
        self.payload = b"document source bytes" * 100
        (self.source / "files/identity_filing.txt").write_bytes(self.payload)
        self.report = {
            "status": "complete", "request": {"matter": "M12205", "category": "Other Documents", "limit": 10},
            "matter": {"matter_number": "M12205", "title": "Water project", "type": "Water", "category": "Capital expenditure",
                       "dates": {"Date Received": "04/07/2025", "Decision Date": None},
                       "category_counts": {"Exhibits": 13, "Key Documents": 6, "Other Documents": 43, "Transcripts": 0, "Recordings": 0}},
            "downloads": [{"document_key": "identity", "original_filename": "filing.txt", "local_path": "files/identity_filing.txt",
                           "validation": {"bytes": len(self.payload), "sha256": sha256(self.payload).hexdigest()}}],
            "catalog": [{"document_key": "identity", "title": "Filing", "date": None}],
            "failures": [], "unavailable": [], "downloaded_count": 1,
        }
        self.save()
        self.queue = JobQueue(self.root / "queue")
        self.addCleanup(self.queue.close)

    def save(self):
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")

    def package(self):
        package_report(self.report_path)
        return self.source / "package/package.json"

    def enqueue(self, raw=None, source="gmail:agent:test", thread="thread-1"):
        self.queue.enqueue(source, raw or message().as_bytes(), thread)
        return self.queue.claim()

    def process(self, job):
        process_job(self.queue, job, AGENT, {SENDER}, extractor="exact", saved_report=self.report_path)
        return self.queue.rows()[0]

    def test_reply_attaches_verified_bytes_and_uses_source_labels_and_counts(self):
        incoming = message()
        incoming["Reply-To"] = "other@example.com"
        raw, info = prepare_reply(self.package(), read_message(incoming.as_bytes(), AGENT), AGENT)
        reply = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(reply["To"].addresses[0].addr_spec, SENDER)
        self.assertEqual(reply["In-Reply-To"], "<request@example.com>")
        self.assertEqual(reply["Auto-Submitted"], "auto-replied")
        text = reply.get_body(preferencelist=("plain",)).get_content()
        self.assertIn("Total category entries: 62", text)
        self.assertIn("not a unique file count", text)
        self.assertIn("Decision Date: Not provided", text)
        self.assertNotIn("final filing", text)
        attachments = list(reply.iter_attachments())
        self.assertEqual(len(attachments), 1)
        with ZipFile(BytesIO(attachments[0].get_content())) as archive:
            self.assertEqual(archive.read("files/identity_filing.txt"), self.payload)
        self.assertEqual(info["attachment"], "attached")
        self.assertLessEqual(info["message_bytes"], 20_000_000)

    def test_oversized_reply_has_no_attachment_and_does_not_claim_delivery(self):
        payload = os.urandom(200000)
        (self.source / "files/identity_filing.txt").write_bytes(payload)
        self.report["downloads"][0]["validation"] = {"bytes": len(payload), "sha256": sha256(payload).hexdigest()}
        self.save()
        raw, info = prepare_reply(self.package(), read_message(message().as_bytes(), AGENT), AGENT, 100000)
        reply = BytesParser(policy=policy.default).parsebytes(raw)
        self.assertEqual(info["attachment"], "oversized")
        self.assertEqual(list(reply.iter_attachments()), [])
        self.assertIn("No ZIP is attached", reply.get_content())
        self.assertLess(len(raw), 100000)

    def test_changed_zip_is_rejected_before_sending(self):
        path = self.package()
        with (path.parent / "documents.zip").open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(DeliveryError):
            prepare_reply(path, read_message(message().as_bytes(), AGENT), AGENT)

    def test_empty_and_partial_replies_are_explicit(self):
        original = deepcopy(self.report)
        self.report.update(status="empty", downloads=[], downloaded_count=0)
        self.save()
        raw, info = prepare_reply(self.package(), read_message(message().as_bytes(), AGENT), AGENT)
        self.assertEqual(info["attachment"], "no_files")
        self.assertIn(b"Retrieval status: empty", raw)
        self.report = original
        self.report["status"] = "partial"
        self.report["failures"] = [{"error": "Transfer timed out"}]
        self.save()
        output = self.source / "partial-package"
        package_report(self.report_path, output)
        raw, info = prepare_reply(output / "package.json", read_message(message().as_bytes(), AGENT), AGENT)
        self.assertEqual(info["attachment"], "attached")
        self.assertIn(b"Retrieval status: partial", raw)
        self.assertIn(b"Failed files: 1", raw)

    def test_duplicate_provider_id_is_processed_only_once(self):
        raw = message().as_bytes()
        self.assertTrue(self.queue.enqueue("same", raw))
        self.assertFalse(self.queue.enqueue("same", message("different request").as_bytes()))
        self.process(self.queue.claim())
        self.assertIsNone(self.queue.claim())
        self.assertEqual(len(self.queue.rows()), 1)
        self.assertEqual(self.queue.rows()[0]["state"], "prepared")

    def test_clarification_never_starts_a_retrieval(self):
        job = self.enqueue(message("Please send files").as_bytes())
        row = self.process(job)
        self.assertEqual(row["info"]["attachment"], "clarification")
        self.assertFalse((self.source / "package").exists())

    def test_unlisted_senders_are_ignored_without_a_reply(self):
        row = self.process(self.enqueue(message(sender="stranger@example.com").as_bytes()))
        self.assertEqual(row["state"], "ignored")
        self.assertNotIn("reply_path", row["info"])

    def test_saved_report_must_match_the_request(self):
        job = self.enqueue(message("M12383 Exhibits").as_bytes())
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.process(job)
        self.assertEqual(self.queue.rows()[0]["state"], "failed")

    def test_pipeline_connects_request_retrieval_packaging_and_reply(self):
        def retrieve(matter, category, output):
            self.assertEqual((matter, category), ("M12205", "Other Documents"))
            shutil.copytree(self.source, output)
            return deepcopy(self.report)
        callback = Mock(side_effect=retrieve)
        job = self.enqueue()
        process_job(self.queue, job, AGENT, {SENDER}, extractor="exact", retrieve=callback)
        self.assertEqual(callback.call_count, 1)
        row = self.queue.rows()[0]
        self.assertEqual(row["state"], "prepared")
        self.assertEqual(row["info"]["attachment"], "attached")
        self.assertTrue((self.queue.root / row["info"]["reply_path"]).is_file())

    def test_access_block_pauses_remaining_jobs_and_survives_the_next_run(self):
        self.queue.enqueue("first", message().as_bytes())
        self.queue.enqueue("second", message().as_bytes())
        self.report["status"] = "access_blocked"
        self.save()
        callback = Mock()
        prepare_pending(self.queue, AGENT, {SENDER}, extractor="exact", saved_report=self.report_path, interval=0)
        rows = self.queue.rows()
        self.assertEqual([row["state"] for row in rows], ["prepared", "pending"])
        self.assertTrue(self.queue.site_paused())
        other_connection = JobQueue(self.queue.root)
        try:
            self.assertTrue(other_connection.site_paused())
            prepare_pending(other_connection, AGENT, {SENDER}, extractor="exact", retrieve=callback, interval=0)
            callback.assert_not_called()
            other_connection.resume_site()
        finally:
            other_connection.close()
        self.assertFalse(self.queue.site_paused())

    def test_confirmed_send_is_not_repeated(self):
        self.process(self.enqueue())
        provider = Mock()
        provider.send.return_value = {"id": "sent-1"}
        send_prepared(self.queue, provider, AGENT, {SENDER})
        send_prepared(self.queue, provider, AGENT, {SENDER})
        self.assertEqual(provider.send.call_count, 1)
        self.assertEqual(self.queue.rows()[0]["state"], "sent")
        self.assertEqual(provider.send.call_args.args[1], "thread-1")

    def test_lost_send_confirmation_requires_reconciliation_and_is_not_retried(self):
        self.process(self.enqueue())
        provider = Mock()
        provider.send.side_effect = TimeoutError("Response lost")
        with self.assertRaisesRegex(RuntimeError, "inspect Sent"):
            send_prepared(self.queue, provider, AGENT, {SENDER})
        send_prepared(self.queue, provider, AGENT, {SENDER})
        row = self.queue.rows()[0]
        self.assertEqual(provider.send.call_count, 1)
        self.assertEqual(row["state"], "send_uncertain")
        with self.assertRaises(ValueError):
            self.queue.retry(row["id"])

    def test_sender_and_agent_are_rechecked_before_send(self):
        self.process(self.enqueue())
        provider = Mock()
        send_prepared(self.queue, provider, AGENT, {"someone@example.com"})
        provider.send.assert_not_called()
        with self.assertRaises(ValueError):
            send_prepared(self.queue, provider, "wrong@example.com", {SENDER})

    def test_worker_lock_rejects_concurrency_and_releases_after_failure(self):
        root = self.root / "lock-test"
        with self.assertRaisesRegex(RuntimeError, "worker lock"), worker_lock(root):
            with worker_lock(root):
                self.fail("A second worker entered the lock")
        with worker_lock(root):
            self.assertTrue((root / "worker.lock").exists())

    def test_failed_extraction_is_persisted_and_explicit_retry_can_resume(self):
        self.queue.enqueue("failed-extraction", message().as_bytes())
        with patch.dict(os.environ, {}, clear=True):
            prepare_pending(self.queue, AGENT, {SENDER}, saved_report=self.report_path, interval=0)
        row = self.queue.rows()[0]
        self.assertEqual(row["state"], "failed")
        self.queue.retry(row["id"])
        prepare_pending(self.queue, AGENT, {SENDER}, extractor="exact", saved_report=self.report_path, interval=0)
        row = self.queue.rows()[0]
        self.assertEqual(row["state"], "prepared")
        self.assertEqual(row["attempts"], 2)

    def test_real_local_cli_reuses_a_saved_report_and_deduplicates_on_restart(self):
        path = self.root / "request.eml"
        path.write_bytes(message().as_bytes())
        state = self.root / "cli-queue"
        command = [sys.executable, "-m", "senpilot.email", "--eml", str(path), "--agent", AGENT,
                   "--allow-sender", SENDER, "--extractor", "exact", "--saved-report", str(self.report_path),
                   "--state", str(state)]
        for _ in range(2):
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        queue = JobQueue(state)
        try:
            self.assertEqual(len(queue.rows()), 1)
            self.assertEqual(queue.rows()[0]["attempts"], 1)
        finally:
            queue.close()

    def test_watch_cli_connects_poll_retrieval_reply_send_and_clean_stop(self):
        state = self.root / "watch-queue"
        provider = Mock(address=AGENT)
        provider.incoming.return_value = [("gmail:agent:watch-request", message().as_bytes(), "thread-1")]
        provider.send.return_value = {"id": "sent-1"}
        def retrieve(matter, category, output):
            shutil.copytree(self.source, output)
            return self.report
        args = ["senpilot.email", "--gmail", "--agent", AGENT, "--allow-sender", SENDER,
                "--extractor", "exact", "--state", str(state), "--watch", "--send"]
        with patch("sys.argv", args), patch("senpilot.gmail.Gmail", return_value=provider), \
                patch("senpilot.retrieval.retrieve", side_effect=retrieve), \
                patch("senpilot.email.time.sleep", side_effect=KeyboardInterrupt), \
                redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            self.assertEqual(email_main(), 130)
        provider.send.assert_called_once()
        queue = JobQueue(state)
        try:
            self.assertEqual(queue.rows()[0]["state"], "sent")
            self.assertFalse((state / "worker.lock").exists())
        finally:
            queue.close()


class GmailTests(unittest.TestCase):
    def service(self):
        service = Mock()
        service.users.return_value.getProfile.return_value.execute.return_value = {"emailAddress": AGENT}
        return service

    def test_send_uses_base64url_and_has_no_automatic_send_retries(self):
        service = self.service()
        provider = Gmail(Path("unused"), service=service)
        raw = message(sender=AGENT).as_bytes()
        service.users.return_value.messages.return_value.send.return_value.execute.return_value = {"id": "sent"}
        self.assertEqual(provider.send(raw, "thread-1"), {"id": "sent"})
        send = service.users.return_value.messages.return_value.send
        body = send.call_args.kwargs["body"]
        self.assertEqual(base64.urlsafe_b64decode(body["raw"]), raw)
        self.assertEqual(body["threadId"], "thread-1")
        send.return_value.execute.assert_called_once_with(num_retries=0)

    def test_poll_skips_known_ids_and_follows_pagination(self):
        service = self.service()
        messages = service.users.return_value.messages.return_value
        messages.list.return_value.execute.side_effect = [
            {"messages": [{"id": "known"}], "nextPageToken": "next"}, {"messages": [{"id": "new"}]}]
        raw = message().as_bytes()
        messages.get.return_value.execute.side_effect = [
            {"threadId": "thread-1", "sizeEstimate": len(raw)}, {"raw": base64.urlsafe_b64encode(raw).decode()}]
        provider = Gmail(Path("unused"), service=service)
        result = list(provider.incoming({f"gmail:{AGENT}:known"}, allowed_senders={SENDER}))
        self.assertEqual(result, [(f"gmail:{AGENT}:new", raw, "thread-1")])
        self.assertEqual(messages.list.call_args.kwargs["pageToken"], "next")
        self.assertIn("from:" + SENDER, messages.list.call_args.kwargs["q"])

    def test_token_with_only_read_access_is_rejected_before_refresh(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            path.write_text(json.dumps({"client_id": "test", "client_secret": "test", "refresh_token": "test",
                                        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"]}))
            with self.assertRaisesRegex(RuntimeError, "lacks required scopes"):
                load_credentials(path)

    def test_wrong_oauth_account_does_not_save_a_token(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "token.json"
            client = Path(directory) / "credentials.json"
            client.write_text("{}")
            service = self.service()
            service.users.return_value.getProfile.return_value.execute.return_value = {"emailAddress": "wrong@example.com"}
            args = ["senpilot.gmail", "--agent", AGENT, "--token", str(path), "--client", str(client)]
            with patch("sys.argv", args), patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file"), \
                    patch("senpilot.gmail.create_service", return_value=service), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit) as error:
                    gmail_auth_main()
            self.assertEqual(error.exception.code, 2)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
