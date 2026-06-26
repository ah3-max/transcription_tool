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
