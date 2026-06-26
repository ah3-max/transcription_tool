"""S-06 ASR 串流客戶端：前綴剝除與 WS URL 轉換（純函式）。"""
from services.asr import realtime_ws_url, strip_asr_prefix


def test_strip_prefix_basic():
    assert strip_asr_prefix("language zh<asr_text>今天天氣很好") == "今天天氣很好"


def test_strip_prefix_with_space_and_tags():
    assert strip_asr_prefix("language en  hello world") == "hello world"
    assert strip_asr_prefix("<asr_text>純內容</asr_text>") == "純內容"


def test_strip_prefix_noop_when_no_prefix():
    assert strip_asr_prefix("沒有前綴的逐字稿") == "沒有前綴的逐字稿"
    assert strip_asr_prefix("") == ""


def test_ws_url_conversion():
    assert realtime_ws_url("http://host.docker.internal:8000/v1") == \
        "ws://host.docker.internal:8000/v1/realtime"
    assert realtime_ws_url("https://h:8000/v1/") == "wss://h:8000/v1/realtime"
