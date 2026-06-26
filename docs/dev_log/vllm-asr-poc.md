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
| G3 vLLM 載 Qwen3-ASR | 🔄 進行中 | arch Qwen3ASRForConditionalGeneration vLLM 0.23 原生支援；無 wrapper、走 vllm serve；啟動中 |
| G4 批次轉錄 | ⬜ 待跑 | |
| G5 ★串流 partial/final | ⬜ 待跑 | |
| G6 資源 reserve | ⬜ 待跑 | |
| G7 app→vLLM 整合 | ⬜ 待跑 | |
| 🚦 Go/No-Go | ⬜ 未定 | |

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

<!-- 後續逐關 append：G3 收尾 / G4 ... 各一段「原本→發生→改了→困難→又怎麼改→最後如何解決」 -->
