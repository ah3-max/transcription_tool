# 模型下載與啟動 SOP（stt-translate）

> 對象：在**內網主機（host）**上準備、下載、啟動各模型服務，供 app（CPU 容器）經 `host.docker.internal` 連用。
> 依據：D-04 / D-13 / D-14 / D-15 / D-16 / D-17、SEC-1、`.env`。
> 實測硬體（2026-06-26）：RTX PRO 6000 Blackwell **96GB VRAM（sm_120）**、RAM ~60GB、磁碟 2TB（剩 ~1.3TB）、8 核 Xeon 6515P。

---

## 0. 拓樸總原則（先懂這個再動手）

- **app 在純 CPU Docker 容器**（不裝 nvidia-container-toolkit、不重啟 Docker daemon → 對同主機 ~17 個生產容器零影響，D-14）。
- **所有 GPU / LLM 模型都在 host 原生跑**，app 經 `host.docker.internal` 連出。
- **隔離方式 = Python venv，不是 Docker**（D-15）。GPU 服務各用獨立 venv，避免相依（尤其 torch）互相打架。
- 模型權重一律下載到 **host 的 HF 快取 `~/.cache/huggingface/hub`**（在 2TB 卷上；vLLM / transformers 用 repo id 自動找得到）。LM Studio 例外，走它自己的模型庫。

### 埠對照（`.env`）
| 服務 | 軟體 | 埠 | 綁定 | `.env` 變數 |
|---|---|---|---|---|
| app 本體（UI＋API＋WS） | FastAPI（容器） | 3600 / 3610 | `0.0.0.0`（對內網） | `APP_PORT` |
| 文字 LLM（Gemma 31B Q8） | LM Studio（host） | 1234 | localhost 建議 | `LLM_ENDPOINT` |
| ASR（Qwen3-ASR） | vLLM（host） | 8000 | localhost 建議 | `ASR_ENDPOINT` |
| 即時翻譯（NLLB） | 自寫小服務（host） | 8001 | localhost 建議 | `LIVE_TR_ENDPOINT` |
| VRAM 量測 | `host-helpers/gpu_stat.py`（host） | 3601 | `0.0.0.0`（容器要連） | —（D-17） |

---

## 1. 模型一覽：載哪個 → 給哪個軟體 → 放哪 → 狀態

| 模型 | repo / 來源 | 用途 | 軟體・埠 | 下載體積 | 跑起來 VRAM | 狀態 |
|---|---|---|---|---|---|---|
| **Gemma 4 31B Q8** | `lmstudio-community/gemma-4-31B-it-GGUF`（Q8_0） | 批次翻譯＋後處理＋文件 | LM Studio・1234 | 31GB | ~33GB | ✅ 已就緒 |
| **Qwen3-ASR-1.7B** | `Qwen/Qwen3-ASR-1.7B` | ASR（即時串流＋批次） | vLLM・8000 | **4.7GB** | ~5–6GB | ✅ 已下載 |
| **NLLB-200-3.3B** | `facebook/nllb-200-3.3B` | 即時翻譯（中→泰直譯） | 自寫服務・8001 | **17.6GB**（fp32） | ~6.6GB（fp16）/ ~3.4GB（CT2 int8） | ✅ 已下載 |
| **MADLAD-400 7B-bt** | `google/madlad400-7b-mt-bt` | 批次翻譯**中→泰直譯**（T5・450 語） | 自寫服務（同 NLLB 型）・8001 | ~35GB（fp32，已去 gguf） | ~14GB(fp16)/~7GB(CT2) | ⬇ 下載中 |
| **Typhoon Translate 4B** | `scb10x/typhoon-translate-4b`(＋`-gguf`) | 翻譯**英↔泰**（⚠ 非中→泰） | LM Studio(GGUF)・1234 / vLLM | GGUF 2.5GB＋ST ~8GB | ~3–8GB | ⬇ 下載中 |
| DeepFilterNet3 | pip `deepfilternet` | 前處理降噪 | app 容器（CPU） | 數十 MB（自動） | — | 隨容器 |
| Silero VAD | pip `silero-vad` / torch.hub | 前處理切段 | app 容器（CPU） | ~數 MB（自動） | — | 隨容器 |
| ~~TranslateGemma 27B~~ | `google/translategemma-27b-it`（gated）/ `bullerwins/...-GGUF` | 批次翻譯備選 | — | ~28GB(Q8)/54.9GB | — | ⛔ 未選用（改用 MADLAD/Typhoon） |
| Qwen3-ASR-0.6B（備援） | `Qwen/Qwen3-ASR-0.6B` | ASR 備援 | vLLM | 1.9GB | ~2GB | 選配 |
| Whisper Large V3 Turbo（備援） | `openai/whisper-large-v3-turbo` | ASR 備援 | vLLM / transformers | ~1.6GB | ~2GB | 選配 |

> ⚠️ 上面是「下載體積」與「執行 VRAM」兩個不同概念，勿混。NLLB 官方 repo 只有 fp32 權重（17.6GB），但執行時載成 fp16 只吃 ~6.6GB；要更省更快可在 host 端用 CTranslate2 轉 int8（~3.4GB）。

---

## 2. 共用準備：下載器 venv ＋ HF 快取

下載器與各執行服務分開。系統 python 是 3.14（D-15：ML 套件未跟上，勿用），改用 `uv` 建 3.12：

```bash
# 下載器 venv（純 Python，只裝 huggingface_hub，已建好）
uv venv ~/.venvs/hf-dl --python 3.12
uv pip install --python ~/.venvs/hf-dl/bin/python huggingface_hub
export HF_HUB_DISABLE_TELEMETRY=1          # 內部隱私工具，關遙測（NG-1）
```

下載（落在 `~/.cache/huggingface/hub`，用 repo id 即可被 vLLM/transformers 找到）：

```bash
~/.venvs/hf-dl/bin/hf download Qwen/Qwen3-ASR-1.7B
~/.venvs/hf-dl/bin/hf download facebook/nllb-200-3.3B
# 備援（選配）
~/.venvs/hf-dl/bin/hf download Qwen/Qwen3-ASR-0.6B
~/.venvs/hf-dl/bin/hf download openai/whisper-large-v3-turbo
```

### SEC-1 雜湊比對（下載後務必做）
HF 的 `hf download` 會校驗每個 LFS 檔的 SHA256（etag）與 `model.safetensors.index.json` 對齊；要再保險，比對 repo 上的 commit：
```bash
~/.venvs/hf-dl/bin/hf api  /api/models/Qwen/Qwen3-ASR-1.7B/revision/main \
  2>/dev/null | python3 -c "import sys,json;print('sha:',json.load(sys.stdin)['sha'])"
# 鎖版：之後啟動一律帶 --revision <sha>，避免上游悄悄換權重
```

---

## 3. 各模型啟動 SOP

### A. Gemma 4 31B Q8 — LM Studio（:1234）✅ 已就緒
- 檔案：`~/.lmstudio/models/lmstudio-community/gemma-4-31B-it-GGUF/gemma-4-31B-it-Q8_0.gguf`（31GB，已在）。
- 確認在跑：`curl -s http://localhost:1234/v1/models | grep gemma-4-31b`
- 在 LM Studio 設「JIT load / idle TTL」對應 `IDLE_RELEASE_MIN=10`（閒置卸載省 VRAM，D-06）。
- app 端：`.env` 的 `LLM_ENDPOINT=http://host.docker.internal:1234/v1`，模型名 `google/gemma-4-31b`。

### B. Qwen3-ASR-1.7B — vLLM（:8000）⛔ 有硬關卡
> **D-16 硬關卡**：本卡是 Blackwell（sm_120），需 PyTorch cu128/130 ＋新版 vLLM，否則會 `no kernel image available`。**權重已可先下載，但能不能串流要先過 PoC。**
> 📌 **本專案 PoC 由他人負責**；下方 venv／啟動步驟僅供 PoC 負責者參考，本側只備妥權重（已下載）與指令。

1. 建 ASR 專用 venv（與 NLLB 分開）：
   ```bash
   uv venv ~/.venvs/asr --python 3.12
   # 先裝對 Blackwell 的 torch（cu128+），再裝 vLLM＋官方 ASR 包
   uv pip install --python ~/.venvs/asr/bin/python \
     --index-url https://download.pytorch.org/whl/cu128 torch
   uv pip install --python ~/.venvs/asr/bin/python vllm qwen-asr
   ```
2. PoC 驗證（D-16）：確認 torch 認得 sm_120、vLLM 載得起 Qwen3-ASR、串流可用。
3. 啟動（`qwen-asr-serve` 是官方對 `vllm serve` 的包裝；`--gpu-memory-utilization` 對應 D-17 的 reserve）：
   ```bash
   ~/.venvs/asr/bin/qwen-asr-serve Qwen/Qwen3-ASR-1.7B \
     --gpu-memory-utilization 0.8 --host 0.0.0.0 --port 8000
   ```
4. 約束：串流模式**不回時間戳**（NG-6），時間以伺服器時鐘標記；批次單段 ≤20 分鐘、每 15 分鐘切段。
5. app 端：`ASR_ENDPOINT=http://host.docker.internal:8000/v1`。

### C. NLLB-200-3.3B — 自寫小服務（:8001）⚠ 要自己包
> NLLB 是**純模型、無內建 server，且非 OpenAI 相容**（用 FLORES-200 語言碼、需 `forced_bos_token_id`）。要自寫一支服務掛 :8001。語言碼：中(簡)`zho_Hans`、中(繁)`zho_Hant`、英 `eng_Latn`、泰 `tha_Thai`。

1. 建 NLLB 專用 venv：
   ```bash
   uv venv ~/.venvs/nllb --python 3.12
   uv pip install --python ~/.venvs/nllb/bin/python \
     --index-url https://download.pytorch.org/whl/cu128 torch
   uv pip install --python ~/.venvs/nllb/bin/python transformers fastapi uvicorn sentencepiece
   ```
2. 最小服務雛形（起點，非定稿；回應外型對齊專案 `{data,error?}`）：
   ```python
   # ~/services/nllb_server.py  → 啟動：~/.venvs/nllb/bin/uvicorn nllb_server:app --host 0.0.0.0 --port 8001
   import torch
   from fastapi import FastAPI
   from pydantic import BaseModel
   from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

   MODEL = "facebook/nllb-200-3.3B"
   tok = AutoTokenizer.from_pretrained(MODEL)
   model = AutoModelForSeq2SeqLM.from_pretrained(MODEL, torch_dtype=torch.float16).to("cuda").eval()

   app = FastAPI()
   class Req(BaseModel):
       text: str
       src_lang: str = "zho_Hans"     # 來源固定中文（一對多扇出由 app 端對每個目標各打一次，D-03）
       tgt_lang: str                  # tha_Thai / eng_Latn ...

   @app.post("/translate")
   def translate(r: Req):
       tok.src_lang = r.src_lang
       enc = tok(r.text, return_tensors="pt").to("cuda")
       out = model.generate(**enc,
           forced_bos_token_id=tok.convert_tokens_to_ids(r.tgt_lang), max_new_tokens=512)
       return {"data": {"translation": tok.batch_decode(out, skip_special_tokens=True)[0]}}
   ```
3. **更快更省的替代（建議正式採用）**：CTranslate2 int8。在 host 端從官方權重本地轉換（不引第三方權重，符合 SEC-1）：
   ```bash
   uv pip install --python ~/.venvs/nllb/bin/python ctranslate2
   ~/.venvs/nllb/bin/ct2-transformers-converter --model facebook/nllb-200-3.3B \
     --output_dir ~/models/nllb-3.3b-ct2-int8 --quantization int8
   # 服務改用 ctranslate2.Translator 載 ~/models/nllb-3.3b-ct2-int8，VRAM ~3.4GB、延遲更低
   ```
4. app 端：`LIVE_TR_ENDPOINT=http://host.docker.internal:8001`（注意**無 `/v1`**，非 OpenAI 相容）。

### D. 前處理 DeepFilterNet3 + Silero VAD — app 容器內（CPU）
- 不用手動下載：寫進 `server/requirements.txt`（`deepfilternet`、`silero-vad`），容器首跑時自動抓、CPU 執行。
- **內網/離線注意**：若主機不能對外連網抓首包，需把這兩個權重快取**預先放進映像或掛載 volume**（HF / torch.hub 快取），避免容器起不來。

### E. MADLAD-400 7B-bt — 批次中→泰直譯（:8001 同 NLLB 型）⚠ 要自己包
> T5 seq2seq、450 語、**直接吃中文來源輸出泰文**（與 NLLB 同類，非 OpenAI 相容）。
> 用法：來源句前綴目標語碼 `<2th>`（泰）/`<2en>`（英）；Apache-2、免授權。
1. venv 同 NLLB（可共用 `~/.venvs/nllb`）：`transformers`＋`sentencepiece`（spiece.model）。
2. 最小服務（transformers）核心：
   ```python
   from transformers import T5Tokenizer, T5ForConditionalGeneration
   tok = T5Tokenizer.from_pretrained("google/madlad400-7b-mt-bt")
   model = T5ForConditionalGeneration.from_pretrained("google/madlad400-7b-mt-bt",
            torch_dtype="float16", device_map="cuda").eval()
   def tr(text, tgt="th"):
       ids = tok(f"<2{tgt}> {text}", return_tensors="pt").input_ids.to("cuda")
       return tok.decode(model.generate(ids, max_new_tokens=512)[0], skip_special_tokens=True)
   ```
3. 更省更快：CTranslate2 支援 MADLAD，`ct2-transformers-converter --model google/madlad400-7b-mt-bt --quantization int8`（~7GB）。
4. 下載已去掉 repo 內附 gguf（省 ~13GB）；要 llama.cpp 跑再單抓 `model-q6k.gguf`。

### F. Typhoon Translate 4B — 翻譯**英↔泰**（注意語向）
> ⚠️ **方向限制**：官方定位 **英↔泰**，**不**為中→泰設計；本管線來源是中文，故 Typhoon **不放中→泰主流程**（硬走 zh→en→th 是串接，違反 D-03）。適用：th→en、或英文來源情境、或品質參照。
- **LM Studio（最快）**：GGUF 已下載到 `~/.lmstudio/models/scb10x/typhoon-translate-4b-gguf/`（Q4_K_M 2.5GB），LM Studio 掃到即可載；OpenAI 相容、系統提示 `Translate the following text into Thai`。
- **全精度**：`scb10x/typhoon-translate-4b`（safetensors，Gemma3 架構）走 vLLM/transformers。
- ~~TranslateGemma 27B~~：官方 gated、54.9GB，**未選用**，由 MADLAD/Typhoon 取代評測角色。

---

## 4. 啟動順序與健康檢查

```bash
# 1) VRAM 量測服務（容器要靠它，D-17）
GPU_STAT_PORT=3601 GPU_STAT_HOST=0.0.0.0 python3 host-helpers/gpu_stat.py &
# 2) LM Studio（:1234，常駐或 JIT）
# 3) 需要 ASR 時才起 vLLM（:8000）；需要即時翻譯才起 NLLB（:8001）——按需起、閒置釋放（D-06）
# 4) app（容器）
docker compose up -d

# 健康檢查
curl -s http://localhost:3600/api/health
curl -s http://localhost:1234/v1/models        | head
curl -s http://localhost:8000/v1/models        | head     # ASR 起來後
curl -s -X POST http://localhost:8001/translate -H 'content-type: application/json' \
     -d '{"text":"早安","tgt_lang":"tha_Thai"}'            # NLLB 起來後
curl -s http://localhost:3601/gpu                          # VRAM 數字
```

### VRAM 預算（96GB）
| 同時常駐 | 約用量 |
|---|---|
| Gemma 31B Q8 ＋ Qwen3-ASR ＋ NLLB(fp16) | 33 + ~6 + ~7 ≈ **46GB** ✅ 充裕 |
| 再加 TranslateGemma 27B | ≈ 74GB（接近，靠動態 reserve＋閒置釋放錯開，D-06） |
- `RES_CAP=0.8`（上限 80%）、`IDLE_RELEASE_MIN=10`（閒置 10 分鐘卸載顯卡）。vLLM 的 reserve 交 `--gpu-memory-utilization`。

---

## 5. 疑難排解
- **`no kernel image available`（vLLM/torch）**：torch 不含 sm_120 kernel → 換 cu128/130 的 torch，重做 D-16 PoC。
- **`externally-managed-environment`（PEP 668）**：別動系統 python，一律走 `uv venv` 隔離。
- **系統 python 是 3.14**：ML 套件未跟上，所有服務 venv 固定 **3.12**（D-15）。
- **容器連不到 host 模型**：確認 `docker-compose.yml` 的 `extra_hosts: host.docker.internal:host-gateway`，且 host 服務綁得讓 gateway 連得到。
- **NLLB 譯文是空的/語言錯**：檢查 `src_lang`/`tgt_lang` 是否用 FLORES-200 碼（`zho_Hans` 等），`forced_bos_token_id` 是否設對。

---

## 6. 開機自啟（systemd user 服務，免 sudo）
**venv 本身沒有開機自啟**——它只是隔離的 Python 環境。要開機自動跑服務靠 systemd。
本機 `systemd 259`、使用者 `Linger=yes` 已開 → **user 級服務開機即起、不需登入、免 sudo**。

⚠️ 設計取捨（D-06）：GPU 模型（ASR/NLLB）設計為**按需起＋閒置釋放**，不建議無腦開機常駐。
- ✅ 建議常駐自啟：`gpu_stat`（:3601，輕量、app 依賴它量 VRAM）。
- ✅ app 容器：已由 `docker-compose.yml` 的 `restart: unless-stopped` 顧到（Docker 開機起則隨之起）。
- 🟡 NLLB（:8001）：僅 CT2 int8（~3.4GB）才較適合常駐；否則按需起。
- ⛔ ASR/vLLM：不放開機自啟（按需起；PoC 由他人負責）。

安裝（範本在 `host-helpers/systemd/`）：
```bash
mkdir -p ~/.config/systemd/user
cp host-helpers/systemd/stt-gpu-stat.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now stt-gpu-stat      # 開機自啟 ＋ 立即啟動
systemctl --user status stt-gpu-stat            # 確認；日誌：journalctl --user -u stt-gpu-stat -f
```
- NLLB 要常駐：另備 `stt-nllb.service` 範本，同法 enable（先完成 §3.C 的 venv 與服務程式）。
- LM Studio：依現行方式（GUI 或 `lms server start`）；要服務化可比照另寫 unit。

---

## 變更紀錄
- 2026-06-26：建立。下載 Qwen3-ASR-1.7B（4.7GB）＋ NLLB-200-3.3B（17.6GB）到 HF 快取；確認 Gemma 31B Q8 已就緒；下載器 venv `~/.venvs/hf-dl`（uv, py3.12, huggingface_hub 1.21.0）。
- 2026-06-26：補 §6 開機自啟（systemd user 服務）＋ `host-helpers/systemd/` 範本（gpu-stat／nllb）；標記 D-16 PoC 由他人負責；泰文模型 TranslateGemma 來源待使用者選定（§1/§3.E）。
- 2026-06-26：泰文模型定案——**改用 MADLAD-400 7b-mt-bt（中→泰直譯，§3.E）＋ Typhoon Translate 4B（英↔泰，§3.F）**，TranslateGemma 未選用。下載 MADLAD 7b-bt safetensors（~35GB，去 gguf）、Typhoon GGUF（LM Studio，2.5GB）＋safetensors（~8GB）。Qwen3-ASR／NLLB 已下載完成。
