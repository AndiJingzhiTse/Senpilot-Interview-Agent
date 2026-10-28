"""A durable local queue with exclusive workers and explicit delivery states."""

from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import sqlite3


@contextmanager
def worker_lock(root: Path):
    root.mkdir(parents=True, exist_ok=True)
    path = root / "worker.lock"
    try:
        stream = path.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise RuntimeError("A worker lock exists; check for another worker before removing a stale lock") from error
    try:
        with stream:
            stream.write("One worker may retrieve and send at a time.\n")
            yield
    finally:
        path.unlink()


class JobQueue:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(root / "queue.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, source_id TEXT NOT NULL UNIQUE, raw BLOB NOT NULL,
            state TEXT NOT NULL, info TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0)""")
        self.db.execute("CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self.db.commit()

    def close(self):
        self.db.close()

    def enqueue(self, source_id: str, raw: bytes, thread_id: str | None = None) -> bool:
        key = sha256(source_id.encode()).hexdigest()
        with self.db:
            cursor = self.db.execute("INSERT OR IGNORE INTO jobs(id, source_id, raw, state, info) VALUES(?,?,?,?,?)",
                                     (key, source_id, raw, "pending", json.dumps({"thread_id": thread_id})))
        return cursor.rowcount == 1

    def claim(self) -> dict | None:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT * FROM jobs WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE jobs SET state='processing', attempts=attempts+1 WHERE id=?", (row["id"],))
        return {**dict(row), "info": json.loads(row["info"]), "attempts": row["attempts"] + 1}

    def finish(self, key: str, state: str, info: dict):
        with self.db:
            self.db.execute("UPDATE jobs SET state=?, info=? WHERE id=?", (state, json.dumps(info), key))

    def rows(self, state: str | None = None) -> list[dict]:
        rows = self.db.execute("SELECT id,source_id,state,info,attempts FROM jobs ORDER BY rowid" if state is None
                               else "SELECT id,source_id,state,info,attempts FROM jobs WHERE state=? ORDER BY rowid",
                               () if state is None else (state,)).fetchall()
        return [{**dict(row), "info": json.loads(row["info"])} for row in rows]

    def retry(self, key: str):
        with self.db:
            row = self.db.execute("SELECT state,info FROM jobs WHERE id=?", (key,)).fetchone()
            if row is None or row["state"] not in {"failed", "processing"}:
                raise ValueError("Only failed or interrupted processing jobs can be retried; sends require reconciliation")
            previous = json.loads(row["info"])
            info = {name: previous[name] for name in ("thread_id", "saved_report") if name in previous}
            self.db.execute("UPDATE jobs SET state='pending', info=? WHERE id=?", (json.dumps(info), key))

    def pause_site(self, reason: dict):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO settings(name,value) VALUES('site_pause',?)", (json.dumps(reason),))

    def site_paused(self) -> bool:
        return self.db.execute("SELECT 1 FROM settings WHERE name='site_pause'").fetchone() is not None

    def resume_site(self):
        with self.db:
            self.db.execute("DELETE FROM settings WHERE name='site_pause'")
