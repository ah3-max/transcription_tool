"""文件生成與記錄匯出（S-08 API-10、S-09 記錄匯出）。

POST /api/records：來源（既有逐字稿產出 or 手動上傳）＋範本 → Gemma 生成 →
落檔 outputs 區、寫 outputs(kind=record) → 回 {output_id, template, content}。
GET /api/records/{output_id}/export?fmt=docx|md|txt：讀該 record 內容 → render → 串流下載。

記錄不一定屬某 job，故匯出獨立於 job-scoped 的 API-04。
"""
import time

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from models_db.db import db
from responses import envelope
from services import export as export_svc
from services.postprocess import (
    PostprocessError,
    extract_text,
    generate_record,
    parse_custom_template,
    template_sections,
)
from storage.paths import build_path, ensure_zone, new_id

router = APIRouter(prefix="/api/records", tags=["records"])

VALID_TEMPLATES = {"meeting", "handover", "custom"}
TRANSCRIPT_EXTS = {".txt", ".md", ".docx"}
TEMPLATE_EXTS = {".md", ".docx"}


def _err(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=envelope(error=error, message=message))


def _ext_of(name: str) -> str:
    import os
    return os.path.splitext(name or "")[1].lower()


def _write_output_file(content: str) -> tuple[str, str]:
    """把產出內容寫進 outputs 區（id 命名，原檔名不入路徑）。回 (file_id, path)。"""
    ensure_zone("outputs")
    fid = new_id()  # 純英數，供 build_path
    path = build_path("outputs", fid, ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return fid, path


@router.post("", status_code=201)
async def create_record(
    template: str = Form(...),
    ref_output_id: str | None = Form(None),
    transcript_file: UploadFile | None = File(None),
    custom_template_file: UploadFile | None = File(None),
):
    if template not in VALID_TEMPLATES:
        return _err(400, "bad_request", f"template 須為 {sorted(VALID_TEMPLATES)}")

    # 1) 取得逐字稿純文字：既有產出 or 手動上傳（二擇一）
    transcript_text = ""
    ref_type, ref_id = "manual", "manual"
    if ref_output_id:
        with db() as conn:
            row = conn.execute(
                "SELECT * FROM outputs WHERE id=? AND kind='transcript'", (ref_output_id,)
            ).fetchone()
        if row is None:
            return _err(404, "not_found", "來源逐字稿產出不存在")
        try:
            with open(row["path"], "r", encoding="utf-8") as f:
                transcript_text = f.read()
        except OSError:
            return _err(404, "not_found", "來源逐字稿內容已不存在")
        ref_type, ref_id = row["ref_type"], row["ref_id"]
    elif transcript_file is not None:
        ext = _ext_of(transcript_file.filename)
        if ext not in TRANSCRIPT_EXTS:
            return _err(400, "bad_file", "逐字稿僅支援 txt/md/docx")
        data = await transcript_file.read()
        try:
            transcript_text = extract_text(data, ext)
        except PostprocessError as e:
            return _err(400, "bad_file", str(e))
    else:
        return _err(400, "bad_request", "需提供 ref_output_id 或 transcript_file 其一")

    # 2) 自訂範本解析（template=custom 必填）
    custom_structure = None
    if template == "custom":
        if custom_template_file is None:
            return _err(400, "bad_request", "template=custom 需上傳 custom_template_file")
        ext = _ext_of(custom_template_file.filename)
        if ext not in TEMPLATE_EXTS:
            return _err(400, "bad_file", "自訂範本僅支援 md/docx")
        try:
            custom_structure = parse_custom_template(await custom_template_file.read(), ext)
        except PostprocessError as e:
            return _err(400, "bad_file", str(e))

    # 3) 生成（無 post 端點 → 409）
    try:
        content = await generate_record(transcript_text, template, custom_structure=custom_structure)
    except PostprocessError as e:
        return _err(409, "no_endpoint", str(e))

    # 4) 落檔 + 入庫 outputs(kind=record)
    fid, path = _write_output_file(content)
    oid = "o_" + fid
    now = int(time.time())
    with db() as conn:
        conn.execute(
            "INSERT INTO outputs(id,ref_type,ref_id,kind,lang,fmt,path,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (oid, ref_type, ref_id, "record", "zh", "md", path, now),
        )

    return envelope({
        "output_id": oid,
        "template": template,
        "sections": template_sections(template, custom_structure),
        "content": content,
    })


@router.get("/{output_id}/export")
def export_record(output_id: str, fmt: str = "docx"):
    with db() as conn:
        row = conn.execute(
            "SELECT * FROM outputs WHERE id=? AND kind='record'", (output_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="記錄不存在")
    try:
        with open(row["path"], "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        raise HTTPException(status_code=404, detail="記錄內容已不存在")

    try:
        data, media_type, ext = export_svc.render(content, fmt)
    except ValueError as e:
        return _err(400, "bad_request", str(e))

    filename = f"{output_id}.{ext}"  # 檔名用 server id，不含原檔名（SEC-3）
    return StreamingResponse(
        iter([data]),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
