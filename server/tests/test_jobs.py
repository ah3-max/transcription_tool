"""S-04 jobs：建立/清單/單筆/刪除、加固（先驗後寫、10GB 上限）、reserve 守門。"""
from config import settings


def _wav(name="a.wav", data=b"RIFFxxxxWAVE"):
    return (name, data, "audio/wav")


def test_create_list_get_delete(client):
    r = client.post("/api/jobs", files={"files": _wav()},
                    data={"src_lang": "zh", "out_langs": "zh,th"})
    assert r.status_code == 202
    jobs = r.json()["data"]["jobs"]
    assert len(jobs) == 1 and jobs[0]["status"] == "queued"
    jid = jobs[0]["job_id"]

    r = client.get("/api/jobs")
    assert r.json()["pagination"]["total"] == 1

    r = client.get(f"/api/jobs/{jid}")
    assert r.status_code == 200 and "progress" in r.json()["data"]

    assert client.get("/api/jobs/j_nope").status_code == 404
    assert client.delete(f"/api/jobs/{jid}").status_code == 200
    assert client.get("/api/jobs").json()["pagination"]["total"] == 0


def test_bad_extension_rejected(client):
    r = client.post("/api/jobs", files={"files": ("note.txt", b"abc", "text/plain")},
                    data={"out_langs": "zh"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_file"


def test_mixed_good_then_bad_no_orphan(client):
    """[好.wav, 壞.txt] → 400，且不可留下任何 job/檔（原子性回歸）。"""
    files = [("files", _wav("good.wav")), ("files", ("bad.txt", b"abc", "text/plain"))]
    r = client.post("/api/jobs", files=files, data={"out_langs": "zh"})
    assert r.status_code == 400
    assert client.get("/api/jobs").json()["pagination"]["total"] == 0


def test_oversize_rejected_no_row(client, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_gb", 0.0)   # cap=0 → 任何上傳皆超量
    r = client.post("/api/jobs", files={"files": _wav(data=b"abcdef")},
                    data={"out_langs": "zh"})
    assert r.status_code == 413
    assert r.json()["error"] == "too_large"
    assert client.get("/api/jobs").json()["pagination"]["total"] == 0


def test_resource_insufficient_503(client, monkeypatch):
    monkeypatch.setattr(settings, "res_cap", 0.0)         # cap=0 → can_reserve False
    r = client.post("/api/jobs", files={"files": _wav()}, data={"out_langs": "zh"})
    assert r.status_code == 503
    assert r.json()["error"] == "resource"
    assert r.json()["data"]["degrade"] is True


def test_out_langs_required(client):
    r = client.post("/api/jobs", files={"files": _wav()},
                    data={"out_langs": "klingon"})        # 無合法語言
    assert r.status_code == 400
    assert r.json()["error"] == "bad_request"
