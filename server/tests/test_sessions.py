"""S-06 步驟 5 ★寫入契約：save_live_session 落地 sessions/outputs/檔案。"""
import json
import os

from models_db.db import db
from services.sessions import pcm16_to_wav, save_live_session


def test_pcm16_to_wav_header():
    wav = pcm16_to_wav(b"\x01\x00\x02\x00", sample_rate=16000)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    assert wav[36:40] == b"data"
    assert len(wav) == 44 + 4


def test_save_live_session_writes_contract(_fresh_db):
    sid = save_live_session(
        name="晨會", src_lang="zh", targets=["zh", "th", "en"], duration_sec=42,
        transcript="今天血壓偏高", translations={"th": "ความดันสูง", "en": "high BP"},
        audio_pcm16=b"\x00\x01" * 100,
    )
    assert sid.startswith("s_")
    with db() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
        outs = conn.execute(
            "SELECT kind,lang,path FROM outputs WHERE ref_id=? AND ref_type='session' "
            "ORDER BY kind,lang", (sid,)).fetchall()

    assert s["status"] == "done" and s["duration"] == 42
    assert json.loads(s["langs"]) == ["zh", "th", "en"]
    assert s["audio_path"] and os.path.isfile(s["audio_path"])
    assert s["transcript_path"] and os.path.isfile(s["transcript_path"])

    kinds = sorted((o["kind"], o["lang"]) for o in outs)
    # 1 筆 transcript(zh) + 2 筆 translation(th,en)；來源語 zh 不另寫 translation
    assert kinds == [("transcript", "zh"), ("translation", "en"), ("translation", "th")]
    with open(s["transcript_path"], encoding="utf-8") as f:
        assert f.read() == "今天血壓偏高"


def test_save_live_session_no_audio(_fresh_db):
    sid = save_live_session(
        name=None, src_lang="zh", targets=["th"], duration_sec=5,
        transcript="x", translations={"th": "y"}, audio_pcm16=b"",
    )
    with db() as conn:
        s = conn.execute("SELECT * FROM sessions WHERE session_id=?", (sid,)).fetchone()
    assert s["audio_path"] is None
