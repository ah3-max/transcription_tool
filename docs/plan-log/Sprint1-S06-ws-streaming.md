# 規劃：S-06 即時 WebSocket 串流（C 軌．核心命脈）

> 類型：規劃（事前）｜配對開發日誌：`docs/dev_log/Sprint1-S06-ws-streaming.md`
> 對應：FR-1~FR-7, NFR-1｜設計：§2.1/2.2, §5 API-06, SEC-6｜依賴：S-03（已完成）｜被依賴：S-07
> 前置：**vLLM-ASR PoC（D-16）已 GO**——`/v1/realtime` WebSocket 串流可用、不回時間戳（見 `docs/dev_log/vllm-asr-poc.md`）。
> 並行性：主攻軌；**第 5 步「寫入 sessions/outputs 契約」凍結後，D 軌 S-07 後端可並進**。

---

## 1. 現況（已查證）
- `server/ws/` 只有空 `__init__.py`，**從零寫**。
- `services/routing.py` 的 `resolve_endpoint("asr"/"live_tr")` 可取端點。
- ASR：host vLLM `host.docker.internal:8000`，即時走 `/v1/realtime`（WebSocket），批次走 `/v1/audio/transcriptions`。
- 即時翻譯：NLLB（`live_tr`，範本綁 :8001，G2 防火牆議題另處理）。
- `sessions` 表 schema 就緒（session_id/name/langs(JSON)/duration/status/created_at/expire_at/audio_path/transcript_path），**無寫入者**。
- `outputs` 表（ref_type=session、kind=transcript/translation/summary）已被 S-08/09 使用。
- `idle.tracker.record_use(...)` 留有 wiring 掛點（G5）。

## 2. 要做的事（從頭到尾）
1. **ASR 串流客戶端** `services/asr.py`：連 vLLM `/v1/realtime`（`resolve_endpoint("asr")`），餵音框、收 partial/final delta。
2. **即時翻譯** `services/live_translate.py`：對 final（必要時 partial）句打 `live_tr`（NLLB）一對多扇出多語（D-03 精神、不串接）。
3. **VAD 邊界**：Silero VAD 切句（先可用簡化版、保留掛點）。
4. **WS 端點** `ws/live.py` → `/ws/live`：上行音框 → VAD → ASR 串流 → 即時翻譯 → 下行
   `{type:partial|final, src, translations:{th,en,...}, t}`；**`t` 用伺服器時鐘**（串流不回時間戳，NG-6）。
5. **持續錄音＋落地（★D 軌契約）**：連線期間錄音；停止時落地音檔＋逐字稿、**建立 session**（寫 sessions：name/langs/duration/status/audio_path/transcript_path）＋寫 outputs（kind=transcript/translation）；下行 `{type:saved, session_id}`。
   - **此步的欄位寫入契約是 S-07 的依賴，須先凍結並同步給 D 軌。**
6. **SEC-6 加固**：限同網段來源（Origin/來源 IP）、限連線數、限訊息大小、閒置斷線。
7. **idle 插點**：呼叫 `idle.tracker.record_use("asr")` / `record_use("live_tr")`（補 G5 wiring）。
8. **前端**：app.js「即時翻譯」頁接 `/ws/live`，interim 半透明／final 實心（§3.1a 留白節奏、draft→落定）。

## 3. 收標準（對齊規格 S-06）
- [ ] 說中文後幾句內出現對應譯文
- [ ] interim 半透明、final 實心
- [ ] 停止後「錄音記錄」出現該場、含音檔與逐字稿（寫入 sessions/outputs）
- [ ] WS 僅接受內網來源、拒絕外部
- [ ] 串流以伺服器時鐘標記時間（不依賴 ASR 時間戳）

## 4. 並行/衝突
- **碰的檔**：新檔 `ws/live.py`、`services/asr.py`、`services/live_translate.py`；改 `main.py`（註冊 WS，1 行）；`web/app.js`「即時翻譯」頁區塊。
- **與 D 軌 S-07**：靠第 5 步契約解耦——契約凍結後 D 後端可並行；但**整合驗收（停止錄音→記錄出現）必須等本軌第 5 步完成**。
- **與 B 軌 S-10**：消費 B 的降級訊號約定；各動 app.js 不同區塊。
- **與 A 軌 S-12**：零交集。
