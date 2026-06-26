# 規劃：S-04 jobs 加固（修孤兒 job bug＋10GB 上限）＋ Sprint 0 pytest 測試套件

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/Sprint1-S04-hardening-tests.md`
> 對應：S-04（API-01 上傳加固，SEC-5）、開發執行手冊 §4 測試策略（補可重跑 pytest）
> 前提：已 push `origin/main`（4 commits）；本次在其上做加固與測試。

## 1. 想解決什麼問題
- **(a) 多檔上傳原子性 bug**（`routes/jobs.py:74-92`）：副檔名檢查在迴圈內、逐檔即時 commit；上傳 `[好.wav, 壞.txt]` 會先落檔＋建 `queued` 列，第 2 檔才回 400 → 留**孤兒 job/檔**且回應誤導。
- **(b) 上傳無大小上限**（SEC-5）：`jobs.py:83-85` 無限串流寫入，巨檔可塞爆磁碟。使用者要 **10GB 防亂塞**；**時長不擋**（長音檔交未來 S-04 切段，目前尚未實作）。
- **(c) 零自動化測試**：驗證全靠臨時手動、不可重跑（§4 要求 pytest）。

## 2. 要收斂的目標（驗收）
- 多檔含壞副檔名 → 400 且**完全不落檔、不建列**（原子）。
- 單次上傳累計 > 10GB → 413、清掉已寫暫存、不建列。
- pytest 套件可在容器內一鍵跑綠：paths 穿越／cleanup／jobs（含 bug 回歸）／reserve／health／endpoints。
- 既有里程碑三條 curl 不回歸。

## 3. 要怎麼改、為什麼這樣
### 3.1 `routes/jobs.py` POST 重構為「先驗 → 再寫 → 全寫成功才入庫」
1. 先驗**所有** files 副檔名（任一不合 → 400 `bad_file`，零副作用）。
2. `can_reserve` 守門（既有，503）。
3. 寫入迴圈累計位元組；超過 `MAX_UPLOAD_BYTES` → 刪除本請求已寫檔 → 413 `error:"too_large"`。
4. 全部寫成功後，**單一交易插入所有 job 列**；插入失敗 → 刪除已寫檔（best-effort）。
→ 消除孤兒 job、加上限、維持 202 與統一外型。
### 3.2 `config.py` 新增 `max_upload_gb`（預設 10）；`.env`／`.env.example` 同步加 `MAX_UPLOAD_GB=10`。Content-Length 若有先擋（快速拒絕），串流再硬擋（防偽報／分塊）。
### 3.3 `server/tests/`（pytest）
- `conftest.py`：**import app 前**把 `DATA_DIR`／`DB_PATH` 指到 tmp，避免碰 `/data`。
- `test_paths.py`（穿越/id 命名）、`test_cleanup.py`（到期刪檔＋列）、`test_jobs.py`（202／.txt→400／**[好,壞]→無孤兒回歸**／cap 以小值模擬→413／清單分頁／單筆 404／DELETE）、`test_reserve.py`（RES_CAP=0→503）、`test_health.py`、`test_endpoints.py`（CRUD＋壞 function 400）。
- `requirements.txt` 加 `pytest`；rebuild 映像；`docker compose exec stt-app python -m pytest` 跑。

## 4. 範圍邊界（做 / 不做）
- **做**：上述加固＋測試。
- **不做**：真前處理／VAD／切段／ASR（S-04 其餘）、MIME 深度解碼（S-13）、翻譯（S-05）。

## 5. 驗收檢查清單
- [ ] `[好.wav, 壞.txt]` → 400 且 jobs 表零新增、uploads 無殘檔
- [ ] 小 cap 模擬：超量 → 413、殘檔清除、零列
- [ ] 正常多檔 → 202、皆 queued、id 命名
- [ ] pytest 全綠（記錄 N passed）
- [ ] 既有里程碑三條 curl 仍通

## 6. commit 規劃（兩個可驗收單元）
- `fix(S-04): 多檔上傳先驗後寫(修孤兒 job)＋10GB 上限(SEC-5)`
- `test: Sprint0/S-04 pytest 套件(paths/cleanup/jobs/reserve/health/endpoints)`

## 7. 開發日誌
> 見 `docs/dev_log/Sprint1-S04-hardening-tests.md`（動工後逐步追加）
