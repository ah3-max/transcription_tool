"""G5：模型閒置追蹤與釋放（注入時鐘＋假 hook，純單元測試，不依賴 host）。"""
from services.idle import IdleTracker


class FakeClock:
    """可手動推進的時鐘（分鐘為單位推進）。"""
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance_min(self, m):
        self.t += m * 60


def test_record_use_and_idle_minutes():
    clk = FakeClock()
    tr = IdleTracker(clock=clk)
    assert tr.idle_minutes("asr") is None      # 從未用過
    tr.record_use("asr")
    assert tr.is_loaded("asr") is True
    assert tr.idle_minutes("asr") == 0.0
    clk.advance_min(7)
    assert tr.idle_minutes("asr") == 7.0


def test_check_and_release_triggers_after_threshold():
    clk = FakeClock()
    tr = IdleTracker(clock=clk)
    calls = []
    tr.record_use("asr")
    tr.record_use("live_tr")

    clk.advance_min(5)                          # 未達 10 分 → 不釋放
    assert tr.check_and_release(calls.append, threshold_min=10) == []
    assert calls == []

    clk.advance_min(6)                          # 共 11 分 → 兩者皆釋放
    released = tr.check_and_release(calls.append, threshold_min=10)
    assert set(released) == {"asr", "live_tr"}
    assert set(calls) == {"asr", "live_tr"}
    assert tr.is_loaded("asr") is False
    assert tr.is_loaded("live_tr") is False


def test_failed_hook_keeps_loaded_for_retry():
    clk = FakeClock()
    tr = IdleTracker(clock=clk)
    tr.record_use("asr")
    clk.advance_min(20)

    def boom(_fn):
        raise RuntimeError("host model_ctl 未跑")

    assert tr.check_and_release(boom, threshold_min=10) == []  # 失敗不算釋放
    assert tr.is_loaded("asr") is True                          # 仍 loaded、下輪再試


def test_reload_after_release():
    clk = FakeClock()
    tr = IdleTracker(clock=clk)
    tr.record_use("asr")
    clk.advance_min(15)
    tr.check_and_release(lambda _fn: None, threshold_min=10)
    assert tr.is_loaded("asr") is False
    tr.record_use("asr")                        # 下次使用 → 重新標記 loaded、閒置歸零
    assert tr.is_loaded("asr") is True
    assert tr.idle_minutes("asr") == 0.0
