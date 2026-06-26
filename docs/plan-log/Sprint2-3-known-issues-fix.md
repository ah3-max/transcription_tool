# 規劃：S-08／S-09／S-11 已知問題修復（A–G）

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對日誌：[`Sprint2-3-known-issues-fix`](../dev_log/Sprint2-3-known-issues-fix.md)
> 來源：[`Sprint2-3-known-issues-handoff`](../dev_log/Sprint2-3-known-issues-handoff.md)（review 後彙整的 8 個問題）
> 目標：把交接文件提到的問題 A–G 全部修完（H 為流程提醒、S-04 已 commit 60713b8 故解除）。

## 範圍與順序
照交接建議優先序 **A → B → F → D → C → E**，外加文件訂正 G。

| # | 問題 | 修法摘要 | 動到的檔 |
|---|---|---|---|
| A | 歷史匯出一律 404、kind/lang 錯配 | `loadHistory` 改依「實際 outputs」生鈕、URL 用真實 kind | `web/app.js` |
| B | 無記錄列表 API、重整後找不回手動記錄 | 後端加 `GET /api/records`；前端文件生成頁加「已生成記錄」清單 | `server/routes/records.py`、`web/index.html`、`web/app.js`、`web/i18n.js` |
| C | 缺 ffprobe → 裸 500 | `create_jobs` 攔 `RuntimeError` → 503 `unavailable` | `server/routes/jobs.py` |
| D | 次要可點元件 <48px | `.ic/.dd-sm/.seg button/.btn.sm/.icon-btn` min-height:48px | `web/styles/tokens.css` |
| E | 來源下拉 N+1 | 後端加 `GET /api/jobs/outputs?kind=`；前端單次取回（歷史頁也改用） | `server/routes/jobs.py`、`web/app.js` |
| F | 匯出走 `window.location`、4xx 整頁洗成 JSON | 抽 `download()` 走 fetch→ok→blob，失敗用既有 msg 元件提示 | `web/app.js` |
| G | dev_log 寫 6 項（實為 7） | 訂正 | `docs/dev_log/Sprint2-S08-doc-generation.md` |

## 決策
- **E 端點命名 `GET /api/jobs/outputs`**：須宣告於 `/{job_id}` 之前，否則被路由成 `job_id='outputs'`。
- **B 不為 template 加 migration**：`outputs` 表無 template 欄位，列表先不顯示範本別並於程式碼／API doc 標註，避免為顯示性需求動資料模型（如日後要顯示再補欄位）。
- **A 與歷史頁也改用 E 的彙整端點**：歷史頁原本也會逐 job N+1，順手用同一端點（transcript＋translation 兩次呼叫）取代。

## 驗收
- 後端 pytest 全綠，新增 3 測試：`test_list_job_outputs_aggregate`、`test_missing_ffprobe_returns_503`、`test_list_records`。
- 前端無自動化測試 → 靠人工起站驗證（歷史匯出、記錄清單重新匯出、缺端點不再整頁跳走）。
