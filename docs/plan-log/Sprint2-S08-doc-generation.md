# 規劃：S-08 文件生成（範本：會議記錄／護理交班／自訂）

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/Sprint2-S08-doc-generation.md`（動工後建）
> 對應：FR-17~FR-20、設計 §2.5／§4.3／§5 API-10；依賴 S-05；被依賴 S-09
> Plan B 可做性：✅ 現在可做（Gemma 已就緒；手動上傳逐字稿即可端到端，不需 vLLM）

## 1. 想解決什麼問題
把逐字稿依範本生成「會議記錄／護理交班」文件；來源可選（錄音記錄/批次產出，分類下拉）或手動上傳逐字稿。

## 2. 要收斂的目標（驗收）
- 來源下拉分類正確（錄音記錄／批次逐字稿 optgroup）、可手動上傳 txt/md/docx。
- 切換範本即更新預覽結構（會議 vs 交班欄位不同）。
- 自訂範本上傳後可套用。
- API-10 `POST /api/records`：來源＋範本 → Gemma 生成 → 存 `outputs`（kind=record）。

## 3. 怎麼改、為什麼
- `services/postprocess.py`：`generate_record(transcript_text, template)` → 呼叫 `post`（或同顆 Gemma）端點，依範本 system prompt 生成結構化文件；逐字稿當「資料」、與指令分離（SEC-4）。
- 範本（先內建）：會議記錄、護理交班（**OQ-3 欄位未定 → 暫定欄位＋標記可調**）、自訂（上傳 md/docx 當範本，python-docx 解析）。
- `routes/records.py`：`POST /api/records`（來源＝job/session 既有 transcript，或手動上傳文字）。
- 為什麼：Gemma 已就緒可生成；範本結構交 system prompt；docx 範本用 python-docx。

## 4. 範圍邊界（做 / 不做）
- **做**：postprocess 生成服務、內建兩範本＋自訂、API-10、`outputs(kind=record)`、pytest（mock 端點）、手動上傳逐字稿路徑（FR-17 本就支援）。
- **不做（待後續）**：來源下拉接「真錄音記錄/批次產出」需 S-04/S-07 資料（先支援手動上傳＋既有 job transcript）；範本切換預覽 UI 屬 S-11；護理交班正式欄位待 OQ-3。

## 5. 驗收清單
- [ ] `POST /api/records`（手動逐字稿＋會議範本）→ Gemma 生成、存 outputs
- [ ] 切交班範本 → 產出結構不同（暫定欄位）
- [ ] 自訂範本（上傳 md/docx）可套用
- [ ] 逐字稿含「指令字樣」不被當指令（SEC-4）
- [ ] pytest（mock 端點）綠

## 6. 開發日誌
> 見 `docs/dev_log/Sprint2-S08-doc-generation.md`（動工後逐步追加）
