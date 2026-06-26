"""S-02 到期清除（NFR-3／SEC-7）：到期連檔帶列刪除；未到期保留。"""
import os
import time

from models_db.db import db
from services.cleanup import sweep_expired
from storage.paths import build_path, ensure_zone, new_id


def _insert_job(job_id, path, expire_at):
    with db() as c:
        c.execute(
            "INSERT INTO jobs(job_id,original_name,zone,src_lang,out_langs,status,"
            "created_at,expire_at,path) VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, "原始.wav", "uploads", "zh", '["zh"]', "queued",
             int(time.time()) - 100, expire_at, path))


def _make_file():
    ensure_zone("uploads")
    fid = new_id()
    path = build_path("uploads", fid, ".wav")
    with open(path, "wb") as f:
        f.write(b"x")
    return fid, path


def test_sweep_removes_expired_file_and_row():
    fid, path = _make_file()
    now = int(time.time())
    _insert_job("j_" + fid, path, now - 1)        # 已到期

    removed = sweep_expired(now=now)

    assert removed["jobs"] == 1
    assert not os.path.isfile(path)
    with db() as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_sweep_keeps_unexpired():
    fid, path = _make_file()
    now = int(time.time())
    _insert_job("j_" + fid, path, now + 9999)     # 未到期

    removed = sweep_expired(now=now)

    assert removed["jobs"] == 0
    assert os.path.isfile(path)
