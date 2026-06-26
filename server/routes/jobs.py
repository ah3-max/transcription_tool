"""批次工作 jobs（S-04 API-01/03/05 骨架）。

本骨架：接多檔上傳→副檔名白名單→`can_reserve` 守門(503)→以伺服器 id 落檔(uploads)→
建 job 列(status=queued)。真正的前處理/VAD/切段/ASR 在 S-04 其餘部分；翻譯在 S-05。
"""
import json
import os
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config import settings
from models_db.db import db
from responses import envelope
from services.resources import can_reserve
from storage.paths import build_path, ensure_zone, new_id, safe_ext

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

VALID_LANGS = {"zh", "en", "th"}


def _parse_langs(raw: str) -> list:
    raw = (raw or "").strip()
    if raw.startswith("["):
        try:
            vals = json.loads(raw)
        except json.JSONDecodeError:
            vals = []
    else:
        vals = [x.strip() for x in raw.split(",")]
    seen, out = set(), []
    for v in vals:  # 保序去重、僅留合法語言
        if v in VALID_LANGS and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _job_dict(r) -> dict:
    return {
        "job_id": r["job_id"], "original_name": r["original_name"], "zone": r["zone"],
        "src_lang": r["src_lang"], "out_langs": json.loads(r["out_langs"]),
        "status": r["status"], "created_at": r["created_at"], "expire_at": r["expire_at"],
    }


@router.post("", status_code=202)
async def create_jobs(
    files: list[UploadFile] = File(...),
    src_lang: str = Form("zh"),
    out_langs: str = Form("zh"),
):
    langs = _parse_langs(out_langs)
    if not langs:
        return JSONResponse(status_code=400, content=envelope(
            error="bad_request", message="out_langs 至少一種（zh/en/th）"))
    if not files:
        return JSONResponse(status_code=400, content=envelope(
            error="bad_request", message="未提供檔案"))

    # 資源守門（SEC-5／NFR-2）：取不到回 503 並標記需降級
    ok, detail = can_reserve()
    if not ok:
        return JSONResponse(status_code=503, content=envelope(
            data={"degrade": True, "over": detail["over"]},
            error="resource", message="目前資源不足，請稍後再試"))

    ensure_zone("uploads")
    now = int(time.time())
    expire = now + settings.retention_days * 86400
    created = []
    for f in files:
        try:
            ext = safe_ext(f.filename or "")
        except ValueError:
            return JSONResponse(status_code=400, content=envelope(
                error="bad_file", message="僅支援 mp3/mp4/m4a/wav"))
        fid = new_id()
        job_id = "j_" + fid
        path = build_path("uploads", fid, ext)  # id 命名、原檔名不入路徑（D-07/SEC-3）
        with open(path, "wb") as out:
            while chunk := await f.read(1024 * 1024):
                out.write(chunk)
        with db() as conn:
            conn.execute(
                "INSERT INTO jobs(job_id,original_name,zone,src_lang,out_langs,status,"
                "created_at,expire_at,path) VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, f.filename, "uploads", src_lang, json.dumps(langs),
                 "queued", now, expire, path))
        created.append({"job_id": job_id, "original_name": f.filename, "status": "queued"})

    return envelope({"jobs": created})


@router.get("")
def list_jobs(limit: int = 50, offset: int = 0):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    with db() as conn:
        total = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        rows = [_job_dict(r) for r in conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))]
    return {"data": rows, "pagination": {"total": total, "limit": limit, "offset": offset}}


@router.get("/{job_id}")
def get_job(job_id: str):
    with db() as conn:
        r = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if r is None:
        raise HTTPException(status_code=404, detail="工作不存在")
    d = _job_dict(r)
    d["progress"] = {"overall_done": 0, "overall_total": 1, "current_pct": 0}  # 真值待 S-04 處理
    return envelope(d)


@router.delete("/{job_id}")
def delete_job(job_id: str):
    with db() as conn:
        r = conn.execute("SELECT path FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if r is None:
            raise HTTPException(status_code=404, detail="工作不存在")
        if r["path"] and os.path.isfile(r["path"]):
            try:
                os.remove(r["path"])
            except OSError:
                pass
        conn.execute("DELETE FROM outputs WHERE ref_id=?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
    return envelope({"deleted": job_id})
