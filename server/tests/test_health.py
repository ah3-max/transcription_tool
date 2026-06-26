def test_health_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "ok"
    assert data["app"] == "stt-translate"
