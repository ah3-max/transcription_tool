"""stt-translate 應用進入點（S-01／S-02／S-03）。

一套 FastAPI 同時提供 UI（同源靜態服務 web/）＋ REST（/api）＋ 之後的 WS（/ws）。
回應一律採統一外型 {data, error?, message?}（見 responses.py）。
啟動時建立 SQLite 四表並啟動到期清除背景任務（S-02）；掛載端點 CRUD 與資源查詢路由（S-03）。
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from responses import envelope
from models_db.db import init_db
from services.cleanup import sweep_expired
from routes import endpoints as endpoints_route
from routes import resources as resources_route
from routes import jobs as jobs_route

CLEANUP_INTERVAL_SEC = 6 * 3600  # 每 6 小時掃一次到期資料（NFR-3／SEC-7）


async def _cleanup_loop() -> None:
    while True:
        try:
            sweep_expired()
        except Exception:
            pass  # 清除失敗不拖垮服務；不外露細節（SEC-8）
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
    return envelope({"status": "ok", "app": "stt-translate", "version": app.version})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(error="http_error", message=str(exc.detail)),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content=envelope(error="bad_request", message="輸入驗證失敗"),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # SEC-8：不外露堆疊與路徑細節
    return JSONResponse(
        status_code=500,
        content=envelope(error="internal", message="伺服器內部錯誤"),
    )


# REST 路由（須在靜態掛載之前）
app.include_router(endpoints_route.router)
app.include_router(resources_route.router)
app.include_router(jobs_route.router)

# 同源靜態服務 web/（html=True 讓根網址載入 index.html）。掛在所有 /api、/ws 之後。
app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
