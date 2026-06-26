"""資源用量查詢（S-03，API-12）。供前端右上資源用量顯示（FR-24，預設隱藏）。"""
from fastapi import APIRouter

from responses import envelope
from services.resources import live_readiness, snapshot

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("")
async def get_resources():
    return envelope(await snapshot())


@router.get("/live-readiness")
async def get_live_readiness():
    """即時翻譯就緒檢查（S-10）：前端連線前查、不足則降級為手動錄音。"""
    return envelope(live_readiness())
