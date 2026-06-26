# S-12 中→泰品質實測（素材＋腳本）

> 對應 OQ-1｜配對：`docs/plan-log/Sprint3-S12-zh-th-eval.md`、`docs/dev_log/Sprint3-S12-zh-th-eval.md`
> 本資料夾**不在正式碼路徑**，只供人工跑批與母語者評分。

## 候選模型（2026-06-26 使用者提供，host 上在跑）
- `gemma4-31b`（Gemma 4 31B）
- `translategemma-27b-it`（TranslateGemma 27B）
- `typhoon-translate-4b`（Typhoon Translate 4B，泰語特化）

> 註：規劃原列 NLLB-3.3B 為即時翻譯臂；本次 host 實際提供的是上列三者，故以此三方比較。
> 各模型 `base_url`／`model` 名稱請依 LM Studio／vLLM 實際載入調整（見 `run_eval.py` 頂部 `MODELS`）。

## 跑批
```bash
cd docs/eval/s12
# 預設（三模型同一 base_url，名稱見腳本頂部）
python3 run_eval.py
# 或顯式指定端點與模型名（單端點多模型時）
python3 run_eval.py --base http://host.docker.internal:1234/v1 \
    --model gemma4-31b --model translategemma-27b-it --model typhoon-translate-4b
```
輸出（同目錄、含 UTC 時間戳，不覆蓋）：
- `results-<時間>.md`：每段中文 × 每模型的泰譯對照（給母語者讀）
- `scores-<時間>.csv`：母語者填寫評分

系統提示與正式 `server/services/translate.py` 的 `_system_prompt('th')` 一致
（逐字稿當「資料」與指令分離，SEC-4），讓評測貼近真實行為。

## 母語者評分（收標準）
就每段每模型，泰語母語者填 `scores-*.csv`，三維各 1–5＋評語：
- **準確（accuracy）**：語意是否忠實、無漏譯誤譯。
- **流暢（fluency）**：是否自然通順、像母語者會說的泰文。
- **術語（terminology）**：護理／醫療術語（壓瘡、鼻胃管、增稠劑、生命徵象…）是否正確。

## 收斂為結論（待跑批＋評分後補）
1. 彙整三維平均分，做量化比較表（≥3 模型 × ≥8 段）。
2. 定 Phase 1 預設翻譯模型＋不達標退路。
3. 補一條決策記錄、更新 `.env` 註解（`LIVE_TR_ENDPOINT`／批次翻譯端點）。
4. 把原始譯文、分數、決策寫回配對 dev_log。

## 目前狀態
素材（`segments.json`，8 段）＋腳本（`run_eval.py`）＋評分表結構**已備**。
跑批與母語者評分待執行（需 host 模型服務在跑＋泰語母語者）。
