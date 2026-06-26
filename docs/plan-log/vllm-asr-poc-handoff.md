# 交接｜vLLM-on-Blackwell「完整編譯模式」ASR PoC（給接手的 AI）

> 目的：讓**完全不知道前情**的 AI 能獨立接手，把 vLLM 以**完整編譯模式**跑起來、完成 PoC。
> 建立：2026-06-26。配對文件：`docs/plan-log/vllm-asr-poc.md`（閘門總表）、`docs/dev_log/vllm-asr-poc.md`（逐關證據）、`docs/model-setup-SOP.md` §3.B。
> 全程繁中、所有指令以絕對路徑為主、在 host 原生環境執行（非容器）。

---

> ✅ **狀態更新（2026-06-26，本文件已收尾）**：PoC **結論 GO**——下方「目前卡點／你的任務」**已全部完成**，本文件僅留存歷史脈絡。
> CCCL 版本衝突採**路C**（`export VLLM_USE_FLASHINFER_SAMPLER=0`）解掉，G3 完整編譯起得來、G4–G7 全過、串流（SSE＋WebSocket `/v1/realtime`）可用。
> **接手者不需再執行本文件的任務**；最終 pin 的版本/env/啟動指令見 `docs/model-setup-SOP.md` §3.B，逐關證據見 `docs/dev_log/vllm-asr-poc.md` ⑨–⑭。

## 0. 一分鐘摘要
語音轉文字工具（stt-translate）的即時 ASR 必須用 vLLM 跑 Qwen3-ASR（D-13）。GPU 是 RTX PRO 6000 **Blackwell（sm_120）**，D-16 要先 PoC 驗證可行。
- ✅ **最大風險已排除**：sm_120 kernel 實測可用（torch 算得出來、arch_list 含 sm_120）。
- ⛔ **目前卡點**：vLLM **完整編譯模式**啟動時，flashinfer 為 sm_120 JIT 編「取樣 kernel」失敗，CCCL 版本守衛報「CUDA compiler 與 toolkit headers 不相容」。根因＝venv 內 pip CUDA 套件**次版本不一致**。
- 🎯 **你的任務**：解掉這個版本衝突 → 讓完整編譯模式起得來 → 跑完 G4–G7 → 給 Go/No-Go。

---

## 1. 目標（Definition of Done）
1. vLLM 以**完整編譯模式**（**不加** `--enforce-eager`，即 torch.compile/Inductor + CUDA graph 生效）穩定服務 `Qwen/Qwen3-ASR-1.7B` 於 `:8000`，`curl /v1/models` 回 200 且服務**持續存活**（非啟動即崩）。
2. 完成並留證據：
   - **G4 批次**：POST 一段中文音檔 → 合理中文逐字稿。
   - **G5 串流**：串流模式回 partial/final 增量，量首字延遲；確認**不回時間戳**（NG-6）。← S-06 命脈。
   - **G6 資源**：`--gpu-memory-utilization` 確實框住 VRAM、與其他租戶不衝突。
   - **G7 整合**：app 容器經 `host.docker.internal:8000` 連得到；DB 註冊 `function=asr` 端點、`routing.resolve_endpoint('asr')` 取得。
3. 把可動的版本/env/啟動指令**回填 `model-setup-SOP.md` §3.B**，更新 `docs/dev_log/vllm-asr-poc.md` 與閘門總表，給出 **Go/No-Go**。

---

## 2. 系統環境事實（已實測，請勿重猜）
| 項目 | 值 |
|---|---|
| 主機 / OS | Ubuntu **26.04**（Resolute Raccoon），host 原生（app 另在 CPU 容器，不在此 PoC 範圍） |
| GPU | NVIDIA **RTX PRO 6000 Blackwell** Server Edition，97887 MiB（~96GB），**capability (12,0) = sm_120** |
| 驅動 / 驅動級 CUDA | driver **595.58.03**，**CUDA 13.2**（向下相容 cu128/cu130） |
| Python（執行用） | uv 管理的 **CPython 3.12.13**（在 `~/.venvs/asr`）；系統 python 是 3.14，**勿用**（D-15） |
| 套件管理 / sudo | apt 可用；**`sudo` 需密碼、非互動失敗** → 要 root 的事得請使用者親跑 |
| 編譯器 | **已裝 build-essential**：`/usr/bin/{cc,gcc,g++,make}`、gcc **15.2.0** |
| 磁碟 | 2TB，剩 ~1.3TB |
| ⚠️ 共用 GPU | 同卡有其他租戶：**ComfyUI**（`~/ComfyUI/venv`，曾佔 ~20GB）、**LM Studio**（Gemma，~14.5GB）、桌面雜項。**啟動前先看可用 VRAM；只可殺 cmdline 含 `.venvs/asr` 的自己 process，絕不動別人。** |

---

## 3. 專案脈絡（為何要這個 PoC）
- 產品：長照機構內網、全本地語音轉文字＋即時翻譯（stt-translate）。
- ASR 模型 Qwen3-ASR-1.7B：**即時串流必須 vLLM**（LM Studio 不支援 ASR，D-13）。
- D-16 把「vLLM 在 Blackwell 上跑得起 Qwen3-ASR 並可串流」定為 S-06（即時串流）上線前**硬性關卡**——本 PoC 即為此。
- 完整規格見 `spec/`；ASR 約束：串流**不回時間戳**（時間靠伺服器時鐘）、批次單段 ≤20 分、每 15 分切段。

---

## 4. 現在「有什麼」（已完成、已驗證）
| 項 | 內容 |
|---|---|
| **權重** | `Qwen/Qwen3-ASR-1.7B` 已在 HF 快取，完整無缺；**鎖版 sha＝`7278e1e70fe206f11671096ffdd38061171dd6e5`**（啟動一律帶 `--revision`，SEC-1） |
| **venv** | `~/.venvs/asr`（py3.12.13） |
| **核心套件** | **vllm 0.23.0**、**torch 2.11.0+cu130**（CUDA 13.0）、triton 3.6.0、flashinfer-python/cubin 0.6.12、transformers 5.12.1、ninja 1.13.0 |
| **sm_120 已證可用** | `torch.cuda.get_arch_list()` 含 `sm_120`；4096² matmul/softmax 實跑無 `no kernel image`。**D-16 主要硬體風險已排除。** |
| **編譯器** | build-essential（gcc 15.2.0）已裝、Triton 認得 cc |
| **venv 內 CUDA 工具鏈** | 整合在 `~/.venvs/asr/lib/python3.12/site-packages/nvidia/cu13/`（`bin/nvcc`=13.2.78 可跑、`bin/ptxas`、`include/`、`lib/`、`nvvm/`） |
| **vLLM 架構支援** | 0.23.0 原生支援 `Qwen3ASRForConditionalGeneration`，並另有 `Qwen3ASRRealtimeGeneration`（串流 G5 的線索） |
| **已知決策** | torch 走 **cu130**（vLLM 原生、實測過，**不要回頭塞 cu128**）；vLLM `--gpu-memory-utilization` 設 **~0.15**（**非** SOP 舊寫的 0.8——那是「全體服務總上限 RES_CAP」，非單一實例 util） |

---

## 5. 現在「沒有什麼／卡在哪」（精準）
**完整編譯模式 server 尚未成功起來。** 走過的失敗鏈（每修一個就露下一個；每次重啟 1–3 分）：

| # | 啟動方式 | 失敗點 | 處置 |
|---|---|---|---|
| 1 | 預設（完整） | torch.compile/Inductor 要 codegen → `Failed to find C compiler` | — |
| 2 | `--enforce-eager` | 模型自帶 Triton kernel `_triton_mrope_forward` JIT 仍要 `cc` → 同錯（eager 關不掉模型內建 triton kernel） | 請使用者裝 build-essential ✅ |
| 3 | 完整 | `FileNotFoundError: 'ninja'` | venv bin 未在 PATH；把 `~/.venvs/asr/bin` 加進 PATH ✅ |
| 4 | 完整 | flashinfer JIT 呼叫 `/usr/local/cuda/bin/nvcc` → not found（exit 127） | 設 `CUDA_HOME` 指向 venv 的 `nvidia/cu13` ✅ |
| 5 | 完整（CUDA_HOME 已設） | **← 目前卡這**：flashinfer 編 sm_120 取樣 kernel，`cccl/.../cuda_toolkit.h:41 error: "CUDA compiler and CUDA toolkit headers are incompatible"` | 見下方解法 |

**根因研判**：venv 內 pip 的 nvidia-cuda-* 套件 **CUDA 次版本兜不攏**——
`nvidia-cuda-nvcc==13.2.78`、`nvidia-cuda-runtime==13.0.96`、`nvidia-cuda-cccl==13.3.3.3.1`、`nvidia-cuda-crt==13.3.33`、`nvidia-cuda-nvrtc==13.0.88`（混了 13.0 / 13.2 / 13.3），加上 flashinfer 自帶 vendored cccl，觸發 CCCL 的「compiler vs headers」版本守衛。
**重要線索**：log 顯示 attention 已用 **FlashAttention v2（預編譯，非 flashinfer）**；目前**只有「取樣器(sampling)」在硬走 flashinfer JIT**（編 `sampling.cu` / `renorm.cu` / `flashinfer_sampling_binding.cu`）。

---

## 6. 要做什麼（接手步驟，含確切指令）

### Step 0 — 前置與安全檢查
```bash
# 確認沒有殘留 vLLM、看可用 VRAM（共用卡！）
ss -ltn | grep ':8000' || echo "(8000 未監聽，無殘留)"
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv
# 若要清殘留，只清自己的（cmdline 含 .venvs/asr）：
for pid in $(nvidia-smi --query-compute-apps=pid --format=csv,noheader); do \
  grep -q '\.venvs/asr' /proc/$pid/cmdline 2>/dev/null && { echo "kill $pid"; kill -9 $pid; }; done
```

### Step 1 — 解 flashinfer / CUDA 版本不相容（擇一，建議由 C 起）
固定 env（每次啟動都要）：
```bash
NV="$HOME/.venvs/asr/lib/python3.12/site-packages/nvidia/cu13"
export CUDA_HOME="$NV" CUDA_PATH="$NV"
export PATH="$NV/bin:$HOME/.venvs/asr/bin:$PATH"
export VLLM_NO_USAGE_STATS=1 DO_NOT_TRACK=1 HF_HUB_DISABLE_TELEMETRY=1   # 內部隱私工具，關遙測（NG-1）
```

- **路 C（最快、建議先試；仍是完整編譯）**：attention 已是 FlashAttention2 預編譯，只把「取樣器」從 flashinfer 換成 torch 原生，繞過版本衝突，torch.compile/CUDA-graph 照常生效：
  ```bash
  export VLLM_USE_FLASHINFER_SAMPLER=0
  # 視情況可再加：export VLLM_ATTENTION_BACKEND=FLASH_ATTN
  ```
  > 這仍算「完整編譯模式」（不加 --enforce-eager）；差別只在取樣不用 flashinfer 的融合 kernel。先用這條把 server 拉起來、把 G4–G7 跑完，是最省事的完整模式路徑。

- **路 A（最正統、要 root；若要連 flashinfer 取樣器都啟用）**：在 host 裝**單一版本、自洽**的 CUDA Toolkit（版本與 nvcc 對齊，建議 13.2 或一致的 13.x），`CUDA_HOME` 指它（取代 venv 的 cu13 拼裝）。需使用者 `sudo`（如 NVIDIA apt repo 的 `cuda-toolkit-13-2`，或對應 runfile）。裝完 flashinfer JIT 應能過 cccl 版本守衛。
  - 先確認衝突版本：`~/.venvs/asr/bin/pip list | grep -i nvidia-cuda`

- **路 B（venv 內對齊，不需 root，較 fiddly）**：把 `nvidia-cuda-*` pip 套件 pin 到**同一 CUDA 次版本**（讓 nvcc 與 headers 一致）；風險是 vLLM/flashinfer 對版本有自己的 pin，動了可能連鎖。非必要不建議。

### Step 2 — 啟動完整編譯模式（背景）
```bash
~/.venvs/asr/bin/vllm serve Qwen/Qwen3-ASR-1.7B \
  --revision 7278e1e70fe206f11671096ffdd38061171dd6e5 \
  --gpu-memory-utilization 0.15 \
  --host 0.0.0.0 --port 8000
```
> 首次會 **flashinfer/Inductor 編譯＋CUDA graph capture（~51 種批量）**，數分鐘，會快取（`~/.cache/flashinfer`、Inductor cache），之後啟動快。**勿用前景 `sleep` 等待**；用 `curl --retry`（見下）。

### Step 3 — 等待就緒並驗證（不要用 sleep）
```bash
curl -s --retry 100 --retry-delay 5 --retry-connrefused --retry-all-errors \
  --retry-max-time 500 -m 5 http://localhost:8000/v1/models -w "\nHTTP %{http_code}\n"
```
HTTP 200＝**G3 過**。若仍崩，讀 stderr 找 `FAILED:` / `error:` 行，對照 §5 的失敗鏈往下解。

### Step 4–7 — 跑 PoC 其餘關卡
- **G4 批次**：備一段中文 wav（≤20 分），
  ```bash
  curl -s http://localhost:8000/v1/audio/transcriptions \
    -F file=@/path/to/中文.wav -F model=Qwen/Qwen3-ASR-1.7B
  ```
  驗：回合理中文逐字稿。
- **G5 串流（S-06 命脈、關鍵未知）**：本 vLLM 對 Qwen3-ASR 的**串流介面尚未確認**。要查：
  - 在 transcription 端點帶 `stream=true`（SSE）看是否回增量；
  - 或研究 `Qwen3ASRRealtimeGeneration` 架構的啟用方式（可能要不同 `--task`/啟動參數或不同端點）。
  - 驗：說一段中文後幾句內出 partial、最後 final；確認**無時間戳**（合 NG-6）。
- **G6 資源**：起來後 `nvidia-smi` 看 vLLM 佔用是否被 `--gpu-memory-utilization` 框住、與其他租戶不衝突；對照 host `gpu_stat`(:3601) 與 app `services/resources.py` 的 `can_reserve()`/`RES_CAP`。
- **G7 整合**：app 容器內 `curl http://host.docker.internal:8000/v1/models`（確認 `docker-compose.yml` 有 `extra_hosts: host.docker.internal:host-gateway`）；用 `POST /api/endpoints` 註冊 `function=asr` 端點，確認 `routing.resolve_endpoint('asr')` 取得。

### Step 8 — 收尾
- 把可動的 **env＋版本＋啟動指令** 回填 `model-setup-SOP.md` §3.B（特別是：host 需 build-essential、`CUDA_HOME`/PATH 設定、util 0.15、cu130、串流結論）。
- 更新 `docs/dev_log/vllm-asr-poc.md` 與 `docs/plan-log/vllm-asr-poc.md` 閘門總表；給 **Go/No-Go**。

---

## 7. 速查（路徑・指令・雷區）
- venv：`~/.venvs/asr`｜ python：`~/.venvs/asr/bin/python`｜vllm：`~/.venvs/asr/bin/vllm`
- 模型 sha（鎖版）：`7278e1e70fe206f11671096ffdd38061171dd6e5`
- CUDA 工具鏈（venv 拼裝）：`~/.venvs/asr/lib/python3.12/site-packages/nvidia/cu13`
- 埠：app 3600/3610、**ASR vLLM 8000**、LLM(LMStudio) 1234、NLLB 8001、gpu_stat 3601
- app 端 env：`ASR_ENDPOINT=http://host.docker.internal:8000/v1`
- 健康檢查：`curl -s http://localhost:8000/v1/models`
- VRAM：`nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader`
- **雷區**：
  1. 共用 GPU——只殺自己（`.venvs/asr`）的 process。
  2. `--gpu-memory-utilization` 用 ~0.15，**不要 0.8**。
  3. torch 用 **cu130**，別回頭塞 cu128（vLLM 0.23 原生 cu130、已實測 sm_120 OK）。
  4. 啟動務必帶 `--revision <sha>`（SEC-1）。
  5. 等待用 `curl --retry`，**不要前景 `sleep`**。
  6. 串流**不回時間戳**是預期行為（NG-6），不是 bug。
  7. `--enforce-eager` 也擋不掉模型內建 Triton kernel 的 JIT（仍需 cc）；它只關 torch.compile/cudagraph。
  8. sudo 需密碼——要 root 的步驟（路 A 裝 CUDA toolkit）得請使用者親跑。

---

## 8. 驗收清單
- [ ] G3 完整編譯模式 server 起來、`/v1/models` 200、持續存活
- [ ] G4 批次轉錄出合理中文逐字稿
- [ ] G5 串流回 partial/final、量首字延遲、確認無時間戳
- [ ] G6 VRAM 受 util 框住、與其他租戶不衝突
- [ ] G7 app 容器連得到、路由解析 `asr` 正確
- [ ] 版本/env/啟動指令回填 SOP §3.B；Go/No-Go 寫入 dev_log
