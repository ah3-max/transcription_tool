"""S-08 API-10 /api/records 與 S-09 記錄匯出（mock post 端點）。"""
from services import postprocess
from tests.test_postprocess import _FakeProvider, _add_post_endpoint


def test_create_record_manual_upload(client, monkeypatch):
    _add_post_endpoint(client)
    monkeypatch.setattr(postprocess, "httpx", _FakeProvider())
    r = client.post(
        "/api/records",
        data={"template": "meeting"},
        files={"transcript_file": ("t.txt", "早上血壓偏高。".encode("utf-8"), "text/plain")},
    )
    assert r.status_code == 201
    body = r.json()["data"]
    assert body["output_id"].startswith("o_")
    assert body["template"] == "meeting"
    assert body["content"].startswith("# 會議記錄")

    assert body["sections"][0] == "出席"  # 回傳範本章節清單


def test_create_record_no_post_endpoint_409(client):
    r = client.post(
        "/api/records",
        data={"template": "meeting"},
        files={"transcript_file": ("t.txt", b"hi", "text/plain")},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "no_endpoint"


def test_create_record_requires_source(client, monkeypatch):
    _add_post_endpoint(client)
    monkeypatch.setattr(postprocess, "httpx", _FakeProvider())
    r = client.post("/api/records", data={"template": "meeting"})
    assert r.status_code == 400


def test_create_record_bad_template(client):
    r = client.post(
        "/api/records",
        data={"template": "nope"},
        files={"transcript_file": ("t.txt", b"hi", "text/plain")},
    )
    assert r.status_code == 400


def test_export_record_docx_filename_is_server_id(client, monkeypatch):
    _add_post_endpoint(client)
    monkeypatch.setattr(postprocess, "httpx", _FakeProvider())
    oid = client.post(
        "/api/records",
        data={"template": "meeting"},
        files={"transcript_file": ("t.txt", "內容".encode("utf-8"), "text/plain")},
    ).json()["data"]["output_id"]

    r = client.get(f"/api/records/{oid}/export?fmt=docx")
    assert r.status_code == 200
    assert "wordprocessingml" in r.headers["content-type"]
    assert f'filename="{oid}.docx"' in r.headers["content-disposition"]  # 檔名用 server id（SEC-3）


def test_export_record_pdf_rejected(client, monkeypatch):
    _add_post_endpoint(client)
    monkeypatch.setattr(postprocess, "httpx", _FakeProvider())
    oid = client.post(
        "/api/records",
        data={"template": "meeting"},
        files={"transcript_file": ("t.txt", "內容".encode("utf-8"), "text/plain")},
    ).json()["data"]["output_id"]
    r = client.get(f"/api/records/{oid}/export?fmt=pdf")
    assert r.status_code == 400
