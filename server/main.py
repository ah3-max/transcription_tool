"""stt-translate 應用進入點（S-01）。

一套 FastAPI 同時提供 UI（同源靜態服務 web/）＋ REST（/api）＋ 之後的 WS（/ws）。
回應一律採統一外型 {data, error?, message?}。內網綁定與埠由 Docker／環境變數決定。
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings

app = FastAPI(
    title="stt-translate",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


def envelope(data=None, error: str | None = None, message: str | None = None) -> dict:
    """統一回應外型：{data, error?, message?}（清單另含 pagination，後續路由再加）。"""
    body: dict = {"data": data}
    if error is not None:
        body["error"] = error
    if message is not None:
        body["message"] = message
    return body


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
