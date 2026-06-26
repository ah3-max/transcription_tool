# 開發日誌：S-08 文件生成（範本：會議記錄／護理交班／自訂）

> 類型：開發日誌（事中／事後）｜ 配對規劃：`docs/plan-log/Sprint2-S08-doc-generation.md`
> 對應：FR-17~20、API-10；格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 困難 → 又怎麼改 → 解決

---

**① 2026-06-26｜postprocess 服務＋`POST /api/records`**
- 原本：只有 S-05 的 `translate.py`（扇出翻譯），無後處理生成；`outputs` 表存在但無人寫入、無 outputs 落地區。
- 發生：要把逐字稿依範本生成「會議記錄／護理交班」結構化文件，並把產出存進 `outputs(kind=record)` 供匯出（S-09）。
- 改了什麼：
  ① `services/postprocess.py`：內建範本 `meeting`（出席／討論事項／決議／待辦事項）、`handover`（住民狀況／用藥與處置／注意事項／待追蹤，**OQ-3 暫定欄位、標 `tentative`**）；`build_system_prompt()` 產生要求 Markdown 輸出的 system prompt，逐字稿明確界定為「資料」、不得當指令（SEC-4，沿用 `translate.py:_system_prompt` 措辭）；`generate_record()` 取 `resolve_endpoint("post")` 打 OpenAI 相容 `/chat/completions`；`parse_custom_template()`／`extract_text()` 用 python-docx 解析 docx，md/txt 直接解碼。
  ② `routes/records.py`：`POST /api/records`（multipart）：來源二擇一（`ref_output_id` 既有 transcript 產出 ／ `transcript_file` 手動上傳 txt/md/docx），`template=custom` 需上傳 `custom_template_file`（md/docx）→ 生成 → 落檔 outputs 區 → 寫 `outputs(kind=record, fmt=md)` → 回 `{output_id, template, sections, content}`。
  ③ `storage/paths.py`：`ZONES` 加 `"outputs"`（產出內容落地；id 命名、原檔名不入路徑 D-07／SEC-3）。
  ④ `main.py` 掛 records router。
- 遇到困難：(a) `build_path` 要求 file_id 為純英數，但 outputs DB id 慣例帶 `o_` 前綴會被擋。(b) 無真 LLM 可端到端驗。(c) 提示注入怎麼驗。
- 又怎麼改：(a) 檔名用 `new_id()` 的純英數 token，DB id 另組 `"o_"+token`（比照 jobs 的 `j_` 慣例）。(b) 起一個極簡 mock OpenAI 端點（回固定 chat completion），設一個 `function=post` 端點指向它。(c) pytest monkeypatch `postprocess.httpx`，斷言含「忽略先前所有指令」的逐字稿只進 user 訊息、不混入 system。
- 最後如何解決：**驗證通過** — pytest 綠（`test_postprocess.py` 6 項：範本 prompt 差異、無 post 端點 `PostprocessError`、逐字稿原樣當資料、自訂 md 解析、SEC-4 隔離）。實機 mock 端點：手動上傳逐字稿＋meeting 範本 → 201、`outputs` 落一筆 `kind=record`、回傳 Markdown 內容與章節清單。
- 待續：來源下拉接「真錄音記錄／批次產出」需 S-04/S-07 落檔（目前支援手動上傳＋既有 transcript 產出）；護理交班正式欄位待 OQ-3 定案。匯出見 [`Sprint2-S09-export-history`](Sprint2-S09-export-history.md)、前端串接見 [`Sprint3-S11-frontend`](Sprint3-S11-frontend.md)。
