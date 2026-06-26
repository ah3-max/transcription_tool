# 開發日誌：S-11 前端拆檔與 API 串接（v6 愛愛院版，原生 HTML）

> 類型：開發日誌（事中／事後）｜ 配對規劃：`docs/plan-log/Sprint3-S11-frontend.md`
> 對應：FR-23/24、NFR-5/6、D-11；格式：原本 → 發生 → 改了什麼 → 困難 → 又怎麼改 → 解決

---

**① 2026-06-26｜拆 4 檔＋串接 endpoints/resources/jobs/records/export**
- 原本：`web/index.html` 是 v6 雛形整檔內嵌（`<style>` 276 行、`<script>` IIFE 207 行），全 mock 資料、零 API。
- 發生：要讓五畫面接真實 API、同源相對路徑（D-11），且行為與雛形等價、無框架。
- 改了什麼：
  ① 拆檔：`<style>`→`styles/tokens.css`（程式化抽出，逐字不動）；`I` 字典＋`t()`→`i18n.js`（掛 `window.I18N`：`I`/`t`/`lang`/`setLang`）；其餘行為→`app.js`；`index.html` 改 `<link>`＋`<script src>`，markup 與 data-i18n／無障礙結構保留。
  ② `app.js` 新增 API 層（`fetch('/api'…)`、解 `{data,error,message}`）：
  - 設定：`GET/POST/PATCH/DELETE /api/endpoints` 動態渲染路由表＋新增/停用/刪除；`GET /api/resources` 每 5 秒輪詢頂欄 VRAM/RAM。
  - **資源用量預設隱藏**（plan 驗收）：`#res` 初始加 `hide`、眼睛鈕切換、隱藏時不打 API。
  - 批次：拖放/點擊上傳（動態 hidden input）→ `POST /api/jobs`（files[]+src_lang+out_langs）；清單／歷史用 `GET /api/jobs`；歷史每語言給 API-04 匯出鈕。
  - 文件生成：範本切換更新預覽結構（沿用）；「依範本生成」→ `POST /api/records`（手動上傳或選來源）→ 顯示回傳 content；匯出 → `GET /api/records/{id}/export`。
  ③ 對應補 markup hooks（id/data-*）：批次來源語言 `data-src=zh|zh_en|en`、輸出 chip `data-lang`、端點表 `tbody#epTable`、生成結果 `#genResult` 等。i18n.js 補 S-11 新字串。
- 遇到困難：(a) 後端 `create_jobs` 已被加上 `src_lang ∈ {zh,zh_en,en}` 驗證（非 zh/en/th），前端送錯會 400。(b) 雛形 `applyLang` 內含 app 專屬 DOM ref（srcToggle/progBtn），純放 i18n.js 會循環相依。(c) 來源下拉需既有 transcript 產出，但 S-04/05 未落檔。
- 又怎麼改：(a) 辨識語言 seg 按鈕標 `data-src`，送 `zh/zh_en/en`、與後端同步。(b) i18n.js 只放字典＋純 `t()`＋`lang` 狀態，`applyLang`（DOM）留在 app.js 呼叫 `I18N.t`。(c) 來源下拉動態查 jobs→outputs（目前多為空，不擋頁）；手動上傳路徑現在即可端到端。
- 最後如何解決：**驗證通過** — uvicorn 起站，`/`、`/app.js`、`/i18n.js`、`/styles/tokens.css` 皆 200 正確 MIME；端點新增→列表出現；資源輪詢回真值（無 GPU 顯 N/A）；批次上傳→job queued；mock `post` 端點下手動上傳逐字稿→生成→docx/txt 匯出（pdf 400）。
- 待續（先 stub/佔位）：批次結果「逐字稿/翻譯預覽」待 S-04/05 outputs；即時舞台 S-06；錄音記錄頁接 session API S-07。文件生成見 [`Sprint2-S08-doc-generation`](../dev_log/Sprint2-S08-doc-generation.md)、匯出見 [`Sprint2-S09-export-history`](../dev_log/Sprint2-S09-export-history.md)。
