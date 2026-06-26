"""SQLite 資料層（S-02）。

四表＋索引依設計決策手冊 §6.1（jobs／sessions／outputs／endpoints）。
時間欄位以 Unix epoch 秒（INTEGER）儲存，便於 expire_at 到期掃描。
"""
import os
import sqlite3
from contextlib import contextmanager

from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id        TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,           -- 原檔名僅顯示，永不進檔案路徑
    zone          TEXT NOT NULL,           -- uploads
    src_lang      TEXT NOT NULL,
    out_langs     TEXT NOT NULL,           -- JSON 陣列 (zh/en/th)
    status        TEXT NOT NULL,           -- queued/running/done/error
    created_at    INTEGER NOT NULL,
    expire_at     INTEGER NOT NULL,
    path          TEXT NOT NULL,
    duration      INTEGER                  -- 音檔時長(秒)；上傳時 ffprobe 取得(G4/SEC-2)
);
CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_expire_at  ON jobs(expire_at);

CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    name            TEXT,
    langs           TEXT NOT NULL,         -- JSON
    duration        INTEGER,
    status          TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    expire_at       INTEGER NOT NULL,
    audio_path      TEXT,
    transcript_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_expire_at ON sessions(expire_at);

CREATE TABLE IF NOT EXISTS outputs (
    id         TEXT PRIMARY KEY,
    ref_type   TEXT NOT NULL,              -- job/session
    ref_id     TEXT NOT NULL,
    kind       TEXT NOT NULL,              -- transcript/translation/summary/record
    lang       TEXT,
    fmt        TEXT,
    path       TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_outputs_ref_id ON outputs(ref_id);

CREATE TABLE IF NOT EXISTS endpoints (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    url      TEXT NOT NULL,
    model    TEXT NOT NULL,
    function TEXT NOT NULL,                 -- asr/batch_tr/live_tr/post
    active   INTEGER NOT NULL DEFAULT 1
);
"""


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    """交易範圍：正常結束自動 commit，例外則由呼叫端處理、最終必關閉連線。"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn) -> None:
    """冪等遷移：對既有 DB 補上後加的欄位（CREATE TABLE IF NOT EXISTS 不會改既有表）。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "duration" not in cols:  # G4：jobs 新增時長欄
        conn.execute("ALTER TABLE jobs ADD COLUMN duration INTEGER")


def init_db() -> None:
    """建表＋索引＋遷移（冪等）。應於 app 啟動時呼叫。"""
    with db() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
