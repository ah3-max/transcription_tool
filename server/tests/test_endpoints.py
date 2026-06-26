"""S-03 端點 CRUD（API-11）與路由解析（FR-21）。"""


def test_endpoint_crud(client):
    r = client.post("/api/endpoints",
                    json={"name": "asr1", "url": "http://h", "model": "m", "function": "asr"})
    assert r.status_code == 201
    eid = r.json()["data"]["id"]

    r = client.get("/api/endpoints")
    assert any(e["id"] == eid for e in r.json()["data"])

    assert client.patch(f"/api/endpoints/{eid}?active=false").status_code == 200
    assert client.delete(f"/api/endpoints/{eid}").status_code == 200
    assert client.delete(f"/api/endpoints/{eid}").status_code == 404   # 已刪再刪


def test_endpoint_bad_function(client):
    r = client.post("/api/endpoints",
                    json={"name": "x", "url": "http://h", "model": "m", "function": "BOGUS"})
    assert r.status_code == 400
    assert r.json()["error"] == "http_error"


def test_resolve_endpoint(client):
    from services.routing import resolve_endpoint
    client.post("/api/endpoints",
                json={"name": "asr1", "url": "http://h", "model": "m", "function": "asr"})
    ep = resolve_endpoint("asr")
    assert ep and ep["function"] == "asr"
    assert resolve_endpoint("post") is None
