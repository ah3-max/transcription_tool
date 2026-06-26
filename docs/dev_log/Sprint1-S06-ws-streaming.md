# 開發日誌：S-06 即時 WebSocket 串流（C 軌）

> 類型：開發日誌（事中／事後，逐步追加）｜配對規劃：`docs/plan-log/Sprint1-S06-ws-streaming.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**狀態：前置 host 服務就緒（§2.6 NLLB 先行已完成）**（C 軌，核心命脈）

⚠️ 開工要點：第 5 步「寫入 sessions/outputs 契約」一凍結，立刻同步給 D 軌 S-07，讓其後端並行。

<!-- 每完成一步 append 一段：原本→發生→改了→困難→又怎麼改→最後如何解決 -->

---

## ① 2026-06-26｜§2.6 前置：NLLB 服務建置＋realtime ASR systemd unit（host 端）

> 分支：`feat/s06-ws-streaming`（自 `feat/s08-s09-s11` HEAD 開，**非** main——main 落後 11 commit 且缺 S-06 依賴的 `idle.py`(S-03)／`live_readiness`(S-10)）。

**原本**：`/v1/realtime`(ASR) 與 NLLB(`live_tr`) 皆未跑、兩個 systemd unit（`stt-vllm-asr`／`stt-nllb`）都不存在；`idle.py:28-30` 已引用卻無實體。§2.6 拍板「NLLB 先行再做完整 S-06」。

**做了什麼**：
1. **NLLB venv**：`uv venv ~/.venvs/nllb`；torch 走 **cu130**（非 SOP §3.C 原寫的 cu128——§2.6 已警告 Blackwell sm_120 的雷）；裝 transformers 5.12.1 / fastapi / uvicorn / sentencepiece / numpy。
2. **sm_120 kernel 驗證**（比照 PoC G2，不假設）：torch 2.12.1+cu130，`is_available()=True`、`get_arch_list()` 含 `sm_120`、device cap (12,0)、實跑 matmul+softmax 出數字（5496.0 / 0.9999998）→ cu130 在 Blackwell 可用。
3. **服務程式** `host-helpers/nllb_server.py`（版控定稿）：`{data,error?}` 外型、`/health` 就緒探針、FLORES 語言碼白名單（zho_Hans/Hant、eng_Latn、tha_Thai）、惰性載入；部署到 `~/services/`。fp16 載入。
4. **翻譯實測**（fp16）：中→泰「早安，今天身體還好嗎？」→「สวัสดีครับ คุณรู้สึกดีไหม?」、「請問哪裡不舒服？」→「คุณรู้สึกไม่สบายตรงไหนครับ?」、中→英→「Good morning, how are you today?」——皆正確。
5. **systemd units**（`host-helpers/systemd/`，皆安裝至 `~/.config/systemd/user/`、`daemon-reload`）：
   - `stt-nllb.service`：補關遙測 env(NG-1)＋`TimeoutStartSec=300`；`systemctl --user start` 起得來、health ready、譯文正確。**按需起、不 enable**。
   - `stt-vllm-asr.service`（**新建，§2.5-B 交付**）：包 §3.B 完整啟動指令（`--hf-overrides` realtime 架構、`--revision` 鎖版、`--gpu-memory-utilization 0.15`、`--kv-cache-memory-bytes 8GiB`、`VLLM_USE_FLASHINFER_SAMPLER=0`、CUDA env），`ExecStopPost` 強殺殘留 `VLLM::EngineCore`。

**遇到的困難 ① cu130 wheel 下載逾時**：首裝 torch 在 `pypi.nvidia.com` 抓 cusparse 逾時（非解析失敗）→ `UV_HTTP_TIMEOUT=600` 重試即過。

**遇到的困難 ②（重要）stt-vllm-asr 起不來——共用卡 VRAM 競爭，非 unit 缺陷**：
- unit 參數**解析正確**（journal `non-default args` 顯示 hf_overrides JSON、revision、util、kv 皆對）。
- 但 EngineCore 報 `Free memory on device cuda:0 (10.58/94.97 GiB) < desired (0.15, 14.25 GiB)`：當下他人服務佔 85.8GB、僅 ~10.6GB free，`--gpu-memory-utilization 0.15` 需 14.25GB free → 起不來。PoC 當時他人只佔 ~16GB 才起得來。
- **結論**：unit 本身正確（停掉後 `ExecStopPost` 清乾淨、無 EngineCore 殘留、VRAM 釋回）；此為共用卡排程現實，正是 D-06「按需起＋閒置釋放」要解的問題。完整 `/v1/realtime` 端到端待 VRAM 較空、或他人服務釋放後再驗（PoC 已證該指令在 VRAM 足時可跑）。
- **VRAM 帳**：NLLB fp16 footprint ~14.6GB（含 CUDA context，非僅 6.6GB 權重）＋ASR ~14GB → 共住逼近上限；要常駐／穩定共住建議轉 NLLB CT2 int8(~3.4GB)。

**另記**：host 既有一個泛用 `vllm.service`（`vllm-env`／cuda-12.8／`/home/aiairdp/model`，亦佔 :8000，已 enable 開機自啟）——**非本專案**、未動它；與 `stt-vllm-asr` 同佔 :8000，兩者不可同時起（已在 unit 註解標明）。model_ctl 白名單僅含 `stt-nllb`/`stt-vllm-asr`，不碰它。

**收尾狀態**：兩服務均**停止**（按需起，D-06 正確 resting state）；unit 與 venv 就緒。下一步＝§2 步驟 1–8 的 S-06 app 端實作（`services/asr.py`／`live_translate.py`／`ws/live.py`／前端）。

---

## ② 2026-06-27｜§2 步驟 1–8：app 端實作（asr/live_translate/vad/sessions/ws/前端＋測試）

**原本**：`ws/` 空、無 ASR/即時翻譯/VAD/落地任何 app 端程式碼；前端即時頁是 stub（計時器假動）。

**做了什麼（對齊 plan §2 八步）**：
1. **`services/asr.py`**：realtime WebSocket 客戶端。協定**直接取自安裝好的 vLLM** `entrypoints/speech_to_text/realtime/{connection,protocol}.py`（非臆測）：client→`session.update`/`input_audio_buffer.commit(final)`/`input_audio_buffer.append(base64 PCM16)`；server→`transcription.delta`/`transcription.done`/`error`。`ASRStream` 支援併發 send_audio／events 迭代；`strip_asr_prefix` 自剝 `language {lang}<asr_text>` 前綴；`realtime_ws_url` 把 `http…/v1`→`ws…/v1/realtime`。
2. **`services/live_translate.py`**：對 NLLB `/translate`（非 OpenAI、FLORES 語碼）一對多**並行**扇出（D-03，不串接）；來源語直送、單語失敗隔離不拖垮其他語；缺端點拋 `LiveTranslateError`。
3. **`services/vad.py`**：純 Python（app 容器無 numpy/torch）RMS 靜音切句 `SilenceSegmenter`，speech 後足夠靜音＝語句邊界；保留換 Silero 的同介面掛點（plan 明示可簡化）。
4. **`ws/live.py` → `/ws/live`**：串接 上行音框→VAD→ASR→翻譯→下行 `{type:ready|partial|final|saved|degraded|error}`；`t` 一律伺服器時鐘（NG-6）。`main.py` 註冊 1 行。
5. **`services/sessions.py`（★契約落地）**：停止時封 PCM16→WAV 落 recordings、逐字稿＋各語譯文落 outputs、寫 `sessions`＋`outputs` 列、回 session_id。**寫入契約凍結於檔頭註解**（S-07 依賴）。
6. **SEC-6**：`/ws/live` 限私網/loopback 來源、限同時連線數(8)、限單則訊息(1MiB)、閒置(120s)斷線。
7. **idle 插點**：用 ASR／live_tr 時呼叫 `idle.tracker.record_use`（補 G5 wiring）。
8. **前端 `web/app.js`＋`i18n.js`**：取代 stub——`getUserMedia`→AudioContext 降 16k PCM16→`/ws/live`；interim 半透明草稿、final 實心、saved 回記錄；多目標語複選、顯示語切換。

**困難 ① 協定欄位無從臆測**：plan §2.5-A 只給握手「序列」，沒給 JSON 欄位名。→ 直接讀 asr venv 內 vLLM 的 `protocol.py`/`connection.py` 取確切事件型別與欄位（`input_audio_buffer.append.audio` 為 base64 PCM16@16k、`commit.final` 等），確保與 server 完全一致。
**困難 ② realtime 緩衝延遲**：ASR 內部 5s 緩衝、首 partial ≈5s，VAD 落定的 final 句可能略落後語音邊界。→ v1 接受此延遲、於程式與 plan 標註（驗收以「幾句內出現譯文」為準，非逐字即時）；落地 transcript 用 ASR 累積全文、譯文用各 final 句串接。
**困難 ③ app 容器無 numpy/torch**：→ VAD 改純 Python `array`+RMS，可單元測試、零新依賴。

**驗證（寫好≠驗過，據實回報）**：新建 throwaway venv 裝 app requirements 跑 pytest——
- **S-06 新測試 18 項全綠**：`test_asr`(前綴/URL)、`test_vad`(RMS/切句)、`test_live_translate`(扇出/隔離/缺端點)、`test_sessions`(★契約落地 sessions/outputs/檔案)、`test_ws_live`(來源守門＋start→ready→stop→saved 契約路徑＋degraded)。
- 全套 63 passed；**10 failed 全在 `test_jobs.py`**——肇因為**該 venv 缺 ffprobe**（jobs 上傳走 ffprobe→503），與 S-06 無關、Docker 映像有裝 ffmpeg 即過。
- **尚未做（VRAM 擋）**：realtime ASR `/v1/realtime` 端到端、瀏覽器麥克風→譯文整段體驗、停止→記錄頁出現該場的整合驗收——需 host 卡空起 `stt-vllm-asr`＋NLLB（或 CT2 騰空間）後實機驗。
