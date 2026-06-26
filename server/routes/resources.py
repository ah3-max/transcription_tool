"""資源用量查詢（S-03，API-12）。供前端右上資源用量顯示（FR-24，預設隱藏）。"""
from fastapi import APIRouter

from responses import envelope
from services.resources import snapshot

router = APIRouter(prefix="/api/resources", tags=["resources"])


@router.get("")
async def get_resources():
    return envelope(await snapshot())
