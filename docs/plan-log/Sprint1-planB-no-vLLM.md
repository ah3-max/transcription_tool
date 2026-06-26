# 規劃：Plan B — 不依賴 vLLM 的並行軌（Sprint 1 先做範圍 ＋ S-05）

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/Sprint1-planB-no-vLLM.md`（動工後建）
> 背景：vLLM／Qwen3-ASR PoC **並行進行中**（解鎖 S-04 核心與 S-06）。本軌同時把**不依賴 ASR** 的東西往前推，PoC 一完成即可把 S-04 worker／S-06 插回。

## 1. 策略（為什麼這樣）
ASR（語音→文字）是**唯一**被 vLLM 卡住的能力；其餘 Story 都在處理「文字」。文字 LLM＝LM Studio 的 Gemma（`host.docker.internal:1234`）**已在跑、容器可達**（S-01 已驗證）。因此趁 PoC 進行，並行把「文字鏈＋前端」推進，零等待。

## 2. Sprint 1 可做範圍（標明卡點）
| Story | 可做？ | 範圍 |
|---|---|---|
| S-04 批次轉錄 | ⏸ 部分 | 骨架已完成；**核心（降噪/VAD/切段/Qwen3-ASR/真進度）＝等 PoC**，不在本軌 |
| **S-05 批次翻譯** | ✅ **本軌主目標** | 翻譯服務 fan-out（zh→th/en，獨立不串接 D-03）走 `batch_tr`＝Gemma；可現在做＋單測 |
| S-06 即時串流 | ⏸ 否 | 等 PoC（vLLM 串流 ASR ＋ NLLB），不在本軌 |

**可順帶往前（Sprint 2/3，同樣不需 vLLM；本軌做完 S-05 可接續）：**
- **S-08 文件生成**：FR-17 本就支援「手動上傳逐字稿」→範本→Gemma→預覽，**可端到端 demo**。
- **S-09 匯出**：python-docx 出 docx/md/txt，純後端、可單測。
- **S-11 前端串接**：把現有 API（jobs／endpoints／resources／上傳／翻譯預覽）接進 v6 UI。

## 3. 先做：S-05 批次翻譯（怎麼改、為什麼）
- `services/translate.py`：`translate_text(zh_text, targets) -> {lang: text}`，對**每個**目標語言獨立呼叫 `resolve_endpoint('batch_tr')` 的 OpenAI 相容 `/chat/completions`（Gemma），**扇出、不串接**（D-03）。System prompt 把逐字稿當「資料」、與指令分離（SEC-4 防提示注入）。
- 譯文存 `outputs`（`kind=translation`、`lang`、`ref_type=job`、`ref_id`）。
- **輸入來源**（S-04 還沒產逐字稿）：
  - 真實流程：批次 job 轉錄完成後對 zh 逐字稿翻譯（**待 S-04 worker**）。
  - 本軌可驗：以「某 job 既有 zh transcript output」為來源的重翻路徑；測試用種子 transcript。
- 為什麼：D-03 一對多扇出、與主 LLM 解耦；batch_tr 預設 Gemma（已就緒）；SEC-4 資料/指令分離。

## 4. 範圍邊界（做 / 不做）
- **做**：`translate.py` 扇出服務、`outputs` 存放、pytest（mock 端點驗扇出/儲存/注入隔離）、可選對真 Gemma 冒煙一筆。
- **不做（等 PoC／後續）**：S-04 ASR 與真逐字稿產生、S-06 即時、NLLB（即時用）。整條 upload→ASR→translate 端到端待 S-04 worker。

## 5. 驗收（S-05 本軌部分）
- [ ] `translate_text(zh, ["th","en"])` 對每語言各打一次 `batch_tr` 端點、回各自譯文（fan-out 不串接）
- [ ] 無 active `batch_tr` 端點時回明確錯誤（不 500）
- [ ] 譯文寫入 `outputs`（`kind=translation`）
- [ ] pytest：mock 端點驗扇出與儲存；逐字稿含「指令字樣」不被當指令（SEC-4）
- [ ] （可選）對真 Gemma 冒煙：一句中文 → 出泰/英

## 6. 等 PoC 完成後（不在本軌、先記著）
- **S-04 worker**：取 `queued` → 降噪/VAD/切段/Qwen3-ASR → 寫 zh transcript output → 觸發 S-05 → 真進度/status。
- **S-06**：`/ws/live` 串流 ASR ＋ NLLB 即時翻譯。

## 7. 開發日誌
> 見 `docs/dev_log/Sprint1-planB-no-vLLM.md`（動工後逐步追加）
