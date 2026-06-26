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

## 2.5 PoC 接線清單（`vllm-asr-poc` dev_log 實證 → 實作必讀）
> 以下是 PoC 已踩過並解掉的雷，§2 各步實作時務必照辦、勿重新發現。出處：`docs/dev_log/vllm-asr-poc.md` ⑨–⑭、`docs/model-setup-SOP.md` §3.B。

- **A. `/v1/realtime` 握手序列（最會卡）**（dev_log ⑪）：`session.update` → **`commit(final=False)` 才會「啟動」generation** → `append` 音框 → `commit(final=True)` 收尾。漏掉 `commit(final=False)` 會**收不到任何 delta**（PoC 首測就栽在這）。
- **B. ASR server 必須以 realtime 架構啟動**：`/v1/realtime` 預設不掛載，要 `--hf-overrides '{"architectures":["Qwen3ASRRealtimeGeneration"]}'`（SOP §3.B 步驟 4）。→ 本軌須先建 systemd unit **`stt-vllm-asr`**（`services/idle.py:29` 已引用、`idle.py:27` 標「待 S-06/PoC 建立」），讓 model_ctl 能按需起停（D-06）。同一份權重的 realtime server 也同時服務批次/SSE。
- **C. 串流輸出要剝前綴**：realtime/SSE 每個 delta 帶 `language {lang}<asr_text>` 前綴，**批次端點 server 端會剝、串流不剝**（SOP §3.B 點 6）→ `services/asr.py` 解析時自行剝除，否則下行 `src` 帶雜訊。
- **D. 切段必須 VAD/重疊**：固定 5s 緩衝會在段界切字（「長辈」→「长｜备」，dev_log ⑪），首 partial ≈5.24s。→ §2 步驟 3 的 VAD/重疊切段是**必需、非選配**。
- **E. 音訊格式轉換（原 plan 未列）**：PoC 餵 **16kHz 單聲道 PCM16、0.5s/塊**。前端 `getUserMedia` → AudioContext 降取樣 16k PCM16；server 轉 base64 PCM 給 realtime `append`。此為 `/ws/live` 上行最易卡的整合點。
- **F. 時間/延遲**：不回時間戳（NG-6），下行 `t` 用伺服器時鐘；首 partial ≈5s＋ASR＋NLLB 扇出，驗收「幾句內出現譯文」以此為基準，非「即時逐字」。
- **G. 版本/啟動指令 pin 在 SOP §3.B**：torch 走 **cu130**（PoC G2 實測 sm_120 OK），勿重挑 build。

## 2.6 前置決策（2026-06-26 拍板）：NLLB 先行，再做完整 S-06
- PoC 只驗了 **ASR**，**未驗即時翻譯**；§2 步驟 2 依賴的 NLLB(`live_tr`, :8001) 服務尚未做（SOP §3.C「要自己包」、`idle.py:30` 的 `stt-nllb` unit 亦未建）。
- **決議**：**先補 NLLB 服務並驗過 → 再做完整 S-06（ASR＋即時翻譯一次到位）**。S-06 起步被 NLLB 擋住，但一次做到位、不留半截。
- ⚠ **PoC 交叉發現（NLLB 建置必看）**：SOP §3.C 的 NLLB venv 寫 `--index-url .../whl/cu128 torch`，但 PoC G2 在 **sm_120 實測驗過的是 cu130**。NLLB 走 transformers（torch 非 vLLM 強制 pin），建 venv 後**務必比照 PoC 先驗 sm_120 kernel**（`is_available()`＋`get_arch_list()` 含 `sm_120`＋實跑 matmul），別假設 cu128 在 Blackwell 可用。

## 3. 收標準（對齊規格 S-06）
> 進度（2026-06-27）：app 端程式碼＋單元測試（18 項）全綠；標 ⏳ 者為 realtime ASR 端到端，受共用卡 VRAM 競爭暫擋（待 host 起 `stt-vllm-asr`＋NLLB 實機驗）。
- [⏳] 說中文後幾句內出現對應譯文 — 程式路徑完成（asr→vad→live_translate→下行），待實機端到端
- [⏳] interim 半透明、final 實心 — 前端已接 `/ws/live`，待實機視覺驗
- [~] 停止後「錄音記錄」出現該場、含音檔與逐字稿（寫入 sessions/outputs）— **契約落地＋pytest 已過**；整合驗收（記錄頁顯示）待 S-07＋實機
- [x] WS 僅接受內網來源、拒絕外部 — `client_allowed` 私網/loopback，pytest 已過
- [x] 串流以伺服器時鐘標記時間（不依賴 ASR 時間戳）— 下行 `t=time.time()`，NG-6

## 4. 並行/衝突
- **碰的檔**：新檔 `ws/live.py`、`services/asr.py`、`services/live_translate.py`；改 `main.py`（註冊 WS，1 行）；`web/app.js`「即時翻譯」頁區塊。
- **與 D 軌 S-07**：靠第 5 步契約解耦——契約凍結後 D 後端可並行；但**整合驗收（停止錄音→記錄出現）必須等本軌第 5 步完成**。
- **與 B 軌 S-10**：消費 B 的降級訊號約定；各動 app.js 不同區塊。
- **與 A 軌 S-12**：零交集。
