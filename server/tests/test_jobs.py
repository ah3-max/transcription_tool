"""S-04 jobs：建立/清單/單筆/刪除、加固（先驗後寫、10GB 上限）、reserve 守門。
S-09：API-04 匯出（依種子 transcript 產出）。
G4：上傳深度驗證（ffprobe 解碼／時長上限）。"""
import io
import struct
import time
import wave

from config import settings
from models_db.db import db
from storage.paths import build_path, ensure_zone, new_id


def _real_wav_bytes(seconds=1.0, rate=8000):
    """產生真正可被 ffprobe 解碼的 WAV（PCM16 mono 靜音），供 G4 深度驗證測試。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack("<%dh" % int(rate * seconds), *([0] * int(rate * seconds))))
    return buf.getvalue()


def _wav(name="a.wav", data=None):
    return (name, data if data is not None else _real_wav_bytes(), "audio/wav")


def _seed_transcript(job_id, content="# 逐字稿\n\n## 內文\n那個血壓有點高。\n", lang="zh"):
    """為某 job 種一筆 transcript 產出（內容落 outputs 區），供匯出測試。"""
    ensure_zone("outputs")
    fid = new_id()
    path = build_path("outputs", fid, ".md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    with db() as conn:
        conn.execute(
            "INSERT INTO outputs(id,ref_type,ref_id,kind,lang,fmt,path,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("o_" + fid, "job", job_id, "transcript", lang, "md", path, int(time.time())),
        )
    return "o_" + fid


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


def test_bad_src_lang_rejected(client):
    """G1/FR-13：非法 src_lang → 400 bad_request；合法 zh_en/en → 202。"""
    r = client.post("/api/jobs", files={"files": _wav()},
                    data={"src_lang": "foo", "out_langs": "zh"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_request"

    for src in ("zh_en", "en"):
        r = client.post("/api/jobs", files={"files": _wav()},
                        data={"src_lang": src, "out_langs": "zh"})
        assert r.status_code == 202, src


def _make_job(client):
    return client.post("/api/jobs", files={"files": _wav()},
                       data={"src_lang": "zh", "out_langs": "zh"}).json()["data"]["jobs"][0]["job_id"]


def test_export_job_transcript_md(client):
    jid = _make_job(client)
    _seed_transcript(jid)
    r = client.get(f"/api/jobs/{jid}/export?fmt=md&lang=zh&kind=transcript")
    assert r.status_code == 200
    assert "那個血壓有點高" in r.content.decode("utf-8")
    assert r.headers["content-disposition"].endswith(f'{jid}_transcript_zh.md"')


def test_export_job_pdf_rejected(client):
    jid = _make_job(client)
    _seed_transcript(jid)
    assert client.get(f"/api/jobs/{jid}/export?fmt=pdf").status_code == 400


def test_export_job_no_output_404(client):
    jid = _make_job(client)
    assert client.get(f"/api/jobs/{jid}/export?fmt=md").status_code == 404


def test_get_job_includes_outputs(client):
    jid = _make_job(client)
    oid = _seed_transcript(jid)
    outs = client.get(f"/api/jobs/{jid}").json()["data"]["outputs"]
    assert any(o["id"] == oid and o["kind"] == "transcript" for o in outs)


def test_bad_audio_rejected_no_orphan(client):
    """G4/SEC-2：副檔名合法但內容非音檔（無法解碼）→ 400 bad_file，且不留孤兒。"""
    r = client.post("/api/jobs", files={"files": _wav("fake.wav", b"this is plain text, not audio")},
                    data={"src_lang": "zh", "out_langs": "zh"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_file"
    assert client.get("/api/jobs").json()["pagination"]["total"] == 0


def test_too_long_rejected_no_orphan(client, monkeypatch):
    """G4：超過時長上限 → 413 too_long，且不留孤兒。"""
    monkeypatch.setattr(settings, "max_file_min", 0)   # 上限 0 分 → 任何正時長皆超時
    r = client.post("/api/jobs", files={"files": _wav()},
                    data={"src_lang": "zh", "out_langs": "zh"})
    assert r.status_code == 413
    assert r.json()["error"] == "too_long"
    assert client.get("/api/jobs").json()["pagination"]["total"] == 0


def test_valid_audio_has_duration(client):
    """G4：合法音檔 → 202，回傳並落庫時長(秒>0)，get_job 也能取得。"""
    r = client.post("/api/jobs", files={"files": _wav()},
                    data={"src_lang": "zh", "out_langs": "zh"})
    assert r.status_code == 202
    job = r.json()["data"]["jobs"][0]
    assert job["duration"] is not None and job["duration"] >= 0
    d = client.get(f"/api/jobs/{job['job_id']}").json()["data"]
    assert "duration" in d


def test_list_job_outputs_aggregate(client):
    """問題 E：彙整端點一次回所有 transcript 產出（含 job 原檔名），避免前端 N+1。"""
    jid = _make_job(client)
    oid = _seed_transcript(jid)
    body = client.get("/api/jobs/outputs?kind=transcript").json()
    assert body["pagination"]["total"] >= 1
    row = next(o for o in body["data"] if o["id"] == oid)
    assert row["job_id"] == jid and row["kind"] == "transcript"
    assert row["original_name"]              # 帶回 job 原檔名供下拉顯示
    # 'outputs' 不可被當成 job_id 路由（宣告順序）
    assert client.get("/api/jobs/outputs?kind=translation").json()["data"] == []


def test_missing_ffprobe_returns_503(client, monkeypatch):
    """問題 C：環境缺 ffprobe（RuntimeError）→ 明確 503，而非裸 500；不留孤兒。"""
    from services import preprocess

    def _boom(path):
        raise RuntimeError("ffprobe 不存在：請確認映像已安裝 ffmpeg")

    monkeypatch.setattr(preprocess, "probe_duration_seconds", _boom)
    r = client.post("/api/jobs", files={"files": _wav()},
                    data={"src_lang": "zh", "out_langs": "zh"})
    assert r.status_code == 503
    assert r.json()["error"] == "unavailable"
    assert client.get("/api/jobs").json()["pagination"]["total"] == 0
