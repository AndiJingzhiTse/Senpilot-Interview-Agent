from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest
from unittest.mock import Mock, patch

from senpilot.queue import JobQueue, WorkerLockError, worker_lock
from senpilot.runtime import ConfigurationError, Heartbeat, LogStream, check_health, load_config, load_key, preflight, service_logger
from senpilot.service import supervise
from senpilot.service import main as service_main


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.config_path = self.root / "agent.json"
        self.secret = "deployment-test-secret-not-a-real-key"
        (self.root / "key").write_text(self.secret, encoding="utf-8")
        token = {"refresh_token": "test", "client_id": "test", "client_secret": "test",
                 "scopes": ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"]}
        (self.root / "token.json").write_text(json.dumps(token))
        self.data = {"agent_address": "agent@example.com", "allowed_senders": ["user@example.com"],
                     "state": "state", "token": "token.json", "deepseek_key_file": "key", "send": True}
        self.save()
        self.config = load_config(self.config_path)

    def save(self):
        self.config_path.write_text(json.dumps(self.data))

    def test_configuration_resolves_paths_and_does_not_put_secrets_in_arguments(self):
        self.assertEqual(self.config.state, self.root / "state")
        self.assertEqual(self.config.token, self.root / "token.json")
        args = self.config.worker_args()
        self.assertIn("--recover-processing", args)
        self.assertIn("--watch", args)
        self.assertIn("--send", args)
        self.assertNotIn(self.secret, " ".join(args))
        self.assertNotIn(str(self.config.key_file), " ".join(args))

    def test_invalid_configuration_is_rejected(self):
        for field, value in (("send", "false"), ("poll_seconds", 1), ("job_interval", float("nan")),
                             ("restart_limit", -1), ("allowed_senders", []), ("accept_any_sender", "true"),
                             ("accept_any_sender", True), ("command", "arbitrary executable")):
            with self.subTest(field=field):
                original = dict(self.data)
                self.data[field] = value
                self.save()
                with self.assertRaises(ConfigurationError):
                    load_config(self.config_path)
                self.data = original

    def test_any_sender_configuration_reaches_the_worker_explicitly(self):
        self.data.update(accept_any_sender=True, allowed_senders=[])
        self.save()
        config = load_config(self.config_path)
        self.assertTrue(config.accept_any_sender)
        self.assertEqual(config.allowed_senders, ())
        self.assertIn("--accept-any-sender", config.worker_args())
        self.assertNotIn("--allow-sender", config.worker_args())

    def test_missing_key_or_invalid_scopes_fail_before_browser_launch(self):
        with patch("playwright.sync_api.sync_playwright") as browser:
            self.config.key_file.unlink()
            with patch.dict(os.environ, {}, clear=True), self.assertRaises(ConfigurationError):
                preflight(self.config)
            self.config.key_file.write_text(self.secret)
            self.config.token.write_text("{}")
            with self.assertRaises(ConfigurationError):
                preflight(self.config)
            browser.assert_not_called()

    def test_preflight_reports_busy_without_contacting_providers(self):
        with worker_lock(self.config.state), patch("senpilot.service.preflight") as check, patch("sys.stderr", StringIO()):
            self.assertEqual(service_main(["--config", str(self.config_path), "--check"]), 73)
        check.assert_not_called()

    def test_key_file_accepts_powershell_utf8_bom(self):
        self.config.key_file.write_bytes(b"\xef\xbb\xbf" + self.secret.encode() + b"\r\n")
        self.assertEqual(load_key(self.config), self.secret)

    def test_key_storage_uses_the_local_environment_and_refuses_overwrites(self):
        self.config.key_file.unlink()
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": self.secret}), redirect_stdout(StringIO()) as output:
            self.assertEqual(service_main(["--config", str(self.config_path), "--store-key"]), 0)
        self.assertNotIn(self.secret, output.getvalue())
        self.assertEqual(self.config.key_file.read_text(), self.secret)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "different-test-value"}), patch("sys.stderr", StringIO()):
            self.assertEqual(service_main(["--config", str(self.config_path), "--store-key"]), 78)
        self.assertEqual(self.config.key_file.read_text(), self.secret)

    def test_heartbeat_distinguishes_running_paused_attention_and_stale(self):
        heartbeat = Heartbeat(self.config.state)
        heartbeat.update(phase="running")
        heartbeat.write()
        self.assertTrue(check_health(heartbeat.path)[0])
        queue = JobQueue(self.config.state)
        try:
            queue.pause_site({"http_status": 429})
            self.assertEqual(heartbeat.write()["status"], "paused")
            self.assertFalse(check_health(heartbeat.path)[0])
            queue.resume_site()
            queue.enqueue("failed", b"request")
            job = queue.claim()
            queue.finish(job["id"], "failed", {})
            self.assertEqual(heartbeat.write()["status"], "attention")
        finally:
            queue.close()
        data = json.loads(heartbeat.path.read_text())
        data.update(status="running", updated_epoch=time.time() - 120)
        heartbeat.path.write_text(json.dumps(data))
        self.assertFalse(check_health(heartbeat.path)[0])

    def test_rotating_logs_redact_the_configured_key(self):
        directory = self.root / "logs"
        logger = service_logger(directory, self.secret, None)
        handler = logger.handlers[0]
        handler.maxBytes = 300
        stream = LogStream(logger)
        for _ in range(20):
            stream.write("provider: " + self.secret + "\n")
        for item in logger.handlers:
            item.close()
        paths = list(directory.glob("worker.log*"))
        self.assertLessEqual(len(paths), 4)
        self.assertGreater(len(paths), 1)
        for path in paths:
            self.assertNotIn(self.secret, path.read_text())
            self.assertIn("[redacted]", path.read_text())

    def test_supervisor_restarts_a_failed_worker_and_restores_environment(self):
        stop = threading.Event()
        calls = []
        def worker(args):
            calls.append(args)
            print("test output: " + self.secret)
            if len(calls) == 1:
                raise OSError("Simulated failure")
            stop.set()
            return 130
        config = replace(self.config, restart_delay=0.01)
        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "previous-test-value"}), redirect_stdout(StringIO()):
            self.assertEqual(supervise(config, self.secret, stop, worker=worker), 0)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "previous-test-value")
        self.assertEqual(len(calls), 2)
        log = (config.state / "service/worker.log").read_text()
        self.assertIn("restart:1", log)
        self.assertNotIn(self.secret, log)
        self.assertEqual(json.loads((config.state / "service/heartbeat.json").read_text())["phase"], "stopped")

    def test_restart_budget_stops_provider_retries(self):
        class StopAtAttention(threading.Event):
            def wait(self, timeout=None):
                if timeout is None:
                    self.set()
                return self.is_set()
        worker = Mock(return_value=2)
        with redirect_stdout(StringIO()):
            supervise(replace(self.config, restart_limit=1), self.secret, StopAtAttention(), worker=worker)
        self.assertEqual(worker.call_count, 2)
        self.assertIn("restart_limit_reached", (self.config.state / "service/worker.log").read_text())

    def test_paused_queue_does_not_restart_provider_access(self):
        queue = JobQueue(self.config.state)
        queue.pause_site({"http_status": 403})
        queue.close()
        class StopAfterPause(threading.Event):
            def wait(self, timeout=None):
                self.set()
                return True
        worker = Mock()
        with redirect_stdout(StringIO()):
            supervise(self.config, self.secret, StopAfterPause(), worker=worker)
        worker.assert_not_called()

    def test_real_preflight_and_windowless_python_launch_only_blank_chrome(self):
        executables = [Path(sys.executable)]
        windowless = Path(sys.executable).with_name("pythonw.exe")
        if os.name == "nt" and windowless.is_file():
            executables.append(windowless)
        for executable in executables:
            with self.subTest(executable=executable.name):
                result = subprocess.run([str(executable), "-m", "senpilot.service", "--config", str(self.config_path), "--check"],
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.config.state / "queue.sqlite3").exists())


class RecoveryTests(unittest.TestCase):
    def test_kernel_lock_is_released_after_forced_process_death(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            program = """from pathlib import Path
import sys,time
from senpilot.queue import worker_lock
root=Path(sys.argv[1])
with worker_lock(root):
    (root/'ready').write_text('locked')
    time.sleep(60)
"""
            # Windows venv executables are launchers. Kill the actual interpreter,
            # rather than its launcher, so this exercises a real worker crash.
            interpreter = getattr(sys, "_base_executable", sys.executable)
            child = subprocess.Popen([interpreter, "-c", program, str(root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 10
                while not (root / "ready").exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue((root / "ready").exists())
                with self.assertRaises(WorkerLockError):
                    with worker_lock(root):
                        self.fail("Another process acquired the live lock")
                child.terminate()
                child.wait(timeout=5)
                with worker_lock(root):
                    self.assertTrue((root / "worker.lock").exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
                child.communicate()

    def test_legacy_lock_is_never_deleted_or_adopted(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "worker.lock"
            for original in (b"One worker may retrieve and send at a time.\n", b""):
                with self.subTest(contents=original):
                    path.write_bytes(original)
                    with self.assertRaisesRegex(WorkerLockError, "legacy"):
                        with worker_lock(root):
                            self.fail("Adopted the old worker's lock")
                    self.assertEqual(path.read_bytes(), original)

    def test_recovery_requeues_only_processing_and_never_repeats_sends(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            queue = JobQueue(root)
            try:
                keys = {}
                for source, state, attempts in (("recover", "processing", 1), ("exhausted", "processing", 3),
                                                ("uncertain", "sending", 1), ("confirmed", "sent", 1),
                                                ("ready", "prepared", 1)):
                    queue.enqueue(source, b"request", "thread")
                    job = queue.claim()
                    queue.finish(job["id"], state, {"thread_id": "thread"})
                    queue.db.execute("UPDATE jobs SET attempts=? WHERE id=?", (attempts, job["id"]))
                    queue.db.commit()
                    keys[source] = job["id"]
                with worker_lock(root):
                    self.assertEqual(queue.recover_interrupted(), {"requeued": 1, "exhausted": 1, "uncertain": 1})
                by_source = {row["source_id"]: row for row in queue.rows()}
                self.assertEqual(by_source["recover"]["state"], "pending")
                self.assertEqual(by_source["exhausted"]["state"], "failed")
                self.assertEqual(by_source["uncertain"]["state"], "send_uncertain")
                self.assertEqual(by_source["confirmed"]["state"], "sent")
                self.assertEqual(by_source["ready"]["state"], "prepared")
                next_job = queue.claim()
                self.assertEqual(next_job["id"], keys["recover"])
                self.assertEqual(next_job["attempts"], 2)
            finally:
                queue.close()


if __name__ == "__main__":
    unittest.main()
