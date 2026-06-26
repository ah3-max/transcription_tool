# 語音轉文字與即時翻譯工具（stt-translate）

長照機構內部、全本地（內網、不上雲、Phase 1 無登入）的語音轉文字＋即時翻譯工具。

## 開發守則（遵循全域 CLAUDE.md，不在此重述）
通用開發紀律以全域 `~/.claude/CLAUDE.md` 為準、務必遵守；本檔僅補充專案專屬內容：
- 先規劃、取得明確同意才寫檔；「等等／接下來」是預告非執行令；只做當前宣告範圍。
- 不憑記憶／快照下結論，動手前先 grep／讀現況／`git status` 查證、引用真實行號。
- 「寫好 ≠ 驗過」據實回報；改欄位／狀態／資料模型 → 全鏈路同步（顯示／輸出／解析是三件事）。
- 收尾寫開發紀錄；commit ＝一個可驗收單元、引用 FR/S/D 編號；溝通與文件一律繁中。

> 遇本地 LLM／環境變數／競態／時區等問題，另查獨立的 `local-ai-dev-traps` skill（不在本檔，僅指路）。

## Commands
```bash
# 應用本體（FastAPI 同時提供 UI＋API＋WebSocket）
cd server && pip install -r requirements.txt
uvicorn main:app --host $BIND_HOST --port 3600 --reload   # 開發；正式拿掉 --reload
pytest                                                    # 測試
# 前端為原生 HTML/CSS/JS，由 FastAPI 靜態服務，無 build 步驟
# 模型由 LM Studio／vLLM／提供商 pod 各自服務（自有埠，如 vLLM:8000、LMS:1234、或 pod URL）；本 app 以端點位址連它們
```

## Stack
- 後端：Python + FastAPI（REST 批次 + WebSocket 即時）
- 前端：**原生 HTML/CSS/JS**（直接沿用 v6 愛愛院版的版面與 token），由 FastAPI 靜態服務；不導入 Vue/React/Vite
- DB：SQLite（jobs / sessions / outputs / endpoints）
- 模型服務：OpenAI 相容端點
  - ASR：Qwen3-ASR 1.7B → **即時串流必須 vLLM**；批次可 transformers 或 vLLM；單段 ≤20min、串流不回時間戳。**LM Studio 不支援 ASR**
  - 文字 LLM（Gemma 4 翻譯／後處理）：LM Studio／vLLM／Ollama／提供商 pod 皆可（各自埠）
  - 即時翻譯：NLLB-3.3B｜批次翻譯：Gemma 4 31B Q8 / TranslateGemma 27B
  - 後處理／摘要／文件：Gemma 4 31B Q8（≈33GB）
  - 前處理：DeepFilterNet3 + Silero VAD
- 文件產出：python-docx；輸出僅 docx / md / txt（**不做 PDF**）
- 認證：Phase 1 無（僅內網綁定）

## Structure
```
server/   main.py routes/ ws/ services/(asr,preprocess,translate,postprocess,export,resources)
          models_db/ storage/ middleware/ config.py
web/      index.html  styles/tokens.css  app.js（原生 JS 串接 API）  i18n.js（zh/en/th 字典）  assets/
data/     uploads/ recordings/   # 執行期資料，不進版控
spec/     產品規格書 / 設計決策手冊 / 開發執行手冊
```

## Architecture
批次走 REST、即時走 WebSocket，同一套 FastAPI。模型以可路由的 OpenAI 相容端點掛載；翻譯與主 LLM 解耦，中文來源對多目標語言「一對多扇出」獨立翻譯（**不串接**）。檔案存兩區（uploads／recordings）＋SQLite 索引，靠索引找檔、不靠路徑。

## Conventions
- REST 前綴 `/api`，即時 `/ws`；回應外型 `{ data, error?, message? }`（清單含 `pagination`）。
- 檔案一律以**伺服器產生的 id** 命名與組路徑；原檔名只存 DB 供顯示，**永不進入檔案系統路徑**（防穿越）。
- 介面 i18n：框架字串多語（zh/en/th），使用者內容不自動翻譯。
- 無障礙（優先生效）：內文 ≥19–20px、行高 1.8、可點元件 ≥48×48px、對比 AA。
- 本專案用 3600–3699：應用本體（前端＋API＋WS）綁 `0.0.0.0` 對內網——**本機開發 3600、內網測試環境 3610**，使用者連「主機內網 IP:3610」；**其餘 3601–3699（除 3610）** 保留自有後端。模型端點**不在此範圍**，指向 LMS／vLLM／pod 各自位址（建議綁 localhost 不外露）。
- 前端同源，API 走相對路徑 `/api`、WebSocket 走 `/ws`（免烤 base URL，無 Vite 重建問題）。
- 敏感資料不放 URL query。

## Environment Variables
```
DATA_DIR=/data            # 必填，資料根
DB_PATH=/data/index.db    # 必填
APP_PORT=3600                           # 應用本體（UI＋API＋WS）；本機開發 3600、內網測試環境 3610
BIND_HOST=0.0.0.0                       # 綁 0.0.0.0 對內網（測試環境使用者連 主機內網IP:3610）
# 3601–3699 保留給本專案其他後端元件；模型端點不佔此範圍，依執行器實際埠設定
ASR_ENDPOINT=http://localhost:8000/v1   # Qwen3-ASR：必須 vLLM 或支援 ASR 的 pod
LLM_ENDPOINT=http://localhost:1234/v1   # Gemma 4：LM Studio／vLLM／pod（依執行器埠）
LIVE_TR_ENDPOINT=http://localhost:8001  # NLLB（依執行器埠）
RETENTION_DAYS=7                       # 保留天數
MAX_FILE_MIN=120                       # 單檔時長上限（分）
RES_CAP=0.8                            # 動態資源上限比例（含 VRAM/RAM/儲存）
IDLE_RELEASE_MIN=10                    # 閒置釋放顯卡（分）
```

## Spec Files
完整規格在 `spec/`，開工任一 Story 前先讀對應章節，commit 註明 FR-xxx / S-xxx：
- `spec-語音轉文字-產品規格書.md` — 需求、角色、情境、資安需求
- `spec-語音轉文字-設計決策手冊.md` — 線框稿、互動狀態、API、資料模型、token、決策記錄
- `spec-語音轉文字-開發執行手冊.md` — Stories、Sprint、測試與資安檢核、部署

## Key Decisions
- 翻譯：一對多扇出、與主 LLM 解耦 — 多語平行、避免串接累積誤差（D-03）
- 資源：動態 reserve＋閒置釋放，上限含 VRAM/RAM/儲存 — 共用 VM 友善（D-06）
- 檔案：SQLite 索引＋id 命名 — 找得到、避免撞名與路徑穿越（D-07）
- 輸出：僅 docx/md/txt — PDF 轉檔不穩（D-05）
- UI：愛愛院版 v6 為唯一定稿，現行 teal 版停用（D-01）
- 前端：**直接用原生 HTML（不導框架）** — 內部工具、單人維護、雛形已含 i18n/主題/無障礙；同源相對路徑免烤 API URL（D-11）
- 連線／埠：本專案用 3600–3699（前端 3600、其他後端 3601+）、綁 0.0.0.0 對內網；模型由 LMS／vLLM／pod 各自埠服務、不佔此範圍。ASR 即時串流必須 vLLM（LMS 不支援 ASR）（D-12）
- 部署：app 進 Docker（純 CPU、不裝 nvidia-container-toolkit、不重啟 daemon → 對共用主機其他容器零影響）；GPU 模型(vLLM/NLLB)＋LM Studio 留 host 原生、app 經 `host.docker.internal` 連（見 `.env.example`）；app 用 Python 3.12；Ollama 不採用（D-14/D-15）
- 規劃與開發日誌寫進 repo：規劃放 `docs/plan-log/`、日誌放 `docs/dev_log/`（每個工作單元兩夾各一份同名檔、互相 cross-ref），讓使用者本機與 GitHub 可見，不只留在 `~/.claude/plans/`

## 本專案其他雷
- RAM 約 60 GiB（64GB 級；原「32GB」為升級前舊值，2026-06-26 實測已升）、VRAM 96GB 充裕；為共用 VM、RAM 仍是相對較小的池，單檔／佇列設上限防耗盡。
- Qwen3-ASR 串流不回時間戳，時間以伺服器時鐘標記；批次每 15 分鐘切段、單段 ≤20 分鐘。
- 後處理 LLM 會遵循指令：逐字稿／使用者文字一律當「資料」與系統指令分離（防提示注入）。
- 不支援台語；護理交班範本欄位（OQ-3）未定案，先用暫定欄位並標記可調。
