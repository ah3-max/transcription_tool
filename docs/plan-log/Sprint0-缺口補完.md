# 規劃：Sprint 0 缺口補完（交付外部 AI 執行）

> 建立：2026-06-26 ｜ 類型：規劃（交辦）｜ 配對開發日誌：`docs/dev_log/Sprint0-缺口補完.md`（執行者邊做邊補）
> 來源：Sprint 0（S-01/02/03）完成度稽核，5 個缺口（G1–G5）。
> 受眾：**接手執行的 AI**（無本專案對話脈絡）。請先讀「§0 必讀」再動工。

---

## §0 必讀（給執行 AI）

### 專案一句話
長照機構內部、全本地、不上雲的「語音轉文字＋即時翻譯」工具。後端 FastAPI（REST＋WS＋靜態），前端原生 HTML（v6），SQLite 索引，模型走 OpenAI 相容端點。

### 關鍵拓樸與硬約束（**務必遵守**）
- **app 跑在 Docker（純 CPU 容器）**；GPU 模型（vLLM＝Qwen3-ASR、NLLB）與 LM Studio **都在 host 原生**；app 經 `host.docker.internal` 連它們（決策 D-14）。
- ⚠️ **這是共用「生產」主機**，上面有 ~17 個別人的生產容器。**絕對不可**：裝 `nvidia-container-toolkit`、`nvidia-ctk runtime configure`、重啟 Docker daemon、或動到別人的容器/埠。app 容器不需要 GPU。
- 埠：app 本機開發 `3600`、內網測試 `3610`；模型端點不佔 3600–3699。VRAM 由 host `host-helpers/gpu_stat.py`（:3601）提供給 app（決策 D-17）。
- 硬體實測：RAM ~60 GiB、VRAM 96GB（RTX PRO 6000 Blackwell）、8 核 Xeon、磁碟 2TB。

### 必讀檔
- `CLAUDE.md`（專案守則）、`spec/`（產品/設計/開發三手冊，含 FR/NFR/SEC/D 編號）。
- `docs/plan-log/Sprint0-S01-S03.md` ＋ `docs/dev_log/Sprint0-S01-S03.md`（Sprint 0 已完成內容與決策 D-14~D-17）。

### 工作流規則（專案要求，務必照做）
1. **每項任務動工前**：先在 `docs/plan-log/` 補/確認該任務規劃，**取得使用者同意才寫程式**（「等等/接下來」是預告非執行令）。
2. **不憑記憶下結論**：動手前 `grep`/讀現況/`git status` 查證、引用真實行號。
3. **寫好 ≠ 驗過**：據實回報；改欄位/狀態 → 全鏈路同步（顯示/輸出/解析三件事）。
4. **收尾寫開發日誌**：`docs/dev_log/<同名>.md`，格式「原狀→發生→改動→困難→又改→解法」。
5. `commit` ＝一個可驗收單元、引用 S/FR/SEC/D 編號；**溝通與文件一律繁體中文**。

### 環境與基準驗證指令
```bash
cd /home/aiairdp/program/transcription_tool
docker compose up -d --build          # 起 app（純 CPU）
curl -s localhost:3600/api/health      # 應回 {"data":{"status":"ok",...}}
# 全測試（基準：目前 18 passed）
docker compose exec -T stt-app sh -c "cd /app && python -m pytest tests -q"
# VRAM 來源（host 上跑；驗 /api/resources 的 gpu 欄位才有值）
python3 host-helpers/gpu_stat.py       # 預設 :3601
```
> 註：`server/` 以 `./server:/app` bind-mount 進容器；改 Python 程式後 `docker compose restart stt-app` 即生效（**新增 pip 依賴或改 Dockerfile 才需 `--build`**）。

### 程式地圖（現況）
- `server/main.py`：app 進入點、lifespan(init_db＋每 6h 清除)、統一例外處理、掛 routers、靜態服務 web/。
- `server/config.py`：`Settings`（env 讀入；含 `max_file_min`、`max_upload_gb`、`res_cap`、`idle_release_min`、各 endpoint）。
- `server/routes/`：`jobs.py`(API-01/03/05)、`endpoints.py`(API-11)、`resources.py`(API-12)、`records.py`。
- `server/services/`：`resources.py`(RAM/儲存/VRAM＋`can_reserve`)、`routing.py`(`resolve_endpoint`)、`cleanup.py`、`translate.py`(S-05 扇出)。
- `server/storage/paths.py`：id 命名、兩區/outputs zone、防穿越。
- `server/tests/`：pytest 套件（paths/cleanup/jobs/health/endpoints/translate）。
- `host-helpers/gpu_stat.py`：host 端 GPU 用量服務。

---

## §1 任務清單（優先序）

| ID | 缺口 | 依賴 | 難度 | 可否現在做 |
|---|---|---|---|---|
| **G1** | `src_lang` 未驗證 | 無 | 易 | ✅ 現在 |
| **G2** | 模型/輔助端點對 LAN 外露（NFR-4/SEC-9） | 無（LMS 部分需使用者點頭） | 中 | ✅ 現在 |
| **G3** | 「3610 跨機可達」未驗（S-01） | 需第二台 LAN 機器 | 易 | ◑ 一半現在 |
| **G4** | SEC-2 上傳僅驗副檔名+大小；缺 MIME/解碼/時長 | S-04 前處理、需 ffmpeg | 中 | ◑ 與 S-04 一起 |
| **G5** | S-03 閒置釋放顯卡未實作（NFR-1/D-06） | S-06（vLLM 要先在 host 跑） | 中高 | ◑ 先做介面 |

**建議順序**：G1 → G2 →（G3 配合使用者）→ G4（併入 S-04）→ G5（介面先行，整合於 S-06）。
每項務必先取得使用者同意再寫碼（見 §0 規則 1）。

---

## G1　`src_lang` 驗證（S-04 / FR-13）　【可現在做・易】
**問題**：`POST /api/jobs` 的 `src_lang` 目前任意字串都收（`server/routes/jobs.py` 的 `create_jobs`，`src_lang: str = Form("zh")`，只存不驗）。
**要做**：
1. 在 `server/routes/jobs.py` 定義合法集合 `VALID_SRC`，對應 FR-13 的「國語／國語＋英文／純英文」。**先核對前端送的值**：讀 `web/index.html` 即時翻譯/批次的「辨識語言」`<select>` 的 `value`（雛形顯示為 中文／中文＋英文／純英文）。以前端實際 value 為準，建議標準碼 `{"zh","zh_en","en"}`；若前端是中文字串則兩邊同步成代碼。
2. `src_lang not in VALID_SRC` → 回 `400` 統一外型 `{"error":"bad_request","message":"辨識語言不支援"}`（用檔內既有 `_err()`）。
3. `server/tests/test_jobs.py` 補一個 case：非法 `src_lang` → 400；合法 → 202。
**驗收**：`POST /api/jobs src_lang=foo` → 400；`zh/zh_en/en` → 202。`pytest` 仍全綠。
**雷**：務必與前端 `web/index.html` 及 DB 既存值一致（改欄位→全鏈路同步）；勿只改後端造成前端送的值被擋。

---

## G2　模型/輔助端點不對 LAN 外露（S-01 / NFR-4・SEC-9）　【可現在做・中】
**問題**：`host-helpers/gpu_stat.py` 綁 `0.0.0.0:3601`、LM Studio 綁 `0.0.0.0:1234`，內網任何機器可直連；規格要求「模型端點綁 localhost、不對內網外露」。
**要做（分兩塊）**：
- **gpu_stat（我們可控，優先）**：改成只讓 **docker 橋接網段**可達、LAN 不可達。二擇一：
  - (建議) 綁 compose 網路的「橋接閘道 IP」而非 `0.0.0.0`：
    ```bash
    docker network inspect transcription_tool_default \
      -f '{{ (index .IPAM.Config 0).Gateway }}'   # 取得如 172.x.0.1
    ```
    以 `GPU_STAT_HOST=<該IP>` 啟動 `gpu_stat.py`（容器經 `host.docker.internal` 仍連得到，LAN 連不到）。把此 IP 偵測寫進啟動腳本/systemd。
  - (替代) 維持 `0.0.0.0` 但加防火牆規則（見下）。
- **LM Studio（共用服務，需使用者點頭）**：二擇一，**動工前先問使用者**：
  - LM Studio 設定關閉「Serve on Local Network」/ 綁 `127.0.0.1`；或
  - host 防火牆（`ufw`/`iptables`）限制 `tcp 1234`（及 `3601`、未來 `8000`/`8001`）**只允許來源＝docker 橋接子網 ＋ 127.0.0.1，其餘 LAN DROP**。
    ⚠️ 規則**只能**針對這幾個埠；**嚴禁**動到別人 17 個容器用的埠或全域 policy。套用前先 `ufw status`/`iptables -L` 備份、列出將加的規則給使用者確認。
**驗收**：
- 從 **LAN 另一台**（非 host、非容器）：`curl http://<hostLANip>:3601/gpu`、`:1234/v1/models` → 連線被拒/逾時。
- 從 **app 容器內**：`docker compose exec stt-app curl -s http://host.docker.internal:1234/v1/models` 與 `:3601/gpu` → 仍正常。
**雷**：共用生產主機，任何防火牆/綁定變更**先取得使用者同意**、且範圍最小化、可回滾。

---

## G3　驗證「3610 跨機可達」（S-01）　【一半現在可做】
**問題**：只在 `localhost:3600` 驗過；測試環境 3610 與「內網其他機器以 主機IP:3610 連」未驗。
**要做**：
1. 本機起測試埠：`APP_PORT=3610 docker compose up -d`（compose 已用 `${APP_PORT:-3600}:3600` 對映；確認 3610 未被占）。`curl localhost:3610/api/health` 應 200。
2. 取 host 內網 IP：`hostname -I`。
3. **跨機（需使用者/第二台機器）**：在同網段另一台開 `http://<主機內網IP>:3610/` → 應載入 v6 介面、`/api/health` 200。
4. 若連不到，檢查 **host 防火牆**是否放行 inbound `3610`（app 已綁 0.0.0.0、publish 在 host）；勿關閉整體防火牆，只放這個埠。
**驗收**：第二台 LAN 機器以 `IP:3610` 開得了介面、health 200。把結果（含實際 IP、截圖/回應）記進 dev_log。
**雷**：3600 與 3610 不要同時搶同一容器名 `stt-app`；測 3610 可用獨立 compose project 名或測完還原。

---

## G4　SEC-2 上傳深度驗證：MIME＋實際解碼＋時長（S-04 / S-13）　【併入 S-04】
**問題**：`POST /api/jobs` 目前只驗**副檔名白名單**（`storage.paths.safe_ext`）＋**累計大小** `MAX_UPLOAD_GB`。缺 MIME、實際解碼、時長上限；`config.max_file_min`（預設 120 分）**定義了但沒人用**。
**要做**：
1. app 映像加入 `ffmpeg`（含 `ffprobe`）：`server/Dockerfile` 的 apt 安裝行加 `ffmpeg`（會增肥，可接受）；需 `--build`。
2. 落檔後、入庫前，對每個檔跑 `ffprobe` 驗證：
   - 無法解碼/非音訊串流 → 回 `400 {"error":"bad_file","message":"無法解碼或非音檔"}`，並**清掉已落檔**（沿用 `jobs.py` 既有 `_cleanup()` 不留孤兒的模式）。
   - 取得時長；`> max_file_min*60` 秒 → 回 `400/413 too_long`，同樣清檔。
   - 將時長寫入（jobs 可加欄或記在 outputs/後續；sessions 已有 `duration` 欄）。
3. （可選）MIME 嗅探：`ffprobe` 解碼成功已強於 MIME；如要再加可用 `python-magic`（需 `libmagic`）。
4. 與 S-04 前處理協調：避免和 `services/preprocess.py`（DeepFilterNet3/VAD，尚未建）重複解碼；建議解碼/時長檢查放在共用的前處理入口。
5. 補測試：偽音檔(.wav 內容是文字)→400；超時長→400/413；正常音檔→202＋有時長。
**驗收**：上述三類 case 行為正確；`pytest` 全綠；`/api/jobs` 對壞檔/超時長明確 4xx（不 500）。
**雷**：解碼在容器內 CPU 跑，注意逾時保護（`ffprobe` 加 `-timeout`/`subprocess timeout`）；大量上傳時逐檔驗、失敗即停並清。

---

## G5　S-03 閒置逾時釋放顯卡、下次重載（NFR-1 / D-06）　【介面先行，整合於 S-06】
**問題**：僅 `config.idle_release_min`（預設 10 分）存在，`services/resources.py` 註記「閒置 unload 屬 host、整合待 S-06」，**零實作**。
**背景/設計**：app 在 CPU 容器內無法直接卸載 GPU；vLLM 也無原生 idle-unload。釋放 VRAM＝**停掉 host 上的模型服務程序**，下次使用前再起。需 host 端可被 app 呼叫的「模型控制」能力。已有相關規劃：commit `8f9cf22`（host systemd units、vLLM-ASR PoC），參考 `docs/dev_log/vllm-asr-poc.md`。
**要做（現在，受依賴限制）**：
1. **app 端閒置追蹤**（`server/services/resources.py`）：
   - `record_use(function)`：模型被使用時更新該 function 的 last-use 時戳（S-04/05/06 呼叫模型時呼叫它——本任務先建函式與儲存，wiring 待各 Story）。
   - `idle_minutes(function)`：回閒置分鐘數。
   - 背景檢查（main lifespan 既有迴圈可擴充）：閒置 > `idle_release_min` → 呼叫「模型控制」hook 停服務；標記該 function 為 unloaded；下次 `record_use`/起工作前先呼叫起服務並等待 ready。
2. **host 模型控制小服務 `host-helpers/model_ctl.py`**（仿 `gpu_stat.py`、純 stdlib）：
   - 提供 `start/stop/status`（包 `systemctl --user start/stop <unit>` 或程序管理）對應 vLLM/NLLB unit；綁橋接/localhost（同 G2 安全要求）。
   - app 經 `host.docker.internal:<port>` 呼叫；新增 config `MODEL_CTL_ENDPOINT`。
3. **systemd unit 範本**：把 vLLM/NLLB 定義成 host（user）service，使其可被 start/stop（與 `8f9cf22` 的 ops 文件整併，勿重複）。
**依賴/分段**：
- **現在可做且可驗**：`record_use`/`idle_minutes` 邏輯＋單元測試；`model_ctl.py` 的 `status` 可對 dummy/真 unit 回應。
- **待 S-06（vLLM 真的在 host 跑）才整合驗**：真正 stop→VRAM 降、start→重載可用；端到端「閒置 10 分自動釋放、再用自動重載」。
**驗收**：
- 現在：`idle_minutes` 隨時間遞增、超閾觸發 hook（可用假 hook 驗呼叫）；`model_ctl status` 可回服務狀態；單元測試綠。
- S-06：實機驗「閒置逾時 VRAM 釋放、下次使用重載成功」並記 dev_log。
**雷**：停/起服務牽涉 host 程序與 GPU，務必只控制本專案的 vLLM/NLLB unit，不得碰別人的服務；所有 host 端控制先取得使用者同意。

---

## §2 完成定義（DoD）與回報
- 每個 G 項：程式改動 ＋ 對應測試（能單元化的）＋ `pytest` 全綠 ＋ 該項驗收指令實跑通過 ＋ `docs/dev_log/Sprint0-缺口補完.md` 補一條（原狀→…→解法）＋ 一個引用編號的 commit。
- 依賴後續 Story 的部分（G4 的前處理整合、G5 的實機 unload）：把「現在做到哪、剩什麼、卡在哪個 Story」明確寫進 dev_log，不要假裝完成。
- 任何**動到 host（防火牆、綁定、systemd、模型服務）或共用資源**的步驟：**先取得使用者明確同意**再執行。
