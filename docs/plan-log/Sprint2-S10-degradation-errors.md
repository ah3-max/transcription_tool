# 規劃：S-10 降級與錯誤處理（B 軌．近獨立）

> 類型：規劃（事前）｜配對開發日誌：`docs/dev_log/Sprint2-S10-degradation-errors.md`
> 對應：NFR-2, SEC-5｜設計：§3.1 降級｜依賴：S-03（已完成）、S-06（介面約定，非阻塞）
> 並行性：**近獨立**——後端只加 1 個資源探測點、前端自成「全域橫幅＋toast」一塊。與 S-06 只靠**一條降級訊號約定**耦合。

---

## 1. 現況（已查證）
- `server/services/resources.py` 有 `can_reserve()`／`RES_CAP`，可判資源是否足夠。
- 前端尚無統一降級橫幅與錯誤 toast 框架（現散落 alert）。
- 設計手冊 §3.1：資源不足以即時翻譯 → 橫幅「目前資源不足，已切換為手動錄音」、停即時、引導手動錄音。

## 2. 要做的事（從頭到尾）
1. **後端資源探測點**：加 `GET /api/resources/live-readiness`（或復用 resources 端點），回「即時翻譯可否起」布林＋原因（VRAM/RAM 不足、`live_tr`/`asr` 端點未 active）。
2. **降級訊號介面約定**（與 C 軌 S-06 的接口，**先凍結**）：
   - WS 連線前先查 readiness；
   - 連線中資源掉線 → 下行 `{"type":"degraded","reason":"..."}`。
   - 此約定凍結後 C 軌照做即可。
3. **前端降級橫幅**：app.js 收到 not-ready／degraded → 顯示橫幅、停即時 UI、引導改手動錄音上傳（接 S-04 批次）。
4. **統一錯誤呈現**：封裝 `showToast(error)` ＋表單欄位錯誤樣式，把各 API 的 `{error,message}` 統一渲染（取代散落 alert），三語 i18n。

## 3. 收標準（對齊規格 S-10）
- [ ] 模擬資源不足（monkeypatch `can_reserve`→false／停 live_tr 端點）→ 前端出現降級橫幅且即時服務停止
- [ ] 各類錯誤（400/413/503/WS 斷線）皆有對應、可理解的中文提示（zh/en/th）
- [ ] pytest 覆蓋 readiness 端點「足/不足」兩路

## 4. 並行/衝突
- **碰的檔**：後端新增端點（routes/resources.py 或新檔，不撞）；前端 `web/app.js` 的「全域橫幅＋toast」區塊。
- **可同時**：A 軌（零交集）、C 軌（只靠降級訊號約定，且各動 app.js 不同區塊——須協調但不阻塞）。
- **須先做的價值**：第 2 步降級訊號約定是 C 軌 S-06 的依賴介面，**先凍結它可解 C 軌依賴**，故建議與 A 軌一起先行。
- **app.js 共用注意**：B（全域橫幅/toast）、C（即時頁）、D（記錄頁）動不同區塊；同一時間多軌動 app.js 時以「區塊不重疊」為界、避免合併衝突。

---

## 5. 降級訊號介面約定（**已凍結 2026-06-26**——C 軌 S-06 照此實作）
1. **連線前守門**：WS `/ws/live` 建立前（或 onopen 後第一步），後端呼叫 `services.resources.live_readiness()`：
   - `ready=False` → 不開即時、回 readiness 結果（含 `reasons`），前端顯示降級橫幅；
   - 前端亦可先打 `GET /api/resources/live-readiness` 預判（已實作）。
2. **連線中掉線**：S-06 在串流過程偵測資源掉線／端點失聯時，下行一筆
   `{"type":"degraded","reason":"<code>"}`，其中 `<code>` ∈ `live_readiness()` 的 reasons 代碼集
   （`ram`/`storage`/`asr_endpoint`/`live_tr_endpoint`）或 `disconnected`。
3. **前端對應**：app.js 已備 `setLiveDegraded(reasons)`／`degrade.<code>` 三語字串；S-06 收到 `degraded`
   下行時呼叫之並停止即時 UI（`degrade.disconnected` 字串已備）。
4. **reasons 代碼為唯一真實來源**：新增降級原因時，同步加 `services.resources.live_readiness()` 代碼
   ＋ `web/i18n.js` 的 `degrade.<code>` 三語，避免顯示/邏輯脫鉤。
