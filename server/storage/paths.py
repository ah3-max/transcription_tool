"""兩區儲存與安全路徑組裝（S-02）。

檔名一律「伺服器產生 id ＋ 副檔名」；原檔名只存 DB 供顯示、永不進入路徑。
以 realpath 正規化並限制在各 zone 內，擋 `../`／絕對路徑穿越（D-07、SEC-3）。
"""
import os
import uuid

from config import settings

ZONES = {"uploads", "recordings", "outputs"}  # outputs：產出內容落地（逐字稿/翻譯/文件，S-08/S-09）
ALLOWED_EXTS = {".mp3", ".mp4", ".m4a", ".wav"}  # 僅音檔上傳白名單；outputs 落檔自組副檔名，不經 safe_ext


def new_id(prefix: str = "") -> str:
    """伺服器端唯一 id（十六進位、無分隔符），可選前綴如 j_/s_。"""
    token = uuid.uuid4().hex[:12]
    return f"{prefix}{token}" if prefix else token


def _zone_root(zone: str) -> str:
    if zone not in ZONES:
        raise ValueError(f"未知 zone：{zone}")
    return os.path.join(settings.data_dir, zone)


def safe_ext(original_name: str) -> str:
    """從原檔名取副檔名並做白名單檢查（不信任原檔名其餘部分）。"""
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"不支援的副檔名：{ext or '(無)'}")
    return ext


def ensure_zone(zone: str) -> str:
    root = _zone_root(zone)
    os.makedirs(root, exist_ok=True)
    return root


def build_path(zone: str, file_id: str, ext: str) -> str:
    """以 server 端 id 組路徑；正規化後必須落在該 zone 內，否則視為穿越攻擊。"""
    if not file_id.isalnum():
        raise ValueError("非法 file_id（僅允許英數）")
    if not ext.startswith(".") or "/" in ext or "\\" in ext:
        raise ValueError("非法副檔名")
    root = os.path.realpath(_zone_root(zone))
    candidate = os.path.realpath(os.path.join(root, f"{file_id}{ext}"))
    if root != candidate and os.path.commonpath([root, candidate]) != root:
        raise ValueError("偵測到路徑逃逸")
    return candidate
