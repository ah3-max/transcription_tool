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
