"""S-06 /ws/live：來源守門（SEC-6）＋ start→ready→stop→saved 契約路徑。"""
import json
from types import SimpleNamespace

import ws.live as live
from models_db.db import db


def _fake_ws(host):
    return SimpleNamespace(client=SimpleNamespace(host=host) if host else None)


def test_client_allowed_private_and_loopback():
    assert live.client_allowed(_fake_ws("127.0.0.1")) is True
    assert live.client_allowed(_fake_ws("192.168.1.50")) is True
    assert live.client_allowed(_fake_ws("10.0.0.3")) is True


def test_client_allowed_rejects_public_and_bad():
    assert live.client_allowed(_fake_ws("8.8.8.8")) is False
    assert live.client_allowed(_fake_ws("not-an-ip")) is False
    assert live.client_allowed(_fake_ws(None)) is False


class _FakeASR:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def send_audio(self, b):
        pass

    async def end(self):
        pass

    async def events(self):
        return
        yield  # noqa: makes this an async generator


def test_ws_start_ready_stop_saved(client, monkeypatch):
    monkeypatch.setattr(live, "client_allowed", lambda ws: True)
    monkeypatch.setattr(live, "live_readiness", lambda: {"ready": True, "reasons": []})
    monkeypatch.setattr(live, "ASRStream", _FakeASR)

    with client.websocket_connect("/ws/live") as wsc:
        wsc.send_text(json.dumps({"type": "start", "src_lang": "zh", "targets": ["th", "en"]}))
        assert wsc.receive_json()["type"] == "ready"
        wsc.send_text(json.dumps({"type": "stop"}))
        msg = wsc.receive_json()
        assert msg["type"] == "saved"
        sid = msg["session_id"]

    with db() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
    assert s is not None and s["status"] == "done"


def test_ws_degraded_when_not_ready(client, monkeypatch):
    monkeypatch.setattr(live, "client_allowed", lambda ws: True)
    monkeypatch.setattr(live, "live_readiness",
                        lambda: {"ready": False, "reasons": ["live_tr_endpoint"]})

    with client.websocket_connect("/ws/live") as wsc:
        wsc.send_text(json.dumps({"type": "start", "src_lang": "zh", "targets": ["th"]}))
        msg = wsc.receive_json()
    assert msg["type"] == "degraded" and "live_tr_endpoint" in msg["reasons"]
