"""模型閒置追蹤與釋放（S-03 / G5 / NFR-1 / D-06）。

app 在純 CPU 容器內無法直接卸載 GPU；釋放 VRAM＝停掉 host 上的模型服務程序，
下次使用前再起。本模組只負責 app 端的「閒置判定」：
- record_use(function)：模型被使用時更新 last-use 時戳並標記為 loaded。
- idle_minutes(function)：回閒置分鐘數（從未用過回 None）。
- check_and_release(hook, threshold)：對閒置超閾且仍 loaded 者呼叫釋放 hook、標記 released。

wiring 分段（依賴後續 Story）：
- 現在：tracker 邏輯＋單元測試（注入時鐘與假 hook 即可驗）；預設釋放 hook 經
  host model_ctl 端點停服務（best-effort，host 未跑時自然失敗、下輪再試）。
- 待 S-06（vLLM 真的在 host 跑）：S-04/05/06 呼叫模型時呼叫 record_use；
  實機驗「閒置逾時 VRAM 釋放、下次使用自動重載」。

function 取值對齊 endpoints.function（asr/batch_tr/live_tr/post）。其中 GPU 模型
（asr→vLLM、live_tr→NLLB）才由我們 start/stop；batch_tr/post 走共用 LM Studio，
不在此停服務。
"""
import time
from threading import Lock

import httpx

from config import settings

# function → host systemd(user) unit；只有 GPU 模型可被我們 stop/start。
# 共用的 LM Studio（batch_tr/post）不在此控制。asr 的 vLLM unit 待 S-06/PoC 建立。
FUNCTION_UNIT = {
    "asr": "stt-vllm-asr",
    "live_tr": "stt-nllb",
}


class IdleTracker:
    """執行緒安全的模型使用時戳追蹤；clock 可注入以便單元測試。"""

    def __init__(self, clock=time.time):
        self._clock = clock
        self._last_use: dict[str, float] = {}
        self._loaded: set[str] = set()
        self._lock = Lock()

    def record_use(self, function: str) -> None:
        with self._lock:
            self._last_use[function] = self._clock()
            self._loaded.add(function)

    def idle_minutes(self, function: str) -> float | None:
        with self._lock:
            t = self._last_use.get(function)
        if t is None:
            return None
        return max(0.0, (self._clock() - t) / 60.0)

    def is_loaded(self, function: str) -> bool:
        with self._lock:
            return function in self._loaded

    def mark_released(self, function: str) -> None:
        with self._lock:
            self._loaded.discard(function)

    def due_for_release(self, threshold_min: float) -> list[str]:
        """回閒置 ≥ threshold_min 且仍 loaded 的 function 清單。"""
        due = []
        with self._lock:
            now = self._clock()
            for fn in list(self._loaded):
                t = self._last_use.get(fn)
                if t is not None and (now - t) / 60.0 >= threshold_min:
                    due.append(fn)
        return due

    def check_and_release(self, release_hook, threshold_min: float) -> list[str]:
        """對閒置超閾者呼叫 release_hook(function)；成功才標記 released。回實際釋放清單。

        hook 拋例外＝釋放失敗（如 host 未跑）：保留 loaded、下輪再試，不拖垮服務。
        """
        released = []
        for fn in self.due_for_release(threshold_min):
            try:
                release_hook(fn)
            except Exception:
                continue
            self.mark_released(fn)
            released.append(fn)
        return released


tracker = IdleTracker()


def release_via_model_ctl(function: str) -> None:
    """預設釋放 hook：經 host model_ctl 停掉該 function 對應的 unit。

    只控制本專案的 vLLM/NLLB unit（FUNCTION_UNIT）；未對應 unit 者略過。
    host model_ctl 未跑時拋例外，由 check_and_release 視為失敗、下輪再試。
    """
    unit = FUNCTION_UNIT.get(function)
    if unit is None:
        return
    with httpx.Client(timeout=5.0) as client:
        r = client.post(f"{settings.model_ctl_endpoint}/stop", json={"unit": unit})
        r.raise_for_status()
