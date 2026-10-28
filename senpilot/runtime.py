"""Configuration, local rotating logs, and a service heartbeat."""

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import sqlite3
import threading
import time

from .messages import mailbox


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class ServiceConfig:
    agent_address: str
    allowed_senders: tuple[str, ...]
    state: Path
    token: Path
    key_file: Path | None
    model: str = "deepseek-flash"
    send: bool = False
    poll_seconds: float = 60
    job_interval: float = 5
    restart_limit: int = 5
    restart_delay: float = 5

    def worker_args(self):
        args = ["--gmail", "--watch", "--recover-processing", "--agent", self.agent_address,
                "--state", str(self.state), "--token", str(self.token),
                "--poll-seconds", str(self.poll_seconds), "--interval", str(self.job_interval)]
        for sender in self.allowed_senders:
            args.extend(["--allow-sender", sender])
        return args + (["--send"] if self.send else [])


def load_config(path: Path) -> ServiceConfig:
    path = path.resolve(strict=True)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    allowed = {"agent_address", "allowed_senders", "state", "token", "deepseek_key_file", "model", "send",
               "poll_seconds", "job_interval", "restart_limit", "restart_delay"}
    if not isinstance(data, dict) or set(data) - allowed:
        raise ConfigurationError("Unknown service configuration fields")
    if not isinstance(data.get("allowed_senders"), list) or not data["allowed_senders"]:
        raise ConfigurationError("Configure at least one allowed sender")
    def location(name, optional=False):
        value = data.get(name)
        if value is None and optional:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Configure a path for {name}")
        return (path.parent / value).resolve()
    for name, minimum, maximum in (("poll_seconds", 30, 3600), ("job_interval", 5, 3600), ("restart_delay", 1, 300)):
        if name in data and (type(data[name]) not in {int, float} or not math.isfinite(data[name])
                             or not minimum <= data[name] <= maximum):
            raise ConfigurationError(f"Invalid {name}")
    if type(data.get("send", False)) is not bool:
        raise ConfigurationError("send must be true or false")
    if type(data.get("restart_limit", 5)) is not int or not 0 <= data.get("restart_limit", 5) <= 10:
        raise ConfigurationError("restart_limit must be between zero and ten")
    if not isinstance(data.get("model", "deepseek-flash"), str) or not data.get("model", "deepseek-flash").strip():
        raise ConfigurationError("Configure a DeepSeek model name")
    return ServiceConfig(mailbox(data.get("agent_address")), tuple(mailbox(value) for value in data["allowed_senders"]),
                         location("state"), location("token"), location("deepseek_key_file", optional=True),
                         **{name: data[name] for name in ("model", "send", "poll_seconds", "job_interval", "restart_limit", "restart_delay") if name in data})


def load_key(config: ServiceConfig) -> str:
    if config.key_file is not None and config.key_file.is_file():
        key = config.key_file.read_text(encoding="utf-8-sig").strip()
    else:
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key or "\n" in key or "\r" in key:
        raise ConfigurationError("Configure a DeepSeek key file or DEEPSEEK_API_KEY; values are never logged")
    return key


def preflight(config: ServiceConfig):
    key = load_key(config)
    try:
        token = json.loads(config.token.read_text(encoding="utf-8-sig"))
        required = {"https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"}
        if (not isinstance(token, dict) or not all(token.get(field) for field in ("refresh_token", "client_id", "client_secret"))
                or not required.issubset(token.get("scopes", []))):
            raise ConfigurationError("The Gmail token must support refresh, read access, and send access")
    except (OSError, ValueError, TypeError) as error:
        raise ConfigurationError("A valid local Gmail OAuth token with the required scopes is needed") from error
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            version = browser.version
        finally:
            browser.close()
    return key, version


def queue_snapshot(state: Path) -> dict:
    path = state / "queue.sqlite3"
    if not path.is_file():
        return {"counts": {}, "site_paused": False}
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            counts = dict(connection.execute("SELECT state,count(*) FROM jobs GROUP BY state").fetchall())
            paused = connection.execute("SELECT 1 FROM settings WHERE name='site_pause'").fetchone() is not None
            return {"counts": counts, "site_paused": paused}
        finally:
            connection.close()
    except sqlite3.Error:
        return {"counts": {}, "site_paused": False, "queue_error": True}


class RedactedJSON(logging.Formatter):
    def __init__(self, secret):
        super().__init__()
        self.secret = secret

    def format(self, record):
        message = record.getMessage().replace(self.secret, "[redacted]") if self.secret else record.getMessage()
        return json.dumps({"utc": datetime.now(timezone.utc).isoformat(), "level": record.levelname,
                           "event": message[:2000]}, ensure_ascii=True)


def service_logger(directory: Path, secret: str, console):
    directory.mkdir(parents=True, exist_ok=True)
    logger = logging.Logger("senpilot.service", level=logging.INFO)
    handler = RotatingFileHandler(directory / "worker.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    # Avoid logging's fallback writing back into redirected stderr on an I/O error.
    handler.handleError = lambda record: None
    logger.addHandler(handler)
    if console is not None:
        logger.addHandler(logging.StreamHandler(console))
    for item in logger.handlers:
        item.setFormatter(RedactedJSON(secret))
        item.handleError = lambda record: None
    return logger


class LogStream:
    encoding = "utf-8"

    def __init__(self, logger, level=logging.INFO):
        self.logger, self.level, self.buffer = logger, level, ""

    def write(self, text):
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                self.logger.log(self.level, line.rstrip("\r"))
        if len(self.buffer) > 2000:
            self.flush()
        return len(text)

    def flush(self):
        if self.buffer.strip():
            self.logger.log(self.level, self.buffer)
        self.buffer = ""

    def isatty(self):
        return False


class Heartbeat:
    def __init__(self, state: Path):
        self.state = state
        self.path = state / "service" / "heartbeat.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.values = {"phase": "starting", "restarts": 0, "pid": os.getpid()}
        self.lock = threading.Lock()

    def update(self, **fields):
        with self.lock:
            self.values.update(fields)

    def write(self):
        with self.lock:
            data = dict(self.values)
        data.update(queue_snapshot(self.state))
        counts = data["counts"]
        status = data["phase"]
        if data["site_paused"]:
            status = "paused"
        elif data.get("queue_error") or counts.get("send_uncertain") or counts.get("failed"):
            status = "attention"
        data.update(status=status, updated_utc=datetime.now(timezone.utc).isoformat(), updated_epoch=time.time())
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temporary.replace(self.path)
        return data


def check_health(path: Path, maximum_age=30) -> tuple[bool, dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        age = time.time() - data["updated_epoch"]
        healthy = data["status"] == "running" and 0 <= age <= maximum_age
        return healthy, data
    except (OSError, ValueError, KeyError, TypeError):
        return False, {"status": "unavailable"}
