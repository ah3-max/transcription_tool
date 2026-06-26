"""資源動態管理（S-03）。

app 在純 CPU 容器內：RAM 用 psutil、儲存用 shutil 量；VRAM 經 host `gpu_stat` 端點查（D-17）。
reserve 不超過 RES_CAP；取不到資源回 503 並標記需降級（NFR-1/2、SEC-5）。
GPU reserve 本身交 vLLM 啟動參數 gpu_memory_utilization、閒置 unload 屬 host（整合待 S-06）。
"""
import shutil

import httpx
import psutil

from config import settings
from services.routing import resolve_endpoint


def ram_usage() -> dict:
    vm = psutil.virtual_memory()
    used = vm.total - vm.available
    return {
        "total": vm.total,
        "used": used,
        "available": vm.available,
        "used_pct": round(used / vm.total * 100, 1) if vm.total else None,
    }


def storage_usage(path: str | None = None) -> dict:
    du = shutil.disk_usage(path or settings.data_dir)
    return {
        "total": du.total,
        "used": du.used,
        "free": du.free,
        "used_pct": round(du.used / du.total * 100, 1) if du.total else None,
    }


async def vram_usage() -> dict | None:
    """經 host gpu_stat 取 VRAM；取不到回 None（FR-24 顯示 N/A、不擋服務）。"""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{settings.gpu_stat_endpoint}/gpu")
            r.raise_for_status()
            return r.json().get("data")
    except Exception:
        return None


async def snapshot() -> dict:
    """供 /api/resources（FR-24 右上資源用量）。"""
    return {
        "ram": ram_usage(),
        "storage": storage_usage(),
        "gpu": await vram_usage(),
        "cap_pct": round(settings.res_cap * 100, 1),
    }


def live_readiness() -> dict:
    """即時翻譯能否起（S-10，NFR-2/SEC-5）。供 WS 連線前守門與前端降級判斷。

    回 {"ready": bool, "reasons": [code...], "detail": {...}}。
    reasons 代碼（前端對應三語訊息）：
      - "ram" / "storage"：app 可量資源已達 RES_CAP（can_reserve 不過）；
      - "asr_endpoint"：未設定 active 的 ASR 端點（即時辨識必須 vLLM）；
      - "live_tr_endpoint"：未設定 active 的即時翻譯端點。
    S-06 WS 連線前呼叫此函式；連線中資源掉線則下行 {"type":"degraded","reason":...}。
    """
    ok_res, detail = can_reserve()
    reasons = list(detail["over"]) if not ok_res else []
    if resolve_endpoint("asr") is None:
        reasons.append("asr_endpoint")
    if resolve_endpoint("live_tr") is None:
        reasons.append("live_tr_endpoint")
    return {"ready": not reasons, "reasons": reasons, "detail": detail}


def can_reserve() -> tuple[bool, dict]:
    """app 可量的資源（RAM／儲存）是否仍在 RES_CAP 內。回 (ok, detail)。

    供 S-04 起工作前守門：not ok → 回 503 並標記需降級。
    GPU 由 vLLM gpu_memory_utilization 自限，不在此判斷。
    """
    cap = settings.res_cap * 100
    ram = ram_usage()
    sto = storage_usage()
    over = [k for k, v in (("ram", ram["used_pct"]), ("storage", sto["used_pct"]))
            if v is not None and v >= cap]
    return (not over, {"over": over, "cap_pct": cap, "ram": ram, "storage": sto})
