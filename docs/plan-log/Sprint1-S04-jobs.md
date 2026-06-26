# 規劃：Sprint 0 收尾接線 ＋ S-04 jobs 骨架（API-01/03/05）

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/Sprint1-S04-jobs.md`
> 對應：S-03（路由解析／reserve／503 接線）、S-04 API-01/03/05；補齊 Sprint 0 里程碑三條 curl

## 1. 想解決什麼問題
使用者指出 S-03 的「reserve／路由解析／503 接線」只有零件、未接線（先前誤標完成）。需用**實際消費者（建立工作）**把它們接起來；同時 Sprint 0 里程碑要求的「建立工作／查清單」其實是 S-04 的 `/api/jobs`，尚未做。本段把兩者一起完成，讓三條 curl（建立工作／查清單／設定端點）整條通。

## 2. 目標（驗收）
- `POST /api/jobs`（multipart）：多檔→副檔名白名單→**`can_reserve` 守門（不過回 503＋needs degrade）**→以伺服器 id 落檔（uploads）→建 job 列（status=queued）→202。
- `GET /api/jobs`（清單＋pagination）、`GET /api/jobs/{id}`（含進度欄位 stub）、`DELETE /api/jobs/{id}`（API-05）。
- **路由解析** `resolve_endpoint(function)` 可回該功能 active 端點（FR-21）。
- 里程碑三條 curl 全通。

## 3. 怎麼改、為什麼
- `services/routing.py`：`resolve_endpoint(function)` → 該 function 的 active 端點（FR-21 路由解析；S-04 處理時用來決定打哪個 ASR/翻譯端點）。
- `routes/jobs.py`：API-01/03/05；**reserve→503 接線**（SEC-5／NFR-2，503 用 `error:"resource"` 符合 API-01 規格）；落檔走 `storage.paths`（id 命名、防穿越，D-07／SEC-3）；副檔名白名單（SEC-2 之一部）。
- `main.py`：掛上 jobs router。

## 4. 範圍邊界（做 / 不做）
- **做**：jobs 建立／查／刪骨架、路由解析、reserve＋503 接線、上傳落檔（id 命名）。
- **不做（S-04 其餘／後續）**：真正前處理（DeepFilterNet/VAD）、切段、ASR 轉錄、翻譯（S-05）；MIME＋實際解碼＋時長上限（SEC-2 完整版留 S-04/S-13）；進度真值（先給 stub）。status 停在 `queued`。

## 5. 驗收檢查清單（2026-06-26 全數驗證通過）
- [x] `POST /api/jobs` 上傳 .wav → 202、job 列建立（queued）、檔案落 uploads（id 命名 `3c30fc83dc88.wav`）
- [x] 非白名單副檔名（如 .txt）→ 400 `bad_file`
- [x] `GET /api/jobs` 回清單＋pagination；`GET /api/jobs/{id}` 回單筆＋progress
- [x] `resolve_endpoint('asr')` 能取到 active 的 asr 端點
- [x] 資源不足（模擬 RES_CAP=0）→ `POST /api/jobs` 回 503 `error:"resource"`、標記 degrade
- [x] 里程碑：建立工作／查清單／設定端點 三條 curl 皆通

## 6. 開發日誌
> 見 `docs/dev_log/Sprint1-S04-jobs.md`
