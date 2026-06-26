"""stt-translate 應用進入點（S-01／S-02）。

一套 FastAPI 同時提供 UI（同源靜態服務 web/）＋ REST（/api）＋ 之後的 WS（/ws）。
回應一律採統一外型 {data, error?, message?}。內網綁定與埠由 Docker／環境變數決定。
啟動時建立 SQLite 四表並啟動到期清除背景任務（S-02）。
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from models_db.db import init_db
from services.cleanup import sweep_expired

CLEANUP_INTERVAL_SEC = 6 * 3600  # 每 6 小時掃一次到期資料（NFR-3／SEC-7）


def envelope(data=None, error: str | None = None, message: str | None = None) -> dict:
    """統一回應外型：{data, error?, message?}（清單另含 pagination，後續路由再加）。"""
    body: dict = {"data": data}
    if error is not None:
        body["error"] = error
    if message is not None:
        body["message"] = message
    return body


async def _cleanup_loop() -> None:
    while True:
        try:
            sweep_expired()
        except Exception:
            # 清除失敗不應拖垮服務；錯誤不外露細節（SEC-8）
            pass
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 建表＋索引（冪等）
    task = asyncio.create_task(_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(
    title="stt-translate",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict:
    """健康檢查：回 200。"""
    return envelope({"status": "ok", "app": "stt-translate", "version": app.version})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """未預期錯誤統一外型；SEC-8：不外露堆疊與路徑細節。"""
    return JSONResponse(
        status_code=500,
        content=envelope(error="internal", message="伺服器內部錯誤"),
    )


# 同源靜態服務 web/（html=True 讓根網址載入 index.html）。
# 必須掛在所有 /api、/ws 路由「之後」，否則會吃掉這些路徑。
app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
