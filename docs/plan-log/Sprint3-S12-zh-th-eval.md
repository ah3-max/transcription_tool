# 規劃：S-12 中→泰品質實測（A 軌．獨立）

> 類型：規劃（事前）｜配對開發日誌：`docs/dev_log/Sprint3-S12-zh-th-eval.md`
> 對應：OQ-1｜依賴：S-05（已完成）｜**不沾 ASR / 不沾 vLLM PoC**
> 並行性：**完全獨立、零衝突**——不改任何正式碼路徑，只寫 DB 一筆端點＋產文件。可與 A/B/C/D 任一軌同時跑。

---

## 1. 現況（已查證）
- `server/services/translate.py` 的 `translate_fanout(text, targets)` 已完成可用：
  - 對 zh 源文一對多扇出（D-03，不串接），zh 直接帶回原文；
  - 逐字稿一律當「資料」與系統指令分離（SEC-4 防注入）；
  - 打 `function=batch_tr` 端點的 `/chat/completions`（`resolve_endpoint("batch_tr")`）。
- `routes/endpoints.py`：`POST /api/endpoints` 可註冊端點（function ∈ asr/batch_tr/live_tr/post）、`PATCH /{id}` 切 active。
- 缺口純為「實測活動」：註冊端點 → 拿真實片段跑三模型 → 泰語母語者評分 → 定預設與退路。

## 2. 待使用者提供（開工前確認）
- LMS 端點位址與模型名（預設 `http://host.docker.internal:1234/v1`，模型名＝？）。
- NLLB（`live_tr`）／TranslateGemma 現在是否在 host 跑？
  - 若只有 LMS Gemma：先完成 **Gemma 臂**，NLLB／TranslateGemma 兩臂標「待對應服務起」，不阻塞結論初版。

## 3. 要做的事（從頭到尾）
1. **註冊端點**：`POST /api/endpoints` 把 LMS Gemma 註冊為 `function=batch_tr`；NLLB／TranslateGemma 各註冊一筆供比較（可暫以不同 batch_tr 名稱、切 active 輪測）。
2. **備測資料**：挑 5–10 段真實長照情境中文（護理術語／中英夾雜／口語），存測試素材（`docs/` 旁或 scratchpad，不進版控的執行資料除外）。
3. **三模型跑批**：寫一次性評測腳本（放 scratchpad 或 `docs/`，**不進正式碼路徑**），對每段用 NLLB／Gemma 4／TranslateGemma 各產泰譯 → 對照表。
4. **母語者評分**：泰語母語者就「準確／流暢／術語」量化（1–5）＋評語。
5. **定預設與退路**：依分數定 Phase 1 預設翻譯模型＋不達標退路；補一條決策記錄、更新 `.env` 註解。

## 4. 收標準（對齊規格 S-12）
- [ ] 量化比較表（≥3 模型 × ≥5 段 × 準確/流暢/術語）＋母語者評語
- [ ] 明確結論：建議預設模型＋不達標退路
- [ ] 寫入配對 dev_log（含原始譯文、分數、決策）

## 5. 並行/衝突
- **碰的檔**：DB `endpoints` 一筆；產出文件。**不改 `.py` 正式碼路徑。**
- **可與所有軌同時跑**：零檔案衝突。
- 唯一外部前置：完整三方比較需 NLLB／TranslateGemma 在 host 跑（非本軌可控，缺則先做 Gemma 臂）。
