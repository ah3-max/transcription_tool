"""上傳深度驗證／前處理入口（S-04 / SEC-2 / G4）。

副檔名＋大小只是表層；本模組以 ffprobe 對「實際內容」把關：
1) 能否解碼、是否含音訊串流 → 擋偽音檔（如 .wav 內容其實是文字）。
2) 取得時長 → 套用 `max_file_min` 上限（config 既有但先前無人使用）。

設計：解碼/時長檢查集中在此「前處理入口」，未來 DeepFilterNet3／Silero VAD
等真前處理也掛在這層，避免與 jobs.py 重複解碼。純呼叫 host 不需要的本地
ffmpeg(在 CPU 容器內，見 Dockerfile)。對外只丟兩種結果：合法→時長秒數；
不合法→丟 BadAudio（呼叫端據此回 4xx 並清檔、不留孤兒）。
"""
import json
import shutil
import subprocess

# ffprobe 子程序逾時（秒）：CPU 容器內解碼，避免惡意/壞檔卡死（G4 雷）。
PROBE_TIMEOUT = 15


class BadAudio(Exception):
    """檔案無法解碼或不含音訊串流。"""


def _ffprobe(path: str) -> dict:
    if shutil.which("ffprobe") is None:
        # 映像未含 ffmpeg（理應由 Dockerfile 安裝）；明確報錯勝過默默放行。
        raise RuntimeError("ffprobe 不存在：請確認映像已安裝 ffmpeg")
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise BadAudio("解碼逾時") from e
    if out.returncode != 0:
        raise BadAudio("無法解碼或非音檔")
    try:
        return json.loads(out.stdout or "{}")
    except json.JSONDecodeError as e:
        raise BadAudio("無法解析音檔資訊") from e


def probe_duration_seconds(path: str) -> float:
    """驗證可解碼且含音訊串流，回時長（秒，float）。不合法丟 BadAudio。"""
    info = _ffprobe(path)
    streams = info.get("streams") or []
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise BadAudio("無法解碼或非音檔")

    # 時長優先取 format.duration；缺漏時退而求其次取音訊串流的 duration。
    raw = (info.get("format") or {}).get("duration")
    if raw is None:
        for s in streams:
            if s.get("codec_type") == "audio" and s.get("duration") is not None:
                raw = s["duration"]
                break
    try:
        dur = float(raw)
    except (TypeError, ValueError) as e:
        raise BadAudio("無法取得音檔時長") from e
    if dur <= 0:
        raise BadAudio("音檔時長異常")
    return dur
