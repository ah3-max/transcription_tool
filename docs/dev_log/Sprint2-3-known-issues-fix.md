# 開發日誌：S-08／S-09／S-11 已知問題修復（A–G）

> 建立：2026-06-26 ｜ 類型：開發日誌 ｜ 配對規劃：[`Sprint2-3-known-issues-fix`](../plan-log/Sprint2-3-known-issues-fix.md)
> 來源交接：[`Sprint2-3-known-issues-handoff`](Sprint2-3-known-issues-handoff.md)

## 原狀
review 後彙整 8 個問題（A–H）。動工前先 `git status`／讀現況查證：
- **H 已解除**：交接擔心 `jobs.py`/`test_jobs.py` 被另一條 session 同時改，但 S-04 深驗已 commit（`60713b8`），現無並行改動，可安全動工。
- 後端 API 形狀確認：`GET /api/jobs/{id}` 已回 `outputs` 索引；`records.py` 確無列表端點；`outputs` 表無 `template` 欄位。
- G 確認：`test_postprocess.py` 實際 `def test_` 7 個。

## 改動
- **A（`web/app.js` `loadHistory`）**：不再憑 `out_langs` 猜、不再寫死 `kind=transcript`。改成用彙整端點撈 transcript＋translation，依「實際 outputs」生鈕，URL 帶真實 `kind/lang/fmt`；無產出顯示「尚無可下載產出」。
- **B（後端 `records.py`）**：新增 `GET /api/records?limit=&offset=`，列 `kind='record'` 的 outputs，回 `{id,ref_type,ref_id,fmt,created_at}`＋pagination。**前端**（`index.html`/`app.js`）文件生成頁新增「已生成的記錄」卡片＋`loadRecords()`，進頁與生成後刷新，可重新匯出（docx/md/txt）。範本別未存表故不顯示（已於程式碼註明）。
- **C（後端 `jobs.py`）**：`create_jobs` 在深驗處加攔 `RuntimeError`（ffprobe 不存在）→ 503 `unavailable`＋清檔不留孤兒。
- **D（`web/styles/tokens.css`）**：`.ic`（+min-width＋inline-flex 置中）、`.dd-sm`、`.seg button`、`.btn.sm`、`.icon-btn` 一律 ≥48px。
- **E（後端 `jobs.py`）**：新增 `GET /api/jobs/outputs?kind=`（JOIN jobs 帶回 `original_name`），宣告於 `/{job_id}` 之前。前端 `loadTranscriptSources` 由 N+1 改單次呼叫；歷史頁亦改用之。
- **F（`web/app.js`）**：抽 `download(path, filename, msgEl)` 走 `fetch`→`res.ok`→`blob`→`a[download]`；歷史匯出與記錄匯出全改用，失敗用 `histMsg`/`recMsg`/`genMsg` 顯示友善訊息（新增 `dl.fail` 字典）。
- **G**：訂正 `Sprint2-S08-doc-generation.md` 6 項 → 7 項。
- **i18n**：新增 `gen.histTitle/histHint/histEmpty`、`hist.noOutput`、`kind.transcript/translation/record`、`dl.fail`（皆 zh/en/th）。

## 困難與解法
- **路由吃路徑**：`GET /api/jobs/outputs` 會被既有 `/{job_id}` 收成 `job_id='outputs'`。解法：把新端點宣告於 `/{job_id}` 之前；並加測試 `assert .../outputs?kind=translation` 回空陣列佐證沒被誤路由。
- **本機無 python/ffprobe**：依交接文件以 `uv venv /tmp/ttenv` 建環境＋假 ffprobe 到 PATH 跑測試。

## 驗證（寫好 ≠ 驗過）
- 後端 `pytest -q` → **52 passed**（含新增 3 測試：`test_list_job_outputs_aggregate`、`test_missing_ffprobe_returns_503`、`test_list_records`）。
- Python 語法檢查 routes OK；`node -c web/app.js` OK；新 HTML i18n key 皆在字典、新字典 key 皆有 zh/en/th。
- **未做**：前端人工起站點擊驗證（需使用者環境起站）；範圍外 H（已自然解除）。
