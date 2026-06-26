# 規劃：vLLM-on-Blackwell ASR PoC（D-16 硬關卡）

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/vllm-asr-poc.md`
> 對應：D-13／D-16／D-17、SEC-1、S-06（即時串流 ASR）前置關卡；參考 `docs/model-setup-SOP.md` §3.B

## 1. 想解決什麼問題
即時串流 ASR（S-06）必須用 vLLM 跑 Qwen3-ASR（LM Studio 不支援 ASR，D-13）。本機 GPU 是 RTX PRO 6000 **Blackwell（sm_120）**，挑錯 torch/vLLM build 會 `no kernel image available`。D-16 因此把「vLLM 在 Blackwell 上跑得起 Qwen3-ASR、且串流可用」定為 S-06 上線前的**硬性關卡**。本 PoC 就是把這關用閘門式、可勾選、逐關留證據的方式跑過，產出 Go/No-Go。

## 2. 目標（驗收 = 通過下列閘門）
- torch＋vLLM 在 sm_120 上能生出可用 kernel（不報 no-kernel）。
- vLLM 載得起 Qwen3-ASR-1.7B、`/v1/models` 列得到。
- 批次轉錄回合理中文逐字稿。
- **串流回 partial/final**（S-06 命脈），確認不回時間戳（NG-6）。
- VRAM reserve 行為可控、與既有佔用＋Gemma 不衝突。
- app 容器經 `host.docker.internal` 連得到、路由解析 `function=asr` 正確。

## 3. 現況快照（2026-06-26 實測，PoC 起點）
| 項目 | 實測 | 意義 |
|---|---|---|
| GPU/驅動 | RTX PRO 6000 Blackwell、driver **595.58.03 / CUDA 13.2** | 驅動層已支援 sm_120，cu128/cu130 皆相容 |
| GPU 現佔 | 97887 MiB 中已用 **22784 MiB**（他人） | VRAM 預算以「剩 ~74GB」算 |
| uv/系統py | uv 0.11.19、系統 py 3.14 | PoC 一律 `uv venv --python 3.12`（D-15） |
| `~/.venvs/asr` | **不存在** | 從 G1 起建環境 |
| Qwen3-ASR-1.7B | HF 快取已在 | 下載過關，待 SEC-1 完整性驗證 |
| vLLM :8000 | 未啟動 | 全新起 |
| 磁碟 | 剩 1.3T | 充裕 |

**決議：torch 先走 cu128（成熟、vLLM 相容性驗證最多）；cu130 當失敗分支。**

## 4. 閘門式執行清單（逐關：動作→Gate→證據→失敗分支）
- [ ] **G0 前置完整性**：Qwen3-ASR 權重無 `*.incomplete`；取 `revision/main` sha 鎖版（SEC-1），啟動帶 `--revision <sha>`。
- [ ] **G1 環境建置**：`uv venv ~/.venvs/asr --python 3.12`；裝 vLLM（cu128 torch）。Gate：install 無錯、`vllm --version` 可印。證據：vllm／torch／cuda 三版本字串（pin）。失敗：torch 非 cu128 → 顯式 cu128 index 重裝再修 vllm。
- [ ] **G2 ★核心：sm_120 kernel**：`torch.cuda.get_arch_list()` 含 `sm_120`、`is_available()` True、cuda 矩陣乘算出數字（不報 no-kernel）。失敗：換 cu130 torch；仍不行→升/換 vLLM 版本。
- [x] **G3 vLLM 載 Qwen3-ASR** ✅：原生 `vllm serve`＋`--revision <sha> --gpu-memory-utilization 0.15`；完整編譯（torch.compile＋CUDA graph）；`/v1/models` 200。關鍵：`VLLM_USE_FLASHINFER_SAMPLER=0`（繞 flashinfer sm_120 JIT 版本守衛）＋`--kv-cache-memory-bytes 8GiB`（繞共用 GPU profiling race）。
- [x] **G4 批次轉錄** ✅：POST 8.59s 中文 wav → 內容一致的中文逐字稿。需補裝 soundfile（伺服器解碼後端）。
- [x] **G5 ★S-06 命脈：串流** ✅：SSE(`stream=true`) TTFT 15ms；真 WebSocket `/v1/realtime`（`--hf-overrides` 載 realtime 架構）5s 段 partial、首 partial 5.24s；**兩路皆不回時間戳**（NG-6）。
- [x] **G6 資源 reserve** ✅：EngineCore ~15.9GiB 被 util 0.15＋kv-cache 8GiB 框住；與 ComfyUI 20G＋Gemma 36.7G 共存、剩 16.5G 無衝突。雷：孤兒 `VLLM::EngineCore` 需另殺。
- [x] **G7 app→vLLM 整合冒煙** ✅：於 app image 內 `resolve_endpoint('asr')` 取得＋容器經 `host.docker.internal:8000/v1/models` 得 200。

## 5. 🚦 Go / No-Go（S-06 解鎖閘）→ **結論：GO（2026-06-26）**
- ✅ **GO**：G2–G7 全綠，版本/env/啟動指令已 pin 回 SOP §3.B。S-06 解鎖（即時走 `/v1/realtime`、批次走 `/v1/audio/transcriptions`）。逐關證據見 `docs/dev_log/vllm-asr-poc.md` ⑨–⑭。
- ~~NO-GO（串流不行、批次行）~~：未發生，真 WebSocket 串流可用。
- ~~NO-GO（kernel 起不來）~~：未發生，cu130 在 sm_120 產出可用 kernel（G2）。

## 6. 範圍邊界（做／不做）
- **做**：建 ASR venv、驗 sm_120、起 vLLM、批次＋串流冒煙、VRAM/路由整合驗證、版本 pin 回填。
- **不做（後續 Story）**：S-04 完整前處理（DeepFilterNet/VAD）／15 分切段／落地逐字稿；S-06 WebSocket 串流實作；NLLB 即時翻譯服務（另案）；翻譯評測。

## 7. 與現有 SOP 的兩個出入（本 PoC 一併修正）
1. **`--gpu-memory-utilization 0.8` 對小模型錯**：該值是「單一 vLLM 實例吃掉的總 VRAM 比例」，0.8≈77GB，但 Qwen3-ASR 僅 ~6GB 且 GPU 已被佔 22.7GB＋Gemma 33GB → 會搶爆排擠他人。PoC 設小（~0.15）再調；`RES_CAP=0.8` 是「全體服務總上限」非單一實例 util，語意不同。
2. **安裝順序改「先 vLLM 帶 torch」**：vLLM 自帶編譯 kernel 且嚴格 pin torch，先裝 torch 易被覆寫／kernel 對不上，反更易踩 no-kernel。

## 8. 開發日誌
> 逐關證據與 Go/No-Go 結論見 `docs/dev_log/vllm-asr-poc.md`
