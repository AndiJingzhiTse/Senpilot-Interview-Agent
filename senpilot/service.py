"""Supervise the Gmail worker without a terminal; keep secrets out of logs."""

import argparse
from contextlib import redirect_stderr, redirect_stdout
from getpass import getpass
import logging
import os
from pathlib import Path
import signal
import sys
import threading
import time

from .email import main as email_main
from .queue import WorkerLockError, worker_lock
from .runtime import ConfigurationError, Heartbeat, LogStream, check_health, load_config, preflight, queue_snapshot, service_logger


def supervise(config, key, stop, *, worker=email_main):
    heartbeat = Heartbeat(config.state)
    logger = service_logger(heartbeat.path.parent, key, sys.stdout)
    monitor_stop = threading.Event()
    def monitor():
        while not monitor_stop.is_set():
            try:
                heartbeat.write()
            except OSError:
                logger.error("heartbeat_write_failed")
            monitor_stop.wait(5)
    thread = threading.Thread(target=monitor, name="senpilot-heartbeat", daemon=True)
    thread.start()
    previous_key, previous_model = os.environ.get("DEEPSEEK_API_KEY"), os.environ.get("DEEPSEEK_MODEL")
    os.environ["DEEPSEEK_API_KEY"], os.environ["DEEPSEEK_MODEL"] = key, config.model
    stdout, stderr = LogStream(logger), LogStream(logger, logging.ERROR)
    restarts = 0
    try:
        logger.info("service_start")
        with redirect_stdout(stdout), redirect_stderr(stderr):
            while not stop.is_set():
                snapshot = queue_snapshot(config.state)
                if snapshot["site_paused"] or snapshot["counts"].get("send_uncertain"):
                    heartbeat.update(phase="paused" if snapshot["site_paused"] else "attention")
                    stop.wait(5)
                    continue
                heartbeat.update(phase="running", restarts=restarts)
                started = time.monotonic()
                try:
                    code = worker(config.worker_args())
                except KeyboardInterrupt:
                    stop.set()
                    break
                except Exception as error:
                    logger.error("worker_exception:%s", type(error).__name__)
                    code = 2
                if stop.is_set() or code == 130:
                    break
                if time.monotonic() - started >= 300:
                    restarts = 0
                snapshot = queue_snapshot(config.state)
                if snapshot["site_paused"] or snapshot["counts"].get("send_uncertain"):
                    continue
                if restarts >= config.restart_limit:
                    heartbeat.update(phase="attention", reason="restart_limit")
                    logger.error("restart_limit_reached; operator restart required")
                    stop.wait()
                    break
                restarts += 1
                delay = min(config.restart_delay * 2 ** (restarts - 1), 300)
                heartbeat.update(phase="retrying", restarts=restarts)
                logger.warning("worker_exit:%s; restart:%s; delay_seconds:%s", code, restarts, delay)
                stop.wait(delay)
        return 0
    finally:
        stdout.flush()
        stderr.flush()
        monitor_stop.set()
        thread.join(timeout=10)
        heartbeat.update(phase="stopped")
        try:
            heartbeat.write()
        except OSError:
            logger.error("final_heartbeat_failed")
        logger.info("service_stop")
        for name, previous in (("DEEPSEEK_API_KEY", previous_key), ("DEEPSEEK_MODEL", previous_model)):
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous
        for handler in logger.handlers:
            handler.close()


def wait_for_configuration(config, stop, message):
    heartbeat = Heartbeat(config.state)
    logger = service_logger(heartbeat.path.parent, "", sys.stdout)
    logger.error("preflight_failed:%s; operator restart required", message)
    heartbeat.update(phase="attention", reason="preflight_failed")
    try:
        while not stop.is_set():
            heartbeat.write()
            stop.wait(5)
    finally:
        heartbeat.update(phase="stopped")
        heartbeat.write()
        for handler in logger.handlers:
            handler.close()
    return 0


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Run Senpilot as a supervised background worker")
    parser.add_argument("--config", required=True, type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="Check local configuration and launch blank Chrome; no provider calls")
    action.add_argument("--health", action="store_true", help="Check the local heartbeat without contacting providers")
    action.add_argument("--store-key", action="store_true", help="Save an environment key or secure prompt to the configured key file")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        if args.store_key:
            if config.key_file is None:
                raise ConfigurationError("Configure deepseek_key_file before storing a key")
            if config.key_file.exists():
                raise ConfigurationError("The key file already exists; it was not overwritten")
            key = (os.environ.get("DEEPSEEK_API_KEY") or getpass("DeepSeek API key: ")).strip()
            if not key or "\n" in key or "\r" in key:
                raise ConfigurationError("A nonempty key on a single line is required")
            config.key_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(config.key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(key)
            print(f"Saved local key file: {config.key_file}")
            return 0
        if args.health:
            healthy, data = check_health(config.state / "service/heartbeat.json")
            print(f"Service health: {data['status']}")
            return 0 if healthy else 1
        if args.check:
            with worker_lock(config.state, "service.lock"), worker_lock(config.state):
                key, version = preflight(config)
            print(f"Local preflight passed for {config.agent_address}; Chrome {version}. Provider access was not tested.")
            return 0
    except Exception as error:
        message = str(error) if isinstance(error, (ConfigurationError, WorkerLockError)) else type(error).__name__
        print(f"Service configuration failed: {message}", file=sys.stderr)
        return 73 if isinstance(error, WorkerLockError) else 78
    stop = threading.Event()
    def request_stop(signum, frame):
        if not stop.is_set():
            stop.set()
            raise KeyboardInterrupt
    signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        signals.append(signal.SIGBREAK)
    previous = {item: signal.signal(item, request_stop) for item in signals}
    try:
        with worker_lock(config.state, "service.lock"):
            # Do not start alongside an existing terminal worker, including the legacy version.
            with worker_lock(config.state):
                pass
            try:
                key, version = preflight(config)
            except Exception as error:
                message = str(error) if isinstance(error, ConfigurationError) else type(error).__name__
                return wait_for_configuration(config, stop, message)
            return supervise(config, key, stop)
    except KeyboardInterrupt:
        return 0
    except WorkerLockError:
        print("Service could not acquire its worker lock; stop the existing worker before activation.", file=sys.stderr)
        return 73
    finally:
        for item, handler in previous.items():
            signal.signal(item, handler)


if __name__ == "__main__":
    raise SystemExit(main())
