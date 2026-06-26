"""即時場次落地（S-06 步驟 5，★D 軌 S-07 依賴契約，FR-6/FR-7）。

停止即時翻譯時：把整場錄音落地（recordings 區）＋逐字稿與各語譯文落地（outputs 區）、
建立 `sessions` 列＋寫 `outputs` 列，回 session_id。檔名一律用伺服器 id（原檔名不入路徑）。

★ 寫入契約（凍結 2026-06-27，S-07 後端據此並行；改欄位＝全鏈路同步）：
  sessions：session_id / name / langs(JSON, [src]+targets) / duration(秒) / status='done'
            / created_at / expire_at(＝created_at+retention_days) / audio_path / transcript_path
  outputs ：ref_type='session', ref_id=session_id,
            kind='transcript' lang=src  （逐字稿，每場一筆）
            kind='translation' lang=<目標語> （每目標語一筆；來源語不另寫 translation）
  音檔：recordings 區，16kHz 單聲道 PCM16 封成 .wav；無音框則 audio_path=None。
"""
import io
import json
import struct
import time

from config import settings
from models_db.db import db
from storage.paths import build_path, ensure_zone, new_id

SAMPLE_RATE = 16000  # 即時上行固定 16kHz 單聲道 PCM16（PoC 餵法）


def pcm16_to_wav(pcm16: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """把裸 PCM16（單聲道）封成最小 WAV（含 44-byte header）。"""
    n = len(pcm16)
    buf = io.BytesIO()
    buf.write(b"RIFF")
    buf.write(struct.pack("<I", 36 + n))      # ChunkSize
    buf.write(b"WAVE")
    buf.write(b"fmt ")
    buf.write(struct.pack("<I", 16))           # Subchunk1Size (PCM)
    buf.write(struct.pack("<H", 1))            # AudioFormat = PCM
    buf.write(struct.pack("<H", 1))            # NumChannels = 1
    buf.write(struct.pack("<I", sample_rate))
    buf.write(struct.pack("<I", sample_rate * 2))  # ByteRate = rate*channels*2
    buf.write(struct.pack("<H", 2))            # BlockAlign = channels*2
    buf.write(struct.pack("<H", 16))           # BitsPerSample
    buf.write(b"data")
    buf.write(struct.pack("<I", n))
    buf.write(pcm16)
    return buf.getvalue()


def _write_text(zone: str, text: str, ext: str = ".txt") -> tuple[str, str]:
    ensure_zone(zone)
    fid = new_id()
    path = build_path(zone, fid, ext)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return fid, path


def _write_bytes(zone: str, data: bytes, ext: str) -> tuple[str, str]:
    ensure_zone(zone)
    fid = new_id()
    path = build_path(zone, fid, ext)
    with open(path, "wb") as f:
        f.write(data)
    return fid, path


def save_live_session(*, name: str | None, src_lang: str, targets: list[str],
                      duration_sec: int, transcript: str,
                      translations: dict[str, str], audio_pcm16: bytes | None) -> str:
    """落地一場即時翻譯，回 session_id。見模組頂部寫入契約。"""
    sid = new_id("s_")
    now = int(time.time())
    expire = now + settings.retention_days * 86400
    langs = [src_lang] + [l for l in targets if l != src_lang]

    audio_path = None
    if audio_pcm16:
        _, audio_path = _write_bytes("recordings", pcm16_to_wav(audio_pcm16), ".wav")

    _, transcript_path = _write_text("outputs", transcript or "")

    with db() as conn:
        conn.execute(
            "INSERT INTO sessions(session_id,name,langs,duration,status,created_at,"
            "expire_at,audio_path,transcript_path) VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, name, json.dumps(langs), int(duration_sec), "done", now, expire,
             audio_path, transcript_path),
        )
        # 逐字稿 output（kind=transcript，lang=來源語）
        conn.execute(
            "INSERT INTO outputs(id,ref_type,ref_id,kind,lang,fmt,path,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("o_" + new_id(), "session", sid, "transcript", src_lang, "txt",
             transcript_path, now),
        )
        # 各目標語譯文 output（kind=translation）；來源語不另寫
        for lang in targets:
            if lang == src_lang:
                continue
            _, tpath = _write_text("outputs", translations.get(lang, "") or "")
            conn.execute(
                "INSERT INTO outputs(id,ref_type,ref_id,kind,lang,fmt,path,created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("o_" + new_id(), "session", sid, "translation", lang, "txt", tpath, now),
            )
    return sid
