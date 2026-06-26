# 開發日誌：vLLM-on-Blackwell ASR PoC（D-16 硬關卡）

> 類型：開發日誌（事中／事後）｜ 配對規劃：`docs/plan-log/vllm-asr-poc.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

## 閘門進度總表（逐關更新）
| 關卡 | 狀態 | 證據／版本 pin |
|---|---|---|
| G0 前置完整性 | ✅ 通過 | sha `7278e1e7…`；無 incomplete／無斷鏈；blobs 4.4G |
| G1 環境建置 | ✅ 通過 | vllm 0.23.0｜torch **2.11.0+cu130**（非 cu128，見下）｜cuda 13.0 |
| G2 ★sm_120 kernel | ✅ 通過 | arch_list 含 sm_120；cap (12,0)；matmul/softmax 實跑無 no-kernel |
| G3 vLLM 載 Qwen3-ASR | ✅ 通過 | 路C `VLLM_USE_FLASHINFER_SAMPLER=0` 繞過 flashinfer 版本守衛；完整編譯（torch.compile 21.87s＋CUDA graph 51×2）；`/v1/models` 200、持續存活 |
| G4 批次轉錄 | ✅ 通過 | POST 8.59s 中文 wav → 合理中文逐字稿（內容全中、僅繁→簡）。需在 venv 補 soundfile（伺服器解碼後端）|
| G5 ★串流 partial/final | ✅ 通過 | SSE(`stream=true`)：增量 delta、TTFT 15ms；WebSocket `/v1/realtime`：5s 區塊出 partial（首 partial 5.24s）、38 deltas、final 齊；**兩路皆不回時間戳**(NG-6) |
| G6 資源 reserve | ✅ 通過 | EngineCore 佔 ~15.9GiB（被 util 0.15＋kv-cache 8GiB 框住）；與 ComfyUI 20G＋LM Studio 36.7G 共存、剩 16.5GiB，無衝突 |
| G7 app→vLLM 整合 | ✅ 通過 | 於真正 app image 內：`resolve_endpoint('asr')` 取得；容器經 `host.docker.internal:8000/v1/models` 得 200 |
| 🚦 Go/No-Go | ✅ **GO** | G0–G7 全過（逐關 ✅）；版本/env/啟動指令已回填 SOP §3.B |

狀態圖例：⬜ 待跑｜🔄 進行中｜✅ 通過｜⚠️ 走分支｜❌ 卡關

---

**① 2026-06-26｜現況盤點（PoC 起點）**
- 原本：`~/.venvs/asr` 不存在、vLLM 未起；D-16 關卡未驗。
- 發生：使用者要求規劃並執行 vLLM PoC、可追蹤逐項。
- 現況實測：GPU RTX PRO 6000 Blackwell／driver 595.58.03（CUDA 13.2）；GPU 已被佔 22.7GB；uv 0.11.19、系統 py 3.14；Qwen3-ASR-1.7B 已在 HF 快取；磁碟剩 1.3T。
- 決議：torch 走 cu128；安裝先 vLLM 帶 torch；vLLM util 設 ~0.15（非 SOP 的 0.8）。
- 待續：從 G0/G1 開跑，逐關回填上表與下列分項。

**② 2026-06-26｜G0 前置完整性 ✅**
- 原本：只知 HF 快取有 Qwen3-ASR 目錄，未驗完整性、未鎖版。
- 結果：本地 `refs/main` sha = `7278e1e70fe206f11671096ffdd38061171dd6e5`（snapshot 目錄同名）；2 個 safetensors 分片＋index＋tokenizer/preprocessor/chat_template/generation_config 齊全；無 `*.incomplete`、無斷符號連結；blobs 4.4G（符合 ~4.7GB 預期）。`hf download` 已逐檔 SHA256 校驗（SEC-1 主驗過；遠端 sha 比對為離線環境可省的「再保險」）。
- 鎖版：後續啟動一律帶 `--revision 7278e1e70fe206f11671096ffdd38061171dd6e5`。

**③ 2026-06-26｜G1 環境建置 ✅（torch 落地為 cu130，非 cu128）**
- 原本：`~/.venvs/asr` 不存在；計畫「先 cu128」。
- 發生：`uv venv --python 3.12` 建 py3.12.13；`uv pip install vllm` 解析 190 套件，裝起 **vllm 0.23.0 + torch 2.11.0+cu130（CUDA 13.0）**，連帶 nvidia-*-cu13、nvidia-cuda-nvcc 13.2.78、cudnn-cu13 9.19、nccl-cu13 2.28.9、flashinfer 0.6.12、triton 3.6.0、transformers 5.12.1。
- 關鍵發現：vLLM 0.23.0 的 pinned torch 是 **cu130**（非 cu128）。驅動 CUDA 13.2 向下相容 cu130，且這是 vLLM 自家出貨/測試的組合（最不易 kernel 對不上）。
- 決策：不逆 vLLM 解析去硬塞 cu128（那會重新引入 SOP 修正②的 mismatch 風險）。先以 vLLM 原生 cu130 過 G2；G2 過則 cu130 即最佳解。最終 cu 選擇待 G2 證據＋使用者拍板。
- 困難：大輪子下載（torch 506MB、flashinfer-cubin 427MB、cublas 404MB…）耗 ~35 分鐘，但 exit 0、無錯。
- 待續：G2 驗 sm_120 kernel。

**④ 2026-06-26｜G2 ★sm_120 kernel ✅ PASS（核心關卡退場）**
- 原本：D-16 最大未知＝Blackwell sm_120 上 torch 會不會 `no kernel image available`。
- 結果：torch 2.11.0+cu130、`is_available` True、device=RTX PRO 6000 Blackwell、capability (12,0)=sm_120；**arch_list = ['sm_75','sm_80','sm_86','sm_90','sm_100','sm_120']（含 sm_120）**；4096² matmul（sum=-83249.2）與 softmax（row sum=1.0）實跑成功、無 no-kernel。
- 結論：cu130 在此卡產出可用 sm_120 kernel → **D-16 主要硬體風險退場**。cu128 非必要（cu130 既 vLLM 原生又通過實測）→ cu 版本定為 **cu130**，除非另有政策要求。
- 待續：G3 用 vLLM serve 起 Qwen3-ASR。

**⑤ 2026-06-26｜G3 vLLM 載 Qwen3-ASR 🔄**
- 探架構：模型 architectures=`Qwen3ASRForConditionalGeneration`、model_type=`qwen3_asr`（config 有 support_languages、thinker_config）。
- vLLM 0.23.0 supported archs（共 365）**含 `Qwen3ASRForConditionalGeneration`**，且另有 `Qwen3ASRRealtimeGeneration`／`VoxtralRealtimeGeneration` 等「Realtime」變體 → 對 G5 串流是好兆頭（vLLM 內建 realtime ASR 路徑）。
- `qwen-asr` wrapper 未裝、亦不需要 → 走原生 `vllm serve`。
- 啟動：`vllm serve Qwen/Qwen3-ASR-1.7B --revision 7278e1e7… --gpu-memory-utilization 0.15 --host 0.0.0.0 --port 8000`（util 0.15 而非 SOP 的 0.8，見規劃§7①）。背景啟動中，待 /v1/models 起。

**⑥ 2026-06-26｜G3 ⚠️ 卡關：host 缺 C 編譯器（兩次啟動失敗、根因同一）**
- 第一次（無 eager）：模型成功載入（3.9 GiB on GPU、sm_120 正常），但 `determine_available_memory` 探測階段 vLLM 的 torch.compile/**Inductor** 要 codegen combo kernel → `RuntimeError: Failed to find C compiler`。
- 第二次（加 `--enforce-eager` 關掉 torch.compile）：仍失敗、根因更深——模型碼內的 **Triton kernel `_triton_mrope_forward`（mRoPE）** 在 profiling forward 時 JIT，Triton 用 `cc` 編 launcher → 同樣 `Failed to find C compiler`。**eager 只關得掉 torch.compile，關不掉模型自帶 Triton kernel**、無 flag 可繞。
- 環境查證：Ubuntu 26.04；PATH 無 `gcc/cc/g++/clang`（僅 `gcc-*-base` 執行庫＋孤立 `/usr/libexec/.../cc1`，無前端不可用）；`sudo` 需密碼（無法非互動安裝）；uv 的 py3.12 自帶 `Python.h`（少一相依）。
- 結論：**此堆疊硬性需要 host C 編譯器**（vLLM/Triton JIT 必用）；為 D-16 該暴露的 host 準備缺口，須補進 SOP §3.B。
- VRAM：兩次 crash 都乾淨釋放（現 37GB＝ComfyUI ~20GB＋LM Studio ~14.5GB＋桌面，無我殘留）。
- 待解：host 裝編譯器（建議 `sudo apt install -y build-essential`）後重跑 G3；裝好後可不必加 `--enforce-eager`，並能開 CUDA graph 提速。

**⑦ 2026-06-26｜編譯器補上、G3 重跑（完整模式）**
- 使用者以 `sudo apt install -y build-essential` 裝好 → `/usr/bin/{cc,gcc,g++,make}`、gcc 15.2.0；我方 shell 編譯+執行測試 rc=42 通過、Triton 3.6.0 也認得 cc。task #9 完成。
- 重啟：`vllm serve Qwen/Qwen3-ASR-1.7B --revision 7278e1e7… --gpu-memory-utilization 0.15`（**拿掉 `--enforce-eager`**，走完整 torch.compile/Inductor + CUDA graph，順帶驗編譯鏈在 Blackwell 也通）。背景啟動中，待 /v1/models。

**⑧ 2026-06-26｜G3 完整編譯：工具鏈四連解，現卡 CUDA 版本不相容（轉交接文件）**
- 使用者要求走**完整編譯模式**（非 eager）。逐一解：cc✅ → ninja 進 PATH✅ → nvcc 設 `CUDA_HOME` 指 venv `nvidia/cu13`✅。
- 第 5 次失敗（CUDA_HOME 已設）：flashinfer 為 sm_120 JIT 編「取樣 kernel」時，`cccl/.../cuda_toolkit.h:41 error: "CUDA compiler and CUDA toolkit headers are incompatible"`。
- 根因：venv 內 pip CUDA 套件次版本不一致（nvcc 13.2.78 / runtime 13.0.96 / cccl 13.3.x / crt 13.3.33）＋flashinfer vendored cccl，觸發 CCCL 版本守衛。**線索**：attention 已用 FlashAttention2（預編譯），僅「取樣器」硬走 flashinfer JIT。
- 處置：產出**完整編譯模式接手文件** `docs/plan-log/vllm-asr-poc-handoff.md`（給冷啟動的 AI：現況/缺口/步驟/目標齊全）。建議解法：路C `VLLM_USE_FLASHINFER_SAMPLER=0`（最快、仍完整編譯）或路A 裝單一版本 CUDA Toolkit（最正統、需 sudo）。
- 待續：依 handoff 解版本衝突 → G3 起來 → G4 批次 → G5 串流 → G6 → G7 → Go/No-Go。

**⑨ 2026-06-26｜G3 完整編譯 ✅ 收尾（路C 解版本衝突）**
- 原本：⑧ 卡在 flashinfer 為 sm_120 JIT 編「取樣 kernel」時 CCCL「compiler vs headers 不相容」。
- 改了：採接手文件路C——`export VLLM_USE_FLASHINFER_SAMPLER=0`，取樣器改用 torch 原生（attention 仍走預編譯 FlashAttention2）。完整編譯不受影響。
- 困難①：啟動崩在 memory-profiling 斷言——`Initial free 35.71GiB, current 65.14GiB`，他人（LM Studio）在 profiling 視窗釋放 ~30GB VRAM，vLLM 斷言「free 不該變大」。
- 又怎麼改：改用 `--kv-cache-memory-bytes 8589934592`（8GiB）顯式指定 KV → vLLM 跳過 profiling 守衛（gpu_worker.py:384 early-return）。先試 4GiB 報「65536 max-len 需 7GiB」→ 提到 8GiB。
- 最後如何解決：完整編譯起來——torch.compile 21.87s、AOT 快取、CUDA graph capture 51（PIECEWISE）＋51（FULL decode）、`init engine 36.53s`、`Application startup complete`、`/v1/models` 200 且持續存活。**G3 ✅，完整編譯模式在 Blackwell 證實可用。**

**⑩ 2026-06-26｜G4 批次 ✅（補 soundfile 解碼缺口）**
- 原本：以為起來就能 POST 音檔。
- 困難：vLLM 解上傳音檔走 `load_audio`（soundfile 優先、pyav 退路），但 venv 內 soundfile/pyav 皆缺 → 端點無法解碼。host 也無 ffmpeg/espeak、repo 無樣本音檔。
- 改了：`uv pip install soundfile`（libsndfile 1.2.2，支援 wav 寫＋mp3 讀）＋`edge-tts` 合成已知內容中文句（長照交班情境）→ 轉 16k 單聲道 wav。soundfile 在 server 端 import 時機綁定，故補裝後**重啟 vLLM** 才生效。
- 最後如何解決：POST 8.59s wav → `各位同仁，大家好。今天的护理交班重点是三号病房的长辈血压偏高，需要持续观察并记录。`，與輸入內容一致（僅繁→簡＋標點），HTTP 200。**G4 ✅。** soundfile 列為 ASR venv 必要相依（已回填 SOP）。

**⑪ 2026-06-26｜G5 串流 ✅（SSE＋真 WebSocket 雙路，S-06 命脈解鎖）**
- SSE：`/v1/audio/transcriptions` 帶 `stream=true` → `transcription.chunk` 增量 delta、TTFT 15ms、31 chunks、無時間戳；惟 delta 帶 `language Chinese<asr_text>` 前綴（非串流批次 server 端會剝、串流不剝）。
- 真串流：發現 vLLM 內建 `/v1/realtime` WebSocket（OpenAI-realtime 式協定），但**預設未掛載**——需以 `--hf-overrides '{"architectures":["Qwen3ASRRealtimeGeneration"]}'` 用 realtime 架構載**同一份權重**，supported_tasks 才含 `realtime`、掛上 `/v1/realtime`。
- 困難：首次 WS 測試無 delta。讀 connection.py 發現協定關鍵——`commit(final=True)` 只送結束哨兵、**`commit(final=False)` 才啟動 generation**。正解序列：session.update → commit(final=False) 啟動 → append 區塊 → commit(final=True) 收尾。
- 最後如何解決：以 0.5s 區塊「即時」餵 8.59s 音檔，第一個 partial 在 5.24s（對齊 realtime 5s 段緩衝）、38 deltas、final 齊、無時間戳。固定 5s 分段會在段界切字（「長辈」被切成「长」｜「备」）——S-06 設計應加重疊/VAD 切段改善。**G5 ✅，串流可用、NG-6 成立。**
- 附帶：realtime 架構 server **同時**服務批次/SSE（supported_tasks 含 transcription），批次處理整檔故無切字、前綴已剝 → 單一 server 配置涵蓋批次＋SSE＋WS。

**⑫ 2026-06-26｜G6 資源 ✅ ＋ 共用 GPU 維運雷**
- 證據：realtime server `VLLM::EngineCore` 佔 16278 MiB(~15.9GiB)＝權重 3.9＋KV 8＋activation/graph ~4；被 util 0.15＋kv-cache 8GiB 框住。與 ComfyUI(20.3G)＋LM Studio/Gemma(36.7G) 共存，總用 80.7G/96G、剩 16.5G，無衝突。
- 踩到的雷（重要）：多次重啟過程，被 kill 的父行程留下**孤兒 `VLLM::EngineCore`**（cmdline 不含 `vllm`、`pgrep -f '.venvs/asr/bin/vllm'` 抓不到），各佔 ~16GB → 一度只剩 3.78GB free，導致後續啟動報「free < util 要求」而靜默失敗。解法：`pkill -9 -f 'VLLM::EngineCore'`。已回填 SOP §3.B 第 8 點。

**⑬ 2026-06-26｜G7 app 整合 ✅**
- 於真正的 app image `transcription_tool-stt-app:latest`（含 app 全部 code＋deps）內跑：設 DATA_DIR/DB_PATH、`init_db`、註冊 `function=asr` 端點(url=`http://host.docker.internal:8000/v1`、model=Qwen/Qwen3-ASR-1.7B)，`resolve_endpoint('asr')` 正確取回；再從容器內 `urlopen(url+'/models')` → HTTP 200、model=Qwen/Qwen3-ASR-1.7B。容器以 `--add-host=host.docker.internal:host-gateway`（同 docker-compose `extra_hosts`）。**G7 ✅。**

**⑭ 2026-06-26｜🚦 Go/No-Go = GO**
- G0–G7 全過：前置完整性/環境/sm_120 kernel（G0–G2）＋完整編譯在 Blackwell sm_120 可用、批次與串流（含真 WebSocket `/v1/realtime`）皆可、VRAM 受框且共用卡無衝突、app 路由與容器連通驗證（G3–G7）。
- **S-06 解鎖**：即時串流走 `/v1/realtime`（5s 段 partial、無時間戳）；S-04 批次走 `/v1/audio/transcriptions`。
- 版本/env/啟動指令／共用 GPU 雷已回填 `model-setup-SOP.md` §3.B。
- 與接手文件三條解法對照：採**路C**（`VLLM_USE_FLASHINFER_SAMPLER=0`，最省事、仍完整編譯），未動 root（路A）/未對齊 venv CUDA 套件（路B）。額外解掉文件未預期的兩點：① 共用 GPU profiling race → `--kv-cache-memory-bytes`；② 伺服器解碼缺 soundfile。
- 後續（非本 PoC 範圍）：S-06 串流分段建議加重疊/VAD（避免段界切字）；app 解析需剝 `language X<asr_text>` 前綴（串流路）；按需起停＋閒置釋放（D-06/IDLE_RELEASE_MIN）。
