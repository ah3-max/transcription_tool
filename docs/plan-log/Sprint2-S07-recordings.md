# 規劃：S-07 錄音記錄（D 軌．依賴 S-06）

> 類型：規劃（事前）｜配對開發日誌：`docs/dev_log/Sprint2-S07-recordings.md`
> 對應：FR-8~FR-10｜設計：§2.3, §5 API-07/08/09｜依賴：S-06｜被依賴：S-09（已完成）
> 並行性：**後端可與 S-06 並進**（前提：S-06 第 5 步寫入 sessions/outputs 契約先凍結）；**整合驗收須等 S-06**。

---

## 1. 現況（已查證）
- `sessions` 表 schema 就緒、**無寫入者**（寫入者＝S-06 第 5 步）。
- `outputs` 表已被 S-08/09 使用（ref_type=session、kind=transcript/translation/summary）。
- **無 `routes/sessions.py`**；前端記錄頁未接真實 API。
- `services/translate.py`（重新翻譯可復用 `translate_fanout`）、`services/postprocess.py`（摘要可復用）、`services/export.py`（下載）皆就緒。

## 2. 要做的事（從頭到尾）
1. **`routes/sessions.py`**（API-07/08/09）：
   - `GET /api/sessions`：清單（含 pagination；回 name/created_at/duration/status＋到期提示）。
   - `GET /api/sessions/{id}`：單場（逐字稿／摘要分頁資料）。
   - `POST /api/sessions/{id}/retranslate`：重新翻譯（重跑 `translate_fanout`、更新 outputs）— API-08。
   - `POST /api/sessions/{id}/summary`：按需產摘要（走 postprocess、寫 outputs(kind=summary)）— API-09。
   - 下載原始音檔：靠 DB 索引取 `audio_path`、走既有 export/串流。
2. **`main.py`** 註冊 router。
3. **前端**：app.js「錄音記錄」頁——清單、單場逐字稿/摘要分頁（摘要產生中顯示緩衝動畫）、重新翻譯鈕。

## 3. 收標準（對齊規格 S-07）
- [ ] 清單顯示名稱／時間／長度／狀態與到期提示
- [ ] 摘要首次點選顯示載入動畫後出內容
- [ ] 重新翻譯能重跑並更新產出
- [ ] pytest 覆蓋 sessions 清單／單場／retranslate／summary（可用假 session 列入庫測）

## 4. 並行/衝突
- **碰的檔**：新檔 `routes/sessions.py`；改 `main.py`（註冊 router，1 行）；`web/app.js`「錄音記錄」頁區塊。
- **與 C 軌 S-06**：
  - ✅ 後端可並行——只要 S-06 第 5 步 sessions/outputs 欄位契約先凍結，本軌即可對該 schema 開發＋用假 session 資料 pytest。
  - ⛔ 整合驗收（真的「停止錄音→記錄出現該場」）**必須等 S-06 第 5 步落地**。
- **與 B 軌 S-10**：各動 app.js 不同區塊（記錄頁 vs 全域橫幅）。
- **與 A 軌 S-12**：零交集。
