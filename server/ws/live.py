"""即時翻譯 WebSocket 端點 `/ws/live`（S-06 步驟 4/6/7，FR-1~FR-7、SEC-6、NG-6）。

上行：先一則 JSON 設定 `{type:"start", name?, src_lang, targets:[...]}`，
      接著二進位音框（16kHz 單聲道 PCM16），最後 `{type:"stop"}`。
下行：`{type:"ready"}` | `{type:"degraded", reasons}` | `{type:"partial", src, t}`
      | `{type:"final", src, translations:{th,en,...}, t}` | `{type:"saved", session_id}`
      | `{type:"error", message}`。`t` 一律伺服器時鐘（串流不回時間戳，NG-6）。

SEC-6：限同網段來源（私網/loopback）、限同時連線數、限單則訊息大小、閒置自動斷線。
G5：使用 ASR／live_tr 時呼叫 idle.tracker.record_use（補 wiring）。

延遲說明（§2.5-F）：realtime ASR 首 partial ≈5s、內部 5s 緩衝；VAD 落定的 final 句
可能略落後實際語音邊界，譯文以「幾句內出現」為準、非逐字即時。
"""
import asyncio
import ipaddress
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from services.asr import ASRError, ASRStream
from services.idle import tracker as idle_tracker
from services.live_translate import LiveTranslateError, translate_live_fanout
from services.resources import live_readiness
from services.sessions import save_live_session
from services.vad import SilenceSegmenter

router = APIRouter()

MAX_CONNECTIONS = 8          # 同時即時連線上限（共用卡＋RAM，SEC-6）
MAX_MSG_BYTES = 1_048_576    # 單則訊息上限 1MiB（0.5s 16k PCM16≈16KiB，留充裕餘裕）
IDLE_TIMEOUT_SEC = 120       # 無任何上行訊息逾時即斷（SEC-6）
VALID_LANGS = {"zh", "en", "th"}

_active = 0
_active_lock = asyncio.Lock()


def client_allowed(ws: WebSocket) -> bool:
    """SEC-6：只接受私網/loopback 來源（內網綁定，拒絕外部）。

    取對端 IP（容器內看到的是真實內網 IP 或 host-gateway）；非私網/loopback 一律拒。
    """
    client = ws.client
    if client is None:
        return False
    try:
        ip = ipaddress.ip_address(client.host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


async def _send_json(ws: WebSocket, obj: dict) -> None:
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.send_json(obj)


@router.websocket("/ws/live")
async def live_ws(ws: WebSocket) -> None:
    global _active
    # 來源守門須在 accept 後才能回訊；先 accept 再判、拒絕則關 1008（policy violation）。
    await ws.accept()
    if not client_allowed(ws):
        await _send_json(ws, {"type": "error", "message": "僅接受內網來源"})
        await ws.close(code=1008)
        return

    async with _active_lock:
        if _active >= MAX_CONNECTIONS:
            await _send_json(ws, {"type": "error", "message": "即時連線已達上限，請稍後再試"})
            await ws.close(code=1013)  # try again later
            return
        _active += 1
    try:
        await _serve(ws)
    finally:
        async with _active_lock:
            _active -= 1


async def _serve(ws: WebSocket) -> None:
    # 1) 等設定訊息（start）
    try:
        first = await asyncio.wait_for(ws.receive(), timeout=IDLE_TIMEOUT_SEC)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        return
    cfg = first.get("text")
    if not cfg:
        await _send_json(ws, {"type": "error", "message": "需先送 start 設定"})
        return
    import json
    try:
        cfg = json.loads(cfg)
    except ValueError:
        await _send_json(ws, {"type": "error", "message": "設定格式錯誤"})
        return
    src_lang = cfg.get("src_lang", "zh")
    targets = [l for l in (cfg.get("targets") or []) if l in VALID_LANGS]
    name = cfg.get("name")
    if src_lang not in VALID_LANGS or not targets:
        await _send_json(ws, {"type": "error", "message": "src_lang/targets 不合法"})
        return

    # 2) 連線前就緒守門（S-10）：不足則降級、不開 ASR
    rd = live_readiness()
    if not rd["ready"]:
        await _send_json(ws, {"type": "degraded", "reasons": rd["reasons"]})
        await ws.close(code=1011)
        return

    idle_tracker.record_use("asr")
    idle_tracker.record_use("live_tr")

    # 3) 開 ASR 串流；併發：events_task 收 ASR delta、主迴圈收上行音框
    try:
        asr = ASRStream()
    except ASRError as e:
        await _send_json(ws, {"type": "degraded", "reasons": ["asr_endpoint"], "message": str(e)})
        await ws.close(code=1011)
        return

    audio_buf = bytearray()           # 整場錄音（落地用）
    seg = SilenceSegmenter()
    state = {"latest": "", "boundary": 0, "start": time.time()}
    tr_acc: dict[str, list[str]] = {l: [] for l in targets if l != src_lang}

    async def finalize_segment() -> None:
        """把 boundary 之後的 ASR 文字落定為一句 final → 扇出翻譯 → 下行。"""
        sentence = state["latest"][state["boundary"]:].strip()
        if not sentence:
            return
        state["boundary"] = len(state["latest"])
        try:
            translations = await translate_live_fanout(sentence, targets, src_lang=src_lang)
        except LiveTranslateError:
            translations = {l: "" for l in targets}
        for l, txt in translations.items():
            if l != src_lang and l in tr_acc:
                tr_acc[l].append(txt)
        idle_tracker.record_use("live_tr")
        await _send_json(ws, {"type": "final", "src": sentence,
                              "translations": translations, "t": time.time()})

    async def pump_events() -> None:
        async for ev in asr.events():
            if ev["type"] == "partial":
                state["latest"] = ev["text"]
                await _send_json(ws, {"type": "partial",
                                      "src": ev["text"][state["boundary"]:], "t": time.time()})
            elif ev["type"] == "final":
                state["latest"] = ev["text"] or state["latest"]
            elif ev["type"] == "error":
                await _send_json(ws, {"type": "error", "message": ev["text"]})

    async with asr:
        events_task = asyncio.create_task(pump_events())
        await _send_json(ws, {"type": "ready"})
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=IDLE_TIMEOUT_SEC)
                except asyncio.TimeoutError:
                    await _send_json(ws, {"type": "error", "message": "閒置逾時，已斷線"})
                    break
                if msg["type"] == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is not None:
                    if len(data) > MAX_MSG_BYTES:
                        await _send_json(ws, {"type": "error", "message": "音框過大"})
                        continue
                    audio_buf += data
                    await asr.send_audio(bytes(data))
                    idle_tracker.record_use("asr")
                    if seg.push(bytes(data)):
                        await finalize_segment()
                    continue
                text = msg.get("text")
                if text:
                    try:
                        m = json.loads(text)
                    except ValueError:
                        continue
                    if m.get("type") == "stop":
                        break
        finally:
            # 收尾：commit final，給 ASR 一點時間吐完 done，落定殘句
            try:
                await asr.end()
            except Exception:
                pass
            await asyncio.sleep(0.2)
            await finalize_segment()
            events_task.cancel()

    # 4) 落地場次（★契約）＋回 saved
    duration = int(time.time() - state["start"])
    transcript = state["latest"].strip()
    translations = {l: "\n".join(parts).strip() for l, parts in tr_acc.items()}
    try:
        sid = save_live_session(
            name=name, src_lang=src_lang, targets=targets, duration_sec=duration,
            transcript=transcript, translations=translations, audio_pcm16=bytes(audio_buf),
        )
        await _send_json(ws, {"type": "saved", "session_id": sid})
    except Exception:
        await _send_json(ws, {"type": "error", "message": "場次儲存失敗"})
    if ws.application_state == WebSocketState.CONNECTED:
        await ws.close()
