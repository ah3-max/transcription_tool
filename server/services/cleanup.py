"""到期清除（S-02）：依 expire_at 掃 jobs/sessions，連同其產出檔與索引一併刪除。

對應 NFR-3（7 天到期自動清）、SEC-7（落地清除：刪檔＋刪索引）。
"""
import os
import time

from models_db.db import db


def _safe_unlink(path) -> None:
    if path and os.path.isfile(path):
        try:
            os.remove(path)
        except OSError:
            pass


def sweep_expired(now=None) -> dict:
    """刪除到期的 jobs/sessions：先刪其落地檔與關聯 outputs（檔＋列），再刪本體列。

    回傳刪除統計，供日誌/監看。
    """
    now = int(time.time()) if now is None else int(now)
    removed = {"jobs": 0, "sessions": 0, "output_files": 0}
    with db() as conn:
        expired_jobs = [r["job_id"] for r in conn.execute(
            "SELECT job_id FROM jobs WHERE expire_at <= ?", (now,))]
        expired_sessions = [r["session_id"] for r in conn.execute(
            "SELECT session_id FROM sessions WHERE expire_at <= ?", (now,))]

        # 1) 刪到期本體的落地檔
        for r in conn.execute("SELECT path FROM jobs WHERE expire_at <= ?", (now,)):
            _safe_unlink(r["path"])
        for r in conn.execute(
                "SELECT audio_path, transcript_path FROM sessions WHERE expire_at <= ?", (now,)):
            _safe_unlink(r["audio_path"])
            _safe_unlink(r["transcript_path"])

        # 2) 刪這些 ref 的 outputs（檔＋列）
        for ref_id in expired_jobs + expired_sessions:
            for r in conn.execute("SELECT path FROM outputs WHERE ref_id = ?", (ref_id,)):
                _safe_unlink(r["path"])
                removed["output_files"] += 1
            conn.execute("DELETE FROM outputs WHERE ref_id = ?", (ref_id,))

        # 3) 刪本體列
        removed["jobs"] = conn.execute(
            "DELETE FROM jobs WHERE expire_at <= ?", (now,)).rowcount
        removed["sessions"] = conn.execute(
            "DELETE FROM sessions WHERE expire_at <= ?", (now,)).rowcount
    return removed
