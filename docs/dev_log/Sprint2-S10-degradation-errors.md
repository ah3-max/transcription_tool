# 開發日誌：S-10 降級與錯誤處理（B 軌）

> 類型：開發日誌（事中／事後，逐步追加）｜配對規劃：`docs/plan-log/Sprint2-S10-degradation-errors.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**狀態：完成**（2026-06-26，B 軌；降級訊號約定已凍結交 C 軌 S-06）

<!-- 每完成一步 append 一段：原本→發生→改了→困難→又怎麼改→最後如何解決 -->

## 2026-06-26　S-10 實作

**原本怎麼樣**
- 後端只有 `GET /api/resources`（FR-24 用量快照），無「即時能否起」的就緒判斷。
- 前端錯誤散落 `alert`（download 失敗、端點 CRUD 失敗），無統一降級橫幅；即時頁無資源守門。
- WS（S-06）尚未實作，`server/ws/` 為空。

**發生什麼／要做什麼**
- 按規劃做 readiness 端點＋前端降級橫幅＋統一 toast＋凍結給 S-06 的降級訊號約定。

**改了什麼**
- 後端
  - `server/services/resources.py`：新增 `live_readiness()`，整合 `can_reserve()`（RAM/儲存達 RES_CAP）
    與 `resolve_endpoint("asr")`／`resolve_endpoint("live_tr")`（端點是否 active），回
    `{ready, reasons[], detail}`；reasons 代碼 `ram`/`storage`/`asr_endpoint`/`live_tr_endpoint`。
    放 service 而非 route，供 S-06 WS 連線前直接復用。
  - `server/routes/resources.py`：新增 `GET /api/resources/live-readiness`。
- 前端
  - `web/index.html`：即時頁加降級橫幅 `#liveBanner`（含原因＋「改用手動錄音上傳」鈕）；body 末加 `#toastWrap`。
  - `web/styles/tokens.css`：`.degrade-banner`／`.toast` 樣式（含深色、淡入動畫、AA 對比）。
  - `web/app.js`：新增 `showToast(msg,kind)` 取代 3 處散落 `alert`；新增 `checkLiveReadiness()`／
    `setLiveDegraded(reasons)`，於 `show('live')`＋init 開頁即查、不足則停 startStream 並顯示橫幅、
    「改用手動錄音」鈕導到批次頁；startStream 點擊再加一道 `liveReady` 守門。
  - `web/i18n.js`：`degrade.*`（title/toBatch/四個 reason 代碼/disconnected）三語字串。
- 約定凍結：`docs/plan-log/Sprint2-S10-degradation-errors.md` §5 寫死降級訊號介面，交 C 軌 S-06。
- 測試：`server/tests/test_resources.py` 三案——無端點→not ready、端點齊備＋資源足→ready、
  資源超上限→not ready（monkeypatch `can_reserve`）。

**遇到什麼困難／又怎麼改**
- 本機無 `python`／`pytest`，專案虛擬環境在 `/tmp/ttenv`；改用 `/tmp/ttenv/bin/pytest` 跑。
- 全測有 10 筆 `test_jobs.py` 失敗（503／NoneType）；`git stash` 我的改動後同樣失敗 →
  確認屬環境缺 ffmpeg/ffprobe 的既存問題，非本次回歸。

**最後如何解決**
- 新增 3 案 + 既有 `test_endpoints.py` 全綠；`test_resources.py` 足/不足兩路覆蓋達收標準。
- 收標準對照：readiness 端點足/不足兩路（pytest ✓）；前端模擬不足出現降級橫幅且停即時（程式路徑 ✓，
  待 S-06 起後接 WS degraded 下行端到端驗）；各類錯誤統一 toast 三語（✓）。
