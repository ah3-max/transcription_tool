"""語句邊界偵測（S-06 步驟 3，§2.5-D）。

即時 ASR 內部以 5s 區塊出 partial，但固定 5s 會在段界切字（PoC：「長辈」→「长｜备」）。
上層需要「語句邊界」來決定何時把當前 partial 落定為 final 句、觸發翻譯扇出。

本模組是**簡化版**（純 Python，app CPU 容器無 numpy/torch）：以 PCM16 短時能量(RMS)
判靜音，speech 後出現足夠長的靜音即視為一個語句邊界。保留 `Segmenter` 介面，
未來可換 Silero VAD（同樣 push(pcm16)→是否邊界）而不動上層。

註：能量門檻為相對值、未做雜訊自適應；正式環境可接 DeepFilterNet3 後再判，
或換 Silero。這是「可用、保留掛點」的 v1（plan §2 步驟 3 明示可簡化）。
"""
import array
import math


def rms_pcm16(pcm16: bytes) -> float:
    """16-bit 小端單聲道 PCM 的均方根（0~32767 量級）。空輸入回 0。"""
    if not pcm16:
        return 0.0
    samples = array.array("h")
    # 落單的尾位元組（半個 sample）丟棄，避免 array 例外
    samples.frombytes(pcm16[: len(pcm16) - (len(pcm16) % 2)])
    if not samples:
        return 0.0
    acc = 0
    for s in samples:
        acc += s * s
    return math.sqrt(acc / len(samples))


class SilenceSegmenter:
    """靜音切句：speech 之後累積靜音 ≥ min_silence_ms → 回報一個語句邊界。

    push(pcm16) 回 True 代表「此塊結束時剛好落定一個語句」（上層據此把當前 partial 收為 final）。
    需先有 ≥ min_speech_ms 的語音才會觸發，避免純靜音/雜訊誤切。
    """

    def __init__(self, sample_rate: int = 16000, *, silence_rms: float = 300.0,
                 min_silence_ms: int = 600, min_speech_ms: int = 400):
        self.sample_rate = sample_rate
        self.silence_rms = silence_rms
        self.min_silence_ms = min_silence_ms
        self.min_speech_ms = min_speech_ms
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._in_speech = False

    def _chunk_ms(self, pcm16: bytes) -> float:
        n_samples = len(pcm16) // 2
        return 1000.0 * n_samples / self.sample_rate

    def push(self, pcm16: bytes) -> bool:
        """餵一塊 PCM16。回 True＝此塊結束時偵測到語句邊界（speech→足夠靜音）。"""
        dur = self._chunk_ms(pcm16)
        if dur <= 0:
            return False
        is_speech = rms_pcm16(pcm16) >= self.silence_rms
        if is_speech:
            self._speech_ms += dur
            self._silence_ms = 0.0
            self._in_speech = True
            return False
        # 靜音
        self._silence_ms += dur
        if self._in_speech and self._speech_ms >= self.min_speech_ms \
                and self._silence_ms >= self.min_silence_ms:
            # 落定一句，重置以偵測下一句
            self._speech_ms = 0.0
            self._silence_ms = 0.0
            self._in_speech = False
            return True
        return False

    def has_pending_speech(self) -> bool:
        """是否還有未落定的語音（停止錄音時用來決定要不要把殘餘 partial 收成 final）。"""
        return self._in_speech and self._speech_ms >= self.min_speech_ms
