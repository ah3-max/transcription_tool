# 規劃：Sprint 0 基礎（S-01 / S-02 / S-03）

> 建立日期：2026-06-26 ｜ 類型：規劃（事前）
> 對應：開發執行手冊 §3 Sprint 0（S-01~S-03）、產品規格書 FR/NFR/SEC、設計決策手冊 §5 API／§6 資料模型
> 里程碑：**Sprint 0 完成 — 資料層與路由可運作**
> 配對開發日誌：`docs/dev_log/Sprint0-S01-S03.md`

---

### 1. 想解決什麼問題
全新專案，目前只有規格文件與 v6 UI 雛形，尚無 `server/`、`web/`、`data/`，FastAPI 未安裝（Python 3.14.4）。後面所有功能（批次轉錄 S-04、即時串流 S-06、文件生成 S-08…）都站在這層地基上。Sprint 0 要先讓系統「**能起得來、存得住、連得上模型**」。

### 2. 要收斂的目標（驗收標準）
**Sprint 0 里程碑：資料層與路由可運作。** 具體為三條 curl 可成功：
- 建立工作 `POST /api/jobs`
- 查清單 `GET /api/jobs`
- 設定端點 `POST/GET/DELETE /api/endpoints`

外加 S-01/02/03 各自的驗收清單（見第 5 節）全過。

### 3. 要怎麼改、為什麼這樣

**S-01 專案骨架與內網綁定**
- 怎麼改：建 FastAPI app（`server/main.py`）；`/api/health` 健康檢查；綁 `0.0.0.0` + `APP_PORT`；`StaticFiles` 靜態服務 `web/`（先把 v6 HTML 放成 `web/index.html`）；統一以 helper 產生 `{data, error?, message?}` 回應外型。
- 為什麼：手冊 §1.1 指定 Python+FastAPI 一套供 REST+WS+靜態，單語言棧好維護（NFR-7）；綁 `0.0.0.0` 才能讓內網其他機器連得到，但模型端點留 localhost 不外露（NFR-4、SEC-9）；同源相對路徑 `/api`、`/ws` 免烤 base URL（D-11）。

**S-02 兩區儲存 + SQLite + 清除排程**
- 怎麼改：`server/models_db/` 建 SQLite schema（jobs / sessions / outputs / endpoints 四表＋索引，依設計 §6.1）；`server/storage/` 做兩區（uploads / recordings）路徑管理，檔名一律「**伺服器產生 id + 副檔名**」，用 `realpath` 正規化後檢查必須落在 `DATA_DIR` 內；7 天到期排程（背景任務掃 `expire_at`，刪檔＋刪索引）。
- 為什麼：以 id 命名＋SQLite 索引可避免撞名與路徑穿越（D-07、SEC-3）；原檔名只存 DB 供顯示、永不進路徑；7 天清除對應 NFR-3、SEC-7。

**S-03 模型路由 + 資源動態管理**
- 怎麼改：endpoints CRUD（API-11，function ∈ asr / batch_tr / live_tr / post，active 旗標）；OpenAI 相容 client（httpx）；資源管理模組 `server/services/resources.py`：啟動工作→查可用量（RAM／儲存用 psutil 實量、VRAM 有 pynvml 就量）→reserve 不超過 `RES_CAP`(80%)→閒置 `IDLE_RELEASE_MIN` 分鐘 unload；取不到資源回 503 並標記需降級。
- 為什麼：動態 reserve＋閒置釋放對共用 VM 友善（D-06、NFR-1）；上限納管 VRAM+RAM+儲存，RAM 是相對小的池要防耗盡（SEC-5）；解耦路由讓翻譯/主 LLM 各自切端點（FR-21/22、D-03）。

### 4. 範圍邊界（這次做 / 不做）
- **做**：S-01~03 的骨架、四表資料層、兩區儲存與清除、端點 CRUD、資源管理結構與本機量測。
- **不做（留後續 Story）**：真正 ASR 處理（S-04）、批次/即時翻譯（S-05/06）、文件生成（S-08）、前端完整拆檔串接（S-11，本次只把 v6 HTML 服出去）。
- **本次驗不到、需端點起來才整合驗**：S-03「對真實 vLLM 設 `gpu_memory_utilization`」「實際 unload 顯卡」——先把邏輯/介面做成可單測，整合驗證列為後續。

### 5. 驗收檢查清單（對齊手冊，完成逐項打勾）
**S-01**
- [ ] 測試環境 3610 內網其他機器以「主機IP:3610」可達；模型端點綁 localhost、不對內網外露
- [x] `/api/health` 回 200；開根網址載入 v6 介面 ✅（2026-06-26 驗證）
- [ ] 前端以相對路徑 `/api`、`/ws`（無寫死 host）

**S-02**
- [x] 四表建立、索引正確 ✅（endpoints/jobs/outputs/sessions＋索引）
- [x] 寫入檔案落正確 zone、路徑不含原檔名 ✅（機制：`build_path` id＋副檔名；實際上傳落檔於 S-04 整合）
- [x] `../` 等路徑被擋 ✅（realpath＋commonpath；3 惡意輸入全擋）
- [x] 到期工作連檔帶記錄被清除 ✅（`sweep_expired` 刪檔＋刪列）

**S-03**
- [ ] 可新增/停用端點、切換某功能目標端點
- [ ] 啟動工作只取定額、不超 80% 上限
- [ ] 閒置逾時自動釋放、下次重載（邏輯；整合待端點）
- [ ] 取不到資源回 503 並標記需降級

**里程碑**
- [ ] 三條 curl（建立工作 / 查清單 / 設定端點）皆通

### 6. 決策與待確認（2026-06-26 本 session 更新／定案）
- **執行環境改為 app 進 Docker（`python:3.12-slim` 容器），不建 `server/.venv`。** 因：① 預設 `python3`=3.14、torch/vLLM 等 ML wheel 尚未跟上 → app 用 3.12；② 本機為共用生產主機、已跑 ~17 個別人的生產容器且 `nvidia-container-toolkit` 未裝 → app 純 CPU 容器、不碰 Docker daemon、對生產服務零風險。（對應新增決策 D-14／D-15）
- **模型執行器定案**：GPU 模型 vLLM(Qwen3-ASR)／NLLB 留 **host 原生、預設不啟動**（按需起＋閒置釋放）；文字 LLM **沿用現成 LM Studio**（gemma-4-31b @ :1234）；**Ollama 不採用**。app 經 `host.docker.internal` 連這些 host 端點。
- **spec 檔已搬入 `spec/`**（原待確認 → 完成）。
- **Python**：app 容器內 3.12；host 上 vLLM/NLLB 之 venv 用 3.12（留待 S-06 前「vLLM-on-Blackwell PoC」）。
- 開發日誌格式：規劃與日誌分置 `docs/plan-log/`、`docs/dev_log/`，每個工作單元在兩夾各一份同名檔（本檔為 plan-log）。
- **待確認（安全）**：LM Studio 綁 `0.0.0.0:1234`（LAN 可直連），與「模型端點綁 localhost、不對內網外露」(NFR-4／SEC-9) 有出入；因 LMS 為共用主機既有服務、不擅改其綁定。建議 ①改綁 127.0.0.1 或 ②防火牆擋 :1234 對外——待你決定。

### 7. 部署拓樸與未來試行（兩階段，本 session 規劃）
**拓樸**：app 進 Docker（純 CPU）；vLLM(Qwen3-ASR)／NLLB／LM Studio 皆 host 原生；app 經 `host.docker.internal` 連 :8000／:8001／:1234。不裝 nvidia-container-toolkit、不重啟 Docker daemon → 對同主機 ~17 個生產容器零影響。
- **Stage 1 內網測試（3610）**：app stack ＋ LMS（＋就緒後的 vLLM/NLLB）；7 天保留；只綁內網。先把 S-01~S-11 主流程跑順。
- **Stage 2 長照現場實測**：補 SEC-1~10 加固、音檔加密落地、去識別化與最小留存、多人化前才導入登入；中→泰品質實測（S-12）。
- **S-06 即時功能前硬性關卡**：vLLM-on-Blackwell PoC（PyTorch cu128/130＋新版 vLLM 跑 Qwen3-ASR，驗 sm_120 kernel 載得起、串流可用）。
- 完整計畫備份於 `~/.claude/plans/`（隱藏）；本檔為 repo 可見之正本。
