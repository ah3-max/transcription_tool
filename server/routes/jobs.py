"""批次工作 jobs（S-04 API-01/03/05 骨架）。

本骨架：接多檔上傳→**先驗所有副檔名**→`can_reserve` 守門(503)→串流落檔(uploads，
累計上限 MAX_UPLOAD_GB 防亂塞)→**全部寫成功才一次入庫**(status=queued)。
任一步失敗都不留下孤兒 job/檔。真正前處理/VAD/切段/ASR 在 S-04 其餘；翻譯 S-05。
"""
import json
import os
import time

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from config import settings
from models_db.db import db
from responses import envelope
from services.resources import can_reserve
from storage.paths import build_path, ensure_zone, new_id, safe_ext

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

VALID_LANGS = {"zh", "en", "th"}
# 來源辨識語言（FR-13：國語／國語＋英文／純英文）。th 不是合法來源語。
# 前端「辨識語言」目前為 v6 雛形的 <button>（國語/國語＋英文/純英文，尚無 value、未配線）；
# 將來前端配線時務必送這組代碼，兩邊同步（改欄位→全鏈路同步）。
VALID_SRC = {"zh", "zh_en", "en"}
CHUNK = 1024 * 1024


def _err(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=envelope(error=error, message=message))


def _cleanup(paths) -> None:
    """best-effort 刪除暫存檔（用於失敗時不留孤兒）。"""
    for p in paths:
        try:
            if p and os.path.isfile(p):
                os.remove(p)
        except OSError:
            pass


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
    request: Request,
    files: list[UploadFile] = File(...),
    src_lang: str = Form("zh"),
    out_langs: str = Form("zh"),
):
    if src_lang not in VALID_SRC:
        return _err(400, "bad_request", "辨識語言不支援")
    langs = _parse_langs(out_langs)
    if not langs:
        return _err(400, "bad_request", "out_langs 至少一種（zh/en/th）")
    if not files:
        return _err(400, "bad_request", "未提供檔案")

    max_bytes = int(settings.max_upload_gb * 1024 ** 3)

    # 1) 先驗「所有」副檔名（零副作用）——避免壞檔混入時前面已落檔留下孤兒
    try:
        exts = [safe_ext(f.filename or "") for f in files]
    except ValueError:
        return _err(400, "bad_file", "僅支援 mp3/mp4/m4a/wav")

    # 2) Content-Length 若有先擋（快速拒絕），串流時再硬擋（防偽報/分塊）
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > max_bytes:
        return _err(413, "too_large", f"上傳超過上限 {settings.max_upload_gb}GB")

    # 3) 資源守門（SEC-5／NFR-2）：取不到回 503 並標記需降級
    ok, detail = can_reserve()
    if not ok:
        return JSONResponse(status_code=503, content=envelope(
            data={"degrade": True, "over": detail["over"]},
            error="resource", message="目前資源不足，請稍後再試"))

    # 4) 串流落檔（累計位元組硬擋）；任何失敗都清掉本請求已寫檔、不入庫
    ensure_zone("uploads")
    now = int(time.time())
    expire = now + settings.retention_days * 86400
    staged = []  # (job_id, original_name, path)
    total = 0
    try:
        for f, ext in zip(files, exts):
            fid = new_id()
            path = build_path("uploads", fid, ext)  # id 命名、原檔名不入路徑（D-07／SEC-3）
            with open(path, "wb") as out:
                while chunk := await f.read(CHUNK):
                    total += len(chunk)
                    if total > max_bytes:
                        out.close()
                        _cleanup([s[2] for s in staged] + [path])
                        return _err(413, "too_large", f"上傳超過上限 {settings.max_upload_gb}GB")
                    out.write(chunk)
            staged.append(("j_" + fid, f.filename, path))
    except Exception:
        _cleanup([s[2] for s in staged])
        raise

    # 5) 全部寫成功 → 單一交易入庫；失敗則清檔（不留孤兒）
    try:
        with db() as conn:
            for job_id, original_name, path in staged:
                conn.execute(
                    "INSERT INTO jobs(job_id,original_name,zone,src_lang,out_langs,status,"
                    "created_at,expire_at,path) VALUES(?,?,?,?,?,?,?,?,?)",
                    (job_id, original_name, "uploads", src_lang, json.dumps(langs),
                     "queued", now, expire, path))
    except Exception:
        _cleanup([s[2] for s in staged])
        raise

    created = [{"job_id": j, "original_name": n, "status": "queued"} for j, n, _ in staged]
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
