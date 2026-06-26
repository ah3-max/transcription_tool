"""pytest 設定：用暫存資料根與 DB，絕不碰 /data。

務必在 import 任何專案模組（會建立 config 單例）之前先設好環境變數。
"""
import os
import sys
import tempfile

# 讓 server 根（/app）可被 import（python -m pytest 於 /app 跑時本就在 path，這裡再保險）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 在 config 單例建立前，把資料根與 DB 指向暫存
_TMP = tempfile.mkdtemp(prefix="stt-test-")
os.environ["DATA_DIR"] = _TMP
os.environ["DB_PATH"] = os.path.join(_TMP, "test.db")
os.environ["WEB_DIR"] = _TMP            # StaticFiles 掛載需存在的目錄
os.environ["RES_CAP"] = "0.8"

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _fresh_db():
    """每個測試前重建乾淨 DB。"""
    from models_db.db import init_db
    if os.path.isfile(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])
    init_db()
    yield


@pytest.fixture
def client():
    from main import app
    with TestClient(app) as c:   # 進入 context 會跑 lifespan（init_db）
        yield c
