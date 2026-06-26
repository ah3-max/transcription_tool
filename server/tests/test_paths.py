"""S-02 路徑安全（SEC-3）：白名單副檔名、id 命名、防穿越。"""
import pytest

from storage.paths import build_path, new_id, safe_ext


def test_safe_ext_whitelist():
    assert safe_ext("會議.WAV") == ".wav"          # 大小寫正規化
    for bad in ("note.txt", "x.exe", "noext"):
        with pytest.raises(ValueError):
            safe_ext(bad)


def test_build_path_stays_in_zone():
    p = build_path("uploads", new_id(), ".wav")
    assert "/uploads/" in p and p.endswith(".wav")


def test_build_path_blocks_traversal():
    with pytest.raises(ValueError):
        build_path("uploads", "../../etc/passwd", ".wav")   # 非英數 id
    with pytest.raises(ValueError):
        build_path("uploads", new_id(), "../x")             # 非法副檔名
    with pytest.raises(ValueError):
        build_path("unknown_zone", new_id(), ".wav")        # 未知 zone
