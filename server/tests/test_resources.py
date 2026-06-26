"""S-10 即時就緒檢查（NFR-2/SEC-5）：/api/resources/live-readiness 足/不足兩路。"""
import services.resources as res


def _add_endpoint(client, function):
    client.post("/api/endpoints",
                json={"name": function, "url": "http://h", "model": "m", "function": function})


def test_readiness_not_ready_when_no_endpoints(client):
    """無 ASR／live_tr 端點 → not ready，reasons 含兩端點代碼。"""
    r = client.get("/api/resources/live-readiness")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["ready"] is False
    assert "asr_endpoint" in d["reasons"]
    assert "live_tr_endpoint" in d["reasons"]


def test_readiness_ready_when_endpoints_active(client, monkeypatch):
    """端點齊備且資源足 → ready、reasons 空。"""
    _add_endpoint(client, "asr")
    _add_endpoint(client, "live_tr")
    # 資源充足（避免測試機真實用量影響）
    monkeypatch.setattr(res, "can_reserve", lambda: (True, {"over": []}))
    d = client.get("/api/resources/live-readiness").json()["data"]
    assert d["ready"] is True
    assert d["reasons"] == []


def test_readiness_not_ready_when_resource_over_cap(client, monkeypatch):
    """端點齊備但 RAM 超上限 → not ready，reasons 含 ram。"""
    _add_endpoint(client, "asr")
    _add_endpoint(client, "live_tr")
    monkeypatch.setattr(res, "can_reserve", lambda: (False, {"over": ["ram"]}))
    d = client.get("/api/resources/live-readiness").json()["data"]
    assert d["ready"] is False
    assert "ram" in d["reasons"]
