# 開發日誌：S-04 jobs 加固（修孤兒 job＋10GB 上限）＋ Sprint 0 pytest 測試套件

> 類型：開發日誌 ｜ 配對規劃：`docs/plan-log/Sprint1-S04-hardening-tests.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**① 2026-06-26｜jobs 加固＋pytest（在已 push 的 origin/main 上）**
- 原本：`POST /api/jobs` 副檔名檢查在迴圈內、逐檔即時 commit（多檔含壞副檔名會留孤兒 job/檔並回誤導性 400）；無上傳大小上限；全專案零 pytest。
- 發生：使用者要求 ① 修孤兒 bug ② 加 10GB 防亂塞上限（時長交未來切段、不擋）③ 補可重跑測試。
- 改了什麼：
  - `routes/jobs.py` POST 重構為「**先驗所有副檔名** → Content-Length 快擋＋串流累計硬擋(`MAX_UPLOAD_GB`) → `can_reserve` 守門 → **全寫成功才單一交易入庫**」；任一步失敗 `_cleanup` 清掉本請求暫存、不留孤兒。新增 `_err`／`_cleanup`、import `Request`。
  - `config.py` 加 `max_upload_gb=10`；`.env`／`.env.example` 加 `MAX_UPLOAD_GB=10`。
  - `requirements.txt` 加 `pytest`；新增 `server/tests/`：`conftest`（tmp `DATA_DIR`/`DB_PATH`，不碰 `/data`）＋ `test_health/paths/cleanup/endpoints/jobs`。
- 遇到困難：（a）測試需與 `/data` 隔離，且 `config` 是 import 期單例 → conftest 必須在 import 專案模組「之前」設好 `DATA_DIR`/`DB_PATH`/`WEB_DIR`。（b）pytest 不在原映像 → 需 rebuild。
- 又怎麼改：conftest 於模組頂端先設環境變數＋`sys.path`；`docker compose up -d --build` 重建含 pytest 的映像。
- 最後如何解決：**驗證通過**。
  - pytest：`docker compose exec stt-app python -m pytest tests -q` → **15 passed**（1 個 `httpx/starlette testclient` deprecation warning，不影響，之後可換 `httpx2`）。
  - 活體（3600 服務）：正常 `.wav`→202 建 `queued`、落檔 id 命名 `10800c802bd7.wav`（非原檔名）；清單 `total=1`＋pagination；**好+壞→400 `bad_file` 且清單 `total` 仍=1（無孤兒，回歸通過）**；DELETE 後 uploads 歸零、`total=0`。
- 待續：真前處理／VAD／切段／ASR（S-04 其餘）、MIME 深度解碼（S-13）、翻譯（S-05）；pytest 之後可分離成 dev 依賴、prod 映像瘦身。
