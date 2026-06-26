# 開發日誌：S-09 匯出（docx/md/txt）與批次歷史

> 類型：開發日誌（事中／事後）｜ 配對規劃：`docs/plan-log/Sprint2-S09-export-history.md`
> 對應：FR-10/16/20/25、NG-3、API-04；格式：原本 → 發生 → 改了什麼 → 困難 → 又怎麼改 → 解決

---

**① 2026-06-26｜export 渲染＋API-04＋記錄匯出＋歷史產出索引**
- 原本：產出內容無法下載；`GET /api/jobs/{id}` 不含產出索引；無任何 render。
- 發生：各處要統一「選格式＋匯出」把產出（逐字稿/翻譯/文件）匯出成 docx/md/txt（**不做 PDF**，NG-3/D-05），歷史要能列出可下載產出。
- 改了什麼：
  ① `services/export.py`：`render(content_md, fmt, title=None) -> (bytes, media_type, ext)`。`md` 原樣 utf-8；`txt` 去 Markdown 標記（標題去 `#`、項目轉 `・`）；`docx` 用 python-docx 套 §7.2 字級（H1 26pt＋品牌主色 #00A97A 粗體、H2 20pt、內文 11pt），解析 `#`/`##`/`- `。`fmt` 非 txt/md/docx（含 pdf）→ `ValueError`。
  ② `routes/jobs.py` API-04 `GET /api/jobs/{id}/export?fmt=&lang=&kind=`：依 job＋lang＋kind 查 `outputs` → 讀內容檔 → render → `StreamingResponse`＋`Content-Disposition`（檔名用 server id，不含原檔名 SEC-3）；無產出 404、fmt 非法 400。並補 `get_job` 回傳 `outputs`（產出索引，不外露 path）。
  ③ `routes/records.py` `GET /api/records/{output_id}/export?fmt=`：記錄不一定屬某 job，故獨立匯出（API-04 維持 job-scoped 合規）。
- 遇到困難：(a) S-04/05 尚未產出 transcript/translation 落檔，job 匯出無內容可測。(b) docx 是二進位，怎麼斷言它有效。
- 又怎麼改：(a) 測試以種子產出（直接寫一份 `kind=transcript` 的 outputs 檔）驗 API-04。(b) `test_export.py` 把 render 出的 docx bytes 用 python-docx 重新開啟，斷言標題段落存在；實機再把下載的 docx 重開、確認 H1 顏色 `00A97A`。
- 最後如何解決：**驗證通過** — pytest 綠（`test_export.py` 6 項＋`test_jobs.py` 補 4 項：種子 transcript → md 匯出含內容、`fmt=pdf` 400、無產出 404、`get_job` 含 outputs）。實機：記錄 docx 下載 36KB、可用 python-docx 開啟（標題正確、H1=00A97A）；txt 去標記正確；pdf 一律 400。
- 待續：真實逐字稿/翻譯內容來源待 S-04/05 worker 落檔（屆時 API-04 即有內容）；前端匯出 UI 串接見 [`Sprint3-S11-frontend`](Sprint3-S11-frontend.md)；文件生成來源見 [`Sprint2-S08-doc-generation`](Sprint2-S08-doc-generation.md)。
