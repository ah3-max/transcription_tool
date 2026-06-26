"""即時翻譯扇出（S-06 步驟 2，FR-4~FR-5，D-03）。

對一句中文 final 句子，向 live_tr 端點（NLLB，非 OpenAI 相容、FLORES-200 語碼）
**一對多扇出**——每個目標語言獨立從中文源翻一次，互不串接（D-03，避免累積誤差）。

端點由 `resolve_endpoint("live_tr")` 取得；NLLB 服務介面見 `host-helpers/nllb_server.py`：
  POST {url}/translate {text, src_lang, tgt_lang(FLORES)} → {data:{translation}}
url 無 `/v1`（非 OpenAI 相容）。語碼對照 app(zh/en/th) ↔ FLORES-200。
"""
import asyncio

import httpx

from services.routing import resolve_endpoint

# app 介面語碼 → FLORES-200。中文採繁體（本專案 zh＝繁中）。
APP_TO_FLORES = {"zh": "zho_Hant", "en": "eng_Latn", "th": "tha_Thai"}


class LiveTranslateError(Exception):
    """即時翻譯不可進行（未設定 live_tr 端點）。"""


async def translate_one(text: str, target_lang: str, *, endpoint: dict,
                        src_lang: str = "zh", timeout: float = 30.0) -> str:
    """打一次 NLLB /translate，回單一目標語言譯文。未知語碼以原碼直送（讓 server 擋）。"""
    url = endpoint["url"].rstrip("/") + "/translate"
    payload = {
        "text": text,
        "src_lang": APP_TO_FLORES.get(src_lang, src_lang),
        "tgt_lang": APP_TO_FLORES.get(target_lang, target_lang),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload)
        r.raise_for_status()
        body = r.json()
    if body.get("error"):
        raise LiveTranslateError(body["error"])
    return (body.get("data") or {}).get("translation", "")


async def translate_live_fanout(text: str, targets: list[str], *, src_lang: str = "zh") -> dict:
    """一對多扇出：每個目標語言**並行獨立**翻譯（D-03）。回 {lang: text}。

    - 來源語言（src_lang）在 targets 內 → 直接帶回原文，不自我翻譯。
    - 無 active live_tr 端點 → 拋 LiveTranslateError（呼叫端轉降級，勿 500）。
    - 個別語言失敗不拖垮其他語言：該語回空字串（上層可標示）。
    """
    text = (text or "").strip()
    if not text:
        return {lang: "" for lang in targets}
    endpoint = resolve_endpoint("live_tr")
    if endpoint is None:
        raise LiveTranslateError("尚未設定可用的即時翻譯端點（function=live_tr）")

    async def _one(lang: str) -> tuple[str, str]:
        if lang == src_lang:
            return lang, text
        try:
            return lang, await translate_one(text, lang, endpoint=endpoint, src_lang=src_lang)
        except (httpx.HTTPError, LiveTranslateError):
            return lang, ""  # 單語失敗不影響其他語（扇出彼此獨立）

    results = await asyncio.gather(*(_one(lang) for lang in targets))
    return dict(results)
