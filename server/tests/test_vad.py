"""S-06 簡化版 VAD：RMS 與靜音切句。"""
import array

from services.vad import SilenceSegmenter, rms_pcm16


def _tone(ms, amp, rate=16000):
    n = int(rate * ms / 1000)
    a = array.array("h", [amp if i % 2 else -amp for i in range(n)])
    return a.tobytes()


def test_rms_zero_and_loud():
    assert rms_pcm16(b"") == 0.0
    assert rms_pcm16(_tone(100, 0)) == 0.0
    assert rms_pcm16(_tone(100, 5000)) > 4000


def test_segmenter_boundary_after_speech_then_silence():
    seg = SilenceSegmenter(min_speech_ms=400, min_silence_ms=600)
    # 0.5s 語音 → 尚未邊界
    assert seg.push(_tone(500, 6000)) is False
    # 0.3s 靜音 → 還不夠長
    assert seg.push(_tone(300, 0)) is False
    # 再 0.4s 靜音 → 累積 ≥600ms → 邊界
    assert seg.push(_tone(400, 0)) is True
    # 邊界後重置：純靜音不再觸發
    assert seg.push(_tone(700, 0)) is False


def test_segmenter_ignores_silence_only():
    seg = SilenceSegmenter()
    assert seg.push(_tone(2000, 0)) is False
    assert seg.has_pending_speech() is False
