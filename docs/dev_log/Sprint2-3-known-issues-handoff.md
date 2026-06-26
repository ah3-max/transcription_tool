# 交接：S-08／S-09／S-11 已知問題與 404 排查（review 後彙整）

> 建立：2026-06-26 ｜ 類型：交接／已知問題（事後 review）｜ 撰寫者：審查 S-08/09/11 時彙整
> 配對日誌：[`Sprint2-S08-doc-generation`](Sprint2-S08-doc-generation.md)、[`Sprint2-S09-export-history`](Sprint2-S09-export-history.md)、[`Sprint3-S11-frontend`](Sprint3-S11-frontend.md)
> 目的：把「歷史匯出 404」與 review 期間實測到的相關 bug／坑寫清楚，讓接手者照著修。
>
> **更新（2026-06-26）**：A–G 已全數修復，見 [`Sprint2-3-known-issues-fix`](Sprint2-3-known-issues-fix.md)（H 因 S-04 已 commit `60713b8` 而自然解除）。下表狀態已同步。後端 pytest 52 passed；前端待人工起站驗證。

---

## 0. 怎麼把環境跑起來（接手前先看）

本機 host **沒有** `python`/`ffprobe`，各 venv 也沒裝 `python-docx`。要跑測試或起站，用下面方式做一個乾淨環境：

```bash
# 1) 建 venv 並裝相依（uv 有快取，離線可裝）
uv venv /tmp/ttenv
uv pip install --python /tmp/ttenv/bin/python -r server/requirements.txt

# 2) 測試需要 ffprobe（見問題 C）。容器內 Dockerfile 已裝 ffmpeg；
#    本機若無，放一支假 ffprobe 到 PATH 即可跑完整套件：
mkdir -p /tmp/fakebin
cat > /tmp/fakebin/ffprobe <<'SH'
#!/usr/bin/env bash
path="${@: -1}"
if head -c4 "$path" 2>/dev/null | grep -q "RIFF"; then
  echo '{"streams":[{"codec_type":"audio","duration":"1.0"}],"format":{"duration":"1.0"}}'; exit 0
fi
exit 1
SH
chmod +x /tmp/fakebin/ffprobe

# 3) 跑測試（在 server/ 底下）
cd server && PATH="/tmp/fakebin:$PATH" /tmp/ttenv/bin/python -m pytest -q
# → 預期 45 passed（少了 ffprobe 會有 9 紅，全是音檔深驗相關，見問題 C）
```

起站做手動驗證：

```bash
cd server
DATA_DIR=/tmp/appdata DB_PATH=/tmp/appdata/index.db WEB_DIR=$(pwd)/../web \
  PATH="/tmp/fakebin:$PATH" \
  /tmp/ttenv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 3677
```

---

## 1. 問題總覽

| # | 嚴重度 | 標題 | 區域 | 狀態 |
|---|---|---|---|---|
| **A** | **高** | 歷史「匯出」鈕一律 404（且未來語言/類型會錯配） | 前端 S-11 ＋ API-04 | ✅ 已修 |
| **B** | 中高 | 沒有「列出歷史記錄」的 API，手動生成的文件重整頁面後就找不回 | S-08/S-09 | ✅ 已修 |
| C | 中 | 非容器環境缺 `ffprobe` → 上傳直接 500、測試 9 紅 | S-04（並行）影響全鏈 | ✅ 已修（回 503） |
| D | 中 | 部分可點元件 <48×48px（無障礙明列要求） | S-11 CSS | ✅ 已修 |
| E | 低 | 文件生成「來源下拉」是 N+1 查詢 | 前端 S-11 | ✅ 已修 |
| F | 中 | 匯出走 `window.location`，後端 4xx 會直接蓋掉整頁、無友善訊息 | 前端 S-11 | ✅ 已修 |
| G | 低 | dev_log 把 `test_postprocess` 寫成 6 項（實際 7 項） | 文件 | ✅ 已修 |
| H | — | review 期間 `jobs.py`/`test_jobs.py` 被另一條 session 同時改動 | 流程 | 已解除（S-04 已 commit） |

---

## 2. 問題 A（核心）：歷史「匯出」鈕一律回 404

### 現象
批次 → 歷史記錄，每筆 job 會列出各語言的 `xx.docx` 匯出鈕。**點任何一顆都跳 404**（瀏覽器整頁變成 `{"data":null,"error":"http_error","message":"尚無對應產出可匯出"}`）。

### 重現
1. 上傳音檔建一個 job（會停在 `queued`）。
2. 切到「歷史記錄」分頁。
3. 點任一 `zh.docx` 之類的鈕 → 404。

### 根因（兩層）
1. **目前沒有任何 transcript/translation 產出可下載。** S-04（ASR worker）/S-05（翻譯 worker）尚未把產出落檔，job 永遠停在 `queued`，`outputs` 表沒有 `kind=transcript`/`translation` 的列。後端 `export_job` 查不到對應產出就丟 404：
   - 後端：`server/routes/jobs.py:197-210`（`out is None` → 404「尚無對應產出可匯出」）
   - 前端產生鈕：`web/app.js:191-197`（`loadHistory` 用 `j.out_langs` 逐語言生鈕）
   - 前端點擊導頁：`web/app.js:198-203`

2. **就算 S-04/05 落檔了，現在的參數也會錯配。** 鈕是用「輸出語言 `out_langs`」逐一生成，但匯出網址寫死 `kind=transcript`：
   ```js
   // web/app.js:201
   window.location = '/api/jobs/'+...+'/export?fmt=docx&kind=transcript&lang='+b.dataset.lang;
   ```
   逐字稿（transcript）只會有「來源語言」一份；其餘 `out_langs` 對應的其實是 **翻譯（`kind=translation`）**。所以對非來源語言，這個 `kind=transcript` 永遠對不到列，將來仍會 404 或抓錯東西。

### 影響
- 現在：功能性死路，使用者每次點都 404。
- 將來：語言/類型對應錯，下載到錯的產出或續 404。
- 體驗：因為走 `window.location`（見問題 F），404 直接把整頁洗成 JSON，沒有任何提示。

### 建議修法
1. **狀態未完成就不要給可下載的鈕**：`loadHistory` 只在 `j.status==='done'` 且該 (kind,lang) 真的存在時才渲染鈕。最穩的是改成先打 `GET /api/jobs/{id}` 拿 `outputs` 索引（後端已回，見 `jobs.py:190-193`），**依實際 outputs 列出可下載項**，而不是憑 `out_langs` 猜。
2. **修正 kind/lang 對應**：來源語言給 `kind=transcript`；其餘輸出語言給 `kind=translation`。
3. **改用 fetch + blob 下載**（見問題 F），把 4xx 變成友善訊息而非整頁跳走。

---

## 3. 問題 B：沒有「列出記錄」的 API，手動生成的文件重整後找不回

### 現象
文件生成（S-08）成功後，前端把 `output_id` 存在記憶體變數 `lastRecordId`（`web/app.js:269,281-287`），靠它再匯出。**重整頁面後 `lastRecordId` 沒了，就再也叫不回那份記錄。**

### 根因
- `routes/records.py` 只有 `POST ""`（建立）與 `GET /{output_id}/export`（匯出），**沒有列表端點**（`grep` 確認：`records.py:52,128` 兩個路由而已）。
- 手動上傳逐字稿生成的記錄，入庫時 `ref_type/ref_id = "manual"/"manual"`（`records.py:64,117`），**不掛在任何 job 底下**，所以連 `GET /api/jobs/{id}` 的 `outputs` 也撈不到它。

### 影響
手動來源（FR-17 主路徑）生成的會議記錄／交班，重整即遺失入口；只能靠瀏覽器沒關、變數還在。

### 建議修法
- 加 `GET /api/records?limit=&offset=`（列 `kind=record` 的 outputs，回 `{id,template?,ref_type,ref_id,created_at}`＋pagination），前端文件生成頁加一個「歷史記錄」列表可重新匯出。
- 註：`template` 目前沒存進 `outputs`（只回給前端當下用），若列表要顯示範本別，需在 `outputs` 補欄位或另存。

---

## 4. 問題 C：非容器環境缺 `ffprobe` → 上傳 500、測試 9 紅

### 現象
- 跑 `pytest` 在沒有 ffmpeg 的機器上，`test_jobs.py` 9 項紅（`RuntimeError: ffprobe 不存在`）。
- 實際起站時若環境沒 ffmpeg，**任何上傳都會 500**。

### 根因
- 上傳深驗呼叫 `preprocess.probe_duration_seconds`（`server/routes/jobs.py:136`）。
- 缺 ffprobe 時 `preprocess._ffprobe` 丟的是 `RuntimeError`（**不是** `BadAudio`）：`server/services/preprocess.py:24-27`。`create_jobs` 只攔 `preprocess.BadAudio`（`jobs.py:137`），`RuntimeError` 漏接 → 落到全域 500 handler。
- 這是並行 S-04 工作新加的深驗（review 當下 `jobs.py`/`test_jobs.py` 正被改，見問題 H），非 S-08/09/11 引入。容器內 Dockerfile 已裝 ffmpeg（`server/Dockerfile:13`），正式環境 OK。

### 影響
本機開發、CI（若 runner 沒 ffmpeg）會踩；正式容器不受影響。

### 建議修法
- CI / 本機文件補一句「需 ffmpeg」，或測試對 `probe_duration_seconds` 做 fixture/skip。
- 防呆：`create_jobs` 對「ffprobe 不存在」這種環境錯誤回明確 503/500 訊息，而不是裸 500（看 S-04 owner 要不要收）。

---

## 5. 問題 D：部分可點元件 <48×48px（無障礙）

CLAUDE.md 無障礙明列「可點元件 ≥48×48px」。主要按鈕已達標（愛愛院主題全域覆寫：`.btn`/`.nav button` `min-height:48px`），但下列次要元件仍偏小：

| 元件 | 實際 | 位置 | 用在哪 |
|---|---|---|---|
| `.ic` | ~24px（只設了圓角、無 min-height） | `web/styles/tokens.css:106,233` | 端點啟用/停用/刪除、歷史匯出鈕 |
| `.dd-sm` | 40px | `tokens.css:228` | 小型下拉 |
| `.seg button` | 42px | `tokens.css:230` | 分段切換 |
| `.btn.sm` | 42px | `tokens.css:226` | 小按鈕 |
| `.icon-btn` | 42×42px | `tokens.css:255` | 頂欄圖示鈕 |

### 建議修法
給上述加 `min-height:48px`（`.ic` 連 `min-width`/padding 一起調），尤其 `.ic`——它正好是端點管理與歷史匯出在用的鈕。屬沿用 v6 定稿的尺寸，調整時注意別撐爆表格列。

---

## 6. 問題 E：文件生成「來源下拉」是 N+1 查詢

`web/app.js:231-247` `loadTranscriptSources`：先 `GET /api/jobs`，再對**每一個 job** 各打一次 `GET /api/jobs/{id}` 撈 outputs。job 一多就是 N+1。目前資料少不痛，S-04 落檔後會明顯。
- 建議：後端提供一次撈「所有 transcript 產出」的端點（或 `GET /api/jobs?include=outputs`），前端一次取回。

---

## 7. 問題 F：匯出用 `window.location`，4xx 會整頁洗成 JSON

兩處匯出都直接 `window.location = '/api/.../export?...'`：
- 歷史匯出：`web/app.js:201`
- 文件生成匯出：`web/app.js:286`

成功時瀏覽器會下載；但**失敗（404/400）時整頁被導去那個 JSON 回應**，使用者看到一坨 `{"error":...}`。
- 建議：改 `fetch` → 檢查 `res.ok` → `blob()` → `URL.createObjectURL` 觸發下載；非 ok 就用既有 `genMsg`/`batchMsg` 顯示友善訊息（字典已有 `err.generic` 等）。

---

## 8. 問題 G／H：小訂正與流程提醒

- **G**：`docs/dev_log/Sprint2-S08-doc-generation.md` 寫「`test_postprocess.py` 6 項」，實際 **7 項**（`test_postprocess.py` 內 7 個 `def test_`）。順手訂正即可。
- **H**：review 期間 `server/routes/jobs.py` 與 `server/tests/test_jobs.py` 被**另一條 session 同時修改**（加了 `duration` 欄位＋ffprobe 深驗、3 個新測試）。代表 S-04 ASR 工作正在進行中，接手 jobs 相關時請先 `git status`／對齊，避免覆蓋彼此。

---

## 9. 驗證現況（哪些是真的好的，避免重工）

review 時實測通過、**不用重查**：
- S-08：mock `post` 端點 → `POST /api/records` 回 201、落 `outputs(kind=record)`、含注入字樣逐字稿仍只進 user（SEC-4）、記錄匯出 docx 可開。
- S-09：`render` 三格式正確、docx 重開 H1=26pt 粗體 `#00A97A`/H2=20pt、`fmt=pdf`→400、`get_job` 回 outputs 索引（不外露 path）。
- S-11：四檔拆分、FastAPI 靜態服務全 200＋正確 MIME、端點 CRUD、資源預設隱藏、i18n（120 個 HTML key 全在字典、148 字典 key 全有 zh/en/th）。
- 測試：補齊 ffprobe 後 **45 passed**。

本檔列的 A–F 都集中在「歷史/記錄的取回與下載」這條尾巴，多數是 S-04/05 產出落檔前就先把前端鈕做出來造成的落差。優先順序：**A → B → F → D → C → E**。
