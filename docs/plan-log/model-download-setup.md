# 規劃：模型下載與啟動準備（含 SOP、開機自啟）

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/model-download-setup.md`
> 對應：D-04 / D-13 / D-14 / D-15 / D-16 / D-17、SEC-1、`.env`；產出 `docs/model-setup-SOP.md`

## 1. 想解決什麼問題
使用者要實際開始下載模型，需先釐清：要載哪些、載完放哪、各交給哪個軟體/埠；NLLB 是模型還是服務、要不要 Docker/隔離；以及「開機自啟」怎麼做。本段把這些定清楚並備妥下載與啟動文件。

## 2. 目標（驗收）
- 盤點現況：哪些已就緒、哪些要下載；給出體積、放置位置、服務對應。
- 下載必載模型到 host HF 快取（vLLM/transformers 以 repo id 找得到）。
- 產出可操作的《模型下載與啟動 SOP》。
- 回答 venv／開機自啟，備妥 systemd user 服務範本。

## 3. 怎麼做、為什麼
- 下載器用 `uv` 建 py3.12 venv（D-15：系統 py3.14 ML 斷層、又被 PEP668 擋），只裝純 Python 的 `huggingface_hub`。
- 模型分工（沿用既有決策）：Gemma 31B Q8→LM Studio:1234（已就緒）；Qwen3-ASR→vLLM:8000；NLLB→自寫服務:8001；前處理（DFN3/Silero）→app 容器內 CPU 自動下載。
- GPU 服務一律 host 原生（D-14，不碰 nvidia-container-toolkit／daemon），以 **per-service venv 隔離**（D-15），不是 Docker。
- 開機自啟：venv 無此能力，靠 systemd；本機 Linger=yes，user 服務免 sudo。依 D-06，只有輕量且被 app 依賴的 `gpu_stat` 建議常駐自啟；GPU 模型按需起。

## 4. 範圍邊界（做 / 不做）
- **做**：下載 Qwen3-ASR-1.7B（4.7GB）＋ NLLB-200-3.3B（17.6GB）；寫 SOP；systemd 範本（gpu-stat／nllb）。
- **泰文模型（已定案，2026-06-26）**：使用者指名 **MADLAD-400 ＋ Typhoon**，非 TranslateGemma。下載 **MADLAD-400 7b-mt-bt**（中→泰直譯，T5/450 語，~35GB）＋ **Typhoon Translate 4B**（英↔泰；GGUF 入 LM Studio＋safetensors）。分工：中→泰直譯走 MADLAD（同 NLLB 型），Typhoon 僅英↔泰／參照（不入中→泰主流程，守 D-03）。TranslateGemma（gated/54.9GB）未選用。
- **不做（他人/後續）**：**vLLM-on-Blackwell PoC（D-16）由他人負責**；NLLB 服務程式與 CT2 量化（SOP 給雛形，正式實作另案）；前處理套件落地（屬 app 容器 S-04/S-05）。

## 5. 開發日誌
> 見 `docs/dev_log/model-download-setup.md`
