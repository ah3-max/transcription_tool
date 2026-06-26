"""即時 ASR 串流客戶端（S-06 步驟 1，FR-1~FR-3）。

連 host vLLM 的 `/v1/realtime`（WebSocket），餵 16kHz 單聲道 PCM16 音框、收增量逐字稿。
端點由 `resolve_endpoint("asr")` 取得（S-03）。協定取自 vLLM
`entrypoints/speech_to_text/realtime/{connection,protocol}.py`（PoC 已實證，見
`docs/dev_log/vllm-asr-poc.md` ⑪）：

  client→server：session.update(model) → input_audio_buffer.commit(final=False) 啟動
                 → input_audio_buffer.append(base64 PCM16) → commit(final=True) 收尾
  server→client：session.created / transcription.delta(delta) / transcription.done(text) / error

雷（§2.5）：
- **漏 commit(final=False) 會收不到任何 delta**——它才「啟動」generation（PoC 首測就栽這）。
- 串流每段輸出帶 `language {lang}<asr_text>` 前綴，**批次 server 端會剝、串流不剝**→ 本模組自剝。
- 不回時間戳（NG-6）：時間由上層以伺服器時鐘標記。
"""
import base64
import json
import re

import websockets

from services.routing import resolve_endpoint

# 串流 delta 前綴：`language zh<asr_text>實際逐字…`。批次端點 server 端已剝、串流要自剝。
_PREFIX_RE = re.compile(r"^\s*language\s+[A-Za-z][A-Za-z\-_]*\s*", re.IGNORECASE)


class ASRError(Exception):
    """ASR 串流不可進行（未設定端點 / 連線失敗 / server 回 error）。"""


def strip_asr_prefix(text: str) -> str:
    """剝除 realtime/SSE delta 的 `language {lang}<asr_text>` 前綴與 asr_text 框標。

    對「累積全文」呼叫（前綴只在開頭出現一次）。空字串原樣回。
    """
    if not text:
        return text
    t = _PREFIX_RE.sub("", text, count=1)
    t = t.replace("<asr_text>", "").replace("</asr_text>", "")
    return t.lstrip()


def realtime_ws_url(endpoint_url: str) -> str:
    """ASR 端點（http(s)://host/v1）→ realtime WebSocket（ws(s)://host/v1/realtime）。"""
    u = endpoint_url.rstrip("/")
    if u.startswith("https://"):
        u = "wss://" + u[len("https://"):]
    elif u.startswith("http://"):
        u = "ws://" + u[len("http://"):]
    return u + "/realtime"


class ASRStream:
    """一條 realtime ASR 連線的生命週期；支援併發 send_audio 與 events 迭代。

    用法：
        async with ASRStream() as asr:
            # 一個 task 餵音框：await asr.send_audio(pcm16_bytes)
            # 同時迭代事件：
            async for ev in asr.events():
                ev = {"type": "partial"|"final"|"error", "text": str, "code": str|None}
            await asr.end()   # 餵完音框後收尾，讓 server 送出 final
    """

    def __init__(self, endpoint: dict | None = None, *, connect_timeout: float = 10.0):
        if endpoint is None:
            endpoint = resolve_endpoint("asr")
        if endpoint is None:
            raise ASRError("尚未設定可用的 ASR 端點（function=asr）")
        self._endpoint = endpoint
        self._url = realtime_ws_url(endpoint["url"])
        self._model = endpoint["model"]
        self._connect_timeout = connect_timeout
        self._ws = None
        self._accum = ""  # 累積原始全文（含前綴），剝除後對外

    async def __aenter__(self) -> "ASRStream":
        try:
            self._ws = await websockets.connect(self._url, open_timeout=self._connect_timeout)
            # server 連上即送 session.created；收掉它（不強制）。
            # 接著設定 model → commit(final=False) 啟動 generation（缺它收不到 delta）。
            await self._send({"type": "session.update", "model": self._model})
            await self._send({"type": "input_audio_buffer.commit", "final": False})
        except (OSError, websockets.WebSocketException) as e:
            raise ASRError(f"無法連上 ASR realtime 端點：{e}") from e
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def _send(self, obj: dict) -> None:
        await self._ws.send(json.dumps(obj))

    async def send_audio(self, pcm16: bytes) -> None:
        """送一塊 16kHz 單聲道 PCM16 音框（建議 ~0.5s/塊，PoC 餵法）。"""
        if not pcm16:
            return
        b64 = base64.b64encode(pcm16).decode("ascii")
        await self._send({"type": "input_audio_buffer.append", "audio": b64})

    async def end(self) -> None:
        """音框餵完：commit(final=True) 讓 server 收尾並送 transcription.done。"""
        await self._send({"type": "input_audio_buffer.commit", "final": True})

    async def events(self):
        """迭代 server 事件，yield 正規化後的 {type, text, code}。

        - transcription.delta → {"type":"partial","text": 剝前綴後的累積全文}
        - transcription.done  → {"type":"final","text": 剝前綴後的最終全文}
        - error               → {"type":"error","text": 訊息,"code": 代碼}
        連線正常關閉即結束迭代。
        """
        try:
            async for raw in self._ws:
                try:
                    ev = json.loads(raw)
                except (ValueError, TypeError):
                    continue
                etype = ev.get("type")
                if etype == "transcription.delta":
                    self._accum += ev.get("delta", "")
                    yield {"type": "partial", "text": strip_asr_prefix(self._accum), "code": None}
                elif etype == "transcription.done":
                    text = ev.get("text", self._accum)
                    yield {"type": "final", "text": strip_asr_prefix(text), "code": None}
                elif etype == "error":
                    yield {"type": "error", "text": ev.get("error", "ASR error"),
                           "code": ev.get("code")}
                # session.created 等其他事件略過
        except websockets.WebSocketException as e:
            yield {"type": "error", "text": f"ASR 連線中斷：{e}", "code": "ws_closed"}
