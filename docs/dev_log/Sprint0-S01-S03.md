# 開發日誌：Sprint 0 基礎（S-01 / S-02 / S-03）

> 類型：開發日誌（事中／事後，逐步追加）
> 配對規劃：`docs/plan-log/Sprint0-S01-S03.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**① 2026-06-26｜地基 + S-01 骨架（app-in-Docker）**
- 原本：全新專案、無 `server/`／`web/`；Sprint 0 原規劃擬用 `server/.venv`（host 原生）跑 FastAPI。
- 發生：釐清執行環境時發現 ① 預設 `python3`=3.14（ML wheel 斷層）；② 本機是共用生產主機、已跑 ~17 個別人的生產容器，且 `nvidia-container-toolkit` 未裝（GPU 進不了容器，且 `nvidia-ctk runtime configure` 會重啟 daemon 波及他人）。
- 改了什麼（經使用者核准）：① `git init`(main)＋`.gitignore`；② 建 `server/`(`main.py`／`config.py`／子套件)、`web/`、`spec/`、`data/` 骨架，規格三份移入 `spec/`、v6 複製成 `web/index.html`；③ `server/Dockerfile`(python:3.12-slim、純 CPU)、`docker-compose.yml`、`.env.example`／`.env`；S-01 程式：`/api/health` 回 `{data:{status:"ok"}}`、統一回應外型 helper、`StaticFiles` 同源服務 `web/`。
- 遇到困難：app 在容器、模型(vLLM/NLLB/LMS)在 host → 容器要連得到 host 服務。
- 又怎麼改：`docker-compose.yml` 加 `extra_hosts: ["host.docker.internal:host-gateway"]`，端點一律走 `host.docker.internal`。
- 最後如何解決：使用者指示「依合理順序開發」後恢復——補 `.dockerignore`→`docker compose build`（鎖版實得 fastapi 0.138.1／uvicorn 0.49.0／pydantic 2.13.4／python-docx 1.2.0 等）→`up -d`。**S-01 驗證通過**：`/api/health`→200 `{data:{status:"ok",app:"stt-translate",version:"0.1.0"}}`；根網址載入 v6（`<title>…愛愛院版 v6</title>`）；容器經 `host.docker.internal:1234` 取得 LMS 模型清單；容器 `(healthy)`、`RestartCount=0`；其餘 ~17 生產容器不受影響（總數 18）；本機內網 IP `192.168.1.216`。註：啟動瞬間曾遇 docker-proxy 早於 uvicorn 接受連線致 curl `reset`，加 `--retry-all-errors` 重試即正常。
- 待續：S-01 的「3610 跨機可達」需於 LAN 端確認；前端相對路徑 `/api`、`/ws` 串接屬 S-11。接著進 **S-02**（四表 + 兩區儲存 + 清除排程）。

**② 2026-06-26｜S-02 兩區儲存 + SQLite 四表 + 清除排程**
- 原本：S-01 後只有 health 與靜態服務，無資料層、無儲存、無清除。
- 改了什麼：① `models_db/db.py` 建 jobs/sessions/outputs/endpoints 四表＋索引（設計 §6.1），`init_db()` 於 lifespan 啟動時冪等建表；② `storage/paths.py` 兩區(uploads/recordings)、檔名＝伺服器 id＋副檔名、`realpath`＋`commonpath` 限制在 zone 內、副檔名白名單；③ `services/cleanup.py` 依 `expire_at` 掃 jobs/sessions、連帶刪 outputs 檔與列；main.py lifespan 起每 6 小時背景清除；compose 掛 `./server:/app`（開發免 rebuild）。
- 遇到困難：驗證腳本最後一行用 `db().__enter__()` 取連線，context manager 被即時回收→連線關閉→`Cannot operate on a closed database`。
- 又怎麼改：改用正規 `with db() as c:` 重驗。
- 最後如何解決：**S-02 驗證通過**——四表建立；路徑穿越三案（`../../etc/passwd`、非法副檔名、未知 zone）全擋；插入到期 job→`sweep_expired` 刪檔＋刪列（jobs 1→0、uploads 清空）；`index.db` 落在 `/data`。
- 待續／提醒：實際上傳落檔屬 S-04。**S-03（端點 CRUD＋資源管理）有設計變更**：app 在 CPU 容器內**無法直接量 VRAM**（pynvml 需 GPU），原規劃的 in-process 量測不可行；VRAM 量測須改走 host 途徑，動工前先與使用者確認方案（見下次規劃）。
