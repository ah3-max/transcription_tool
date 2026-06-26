"""S-06 即時翻譯扇出（D-03）：語碼對照、來源直送、缺端點、單語失敗隔離。"""
import asyncio

import pytest

import services.live_translate as lt
from services.live_translate import APP_TO_FLORES, LiveTranslateError, translate_live_fanout


def test_flores_mapping():
    assert APP_TO_FLORES == {"zh": "zho_Hant", "en": "eng_Latn", "th": "tha_Thai"}


def test_fanout_no_endpoint_raises(monkeypatch):
    monkeypatch.setattr(lt, "resolve_endpoint", lambda fn: None)
    with pytest.raises(LiveTranslateError):
        asyncio.run(translate_live_fanout("你好", ["th"]))


def test_fanout_source_passthrough_and_independent(monkeypatch):
    monkeypatch.setattr(lt, "resolve_endpoint", lambda fn: {"url": "http://x", "model": "m"})

    async def fake_one(text, lang, *, endpoint, src_lang="zh", timeout=30.0):
        if lang == "en":
            raise lt.LiveTranslateError("boom")  # 單語失敗
        return f"{lang}:{text}"

    monkeypatch.setattr(lt, "translate_one", fake_one)
    out = asyncio.run(translate_live_fanout("早安", ["zh", "th", "en"], src_lang="zh"))
    assert out["zh"] == "早安"          # 來源語直送
    assert out["th"] == "th:早安"       # 正常翻譯
    assert out["en"] == ""             # 單語失敗不影響其他語


def test_fanout_empty_text(monkeypatch):
    monkeypatch.setattr(lt, "resolve_endpoint", lambda fn: {"url": "http://x", "model": "m"})
    out = asyncio.run(translate_live_fanout("   ", ["th", "en"]))
    assert out == {"th": "", "en": ""}
