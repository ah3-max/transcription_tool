# 開發日誌：模型下載與啟動準備（含 SOP、開機自啟）

> 類型：開發日誌（事中／事後，逐步追加）
> 配對規劃：`docs/plan-log/model-download-setup.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**① 2026-06-26｜盤點現況 + 下載必載模型 + 寫 SOP**
- 原本：規格已定模型分工，但 host 上實際只有 LM Studio 在跑；ASR/NLLB 未下載、未啟動。
- 發生：實測 host 現況——GPU RTX PRO 6000 Blackwell 96GB（現用 22.6GB）、磁碟剩 1.3TB；LM Studio:1234 已在跑且 **Gemma 4 31B Q8_0（31GB）已就緒**；vLLM:8000／NLLB:8001 皆未起、未下載。校正體積認知：NLLB `usedStorage` 顯示 42GB 是含歷史版本，**main 實際 17.6GB（fp32 三分片）**；先前口頭「~7GB」其實是 fp16 執行 VRAM、非下載體積。
- 改了什麼：① 用 `uv` 建下載器 venv `~/.venvs/hf-dl`（py3.12 + huggingface_hub 1.21.0）；② 背景下載 `Qwen/Qwen3-ASR-1.7B`（4.7GB，已完成）、`facebook/nllb-200-3.3B`（17.6GB，收尾中）到 `~/.cache/huggingface/hub`，關 HF 遙測（NG-1）；③ 寫《模型下載與啟動 SOP》`docs/model-setup-SOP.md`（模型一覽、各模型啟動步驟、SEC-1 雜湊比對、VRAM 預算、疑難）。
- 遇到困難：(a) 系統 `python3 -m venv` 失敗——缺 `python3.14-venv`（無 ensurepip）；(b) `pip3 install --user` 被 PEP668（externally-managed）擋；(c) TranslateGemma 官方 repo `google/translategemma-27b-it` 為 **gated（401、需手動接受授權）**、且 54.9GB。
- 又怎麼改：(a)(b) 改用既有 `uv` 建 3.12 venv，繞開 ensurepip 與 PEP668；(c) 列出替代——社群 GGUF `bullerwins/translategemma-27b-it-GGUF` 公開可下載（Q8_0 28.7GB，入 LM Studio），來源取捨交使用者選定。
- 最後如何解決：必載兩顆下載**已完成並驗證完整**（Qwen3-ASR 4.4GB／2 safetensors 分片、NLLB 17GB／3 bin 分片，皆無 `.incomplete` 殘檔），落 `~/.cache/huggingface/hub`。Gemma Q8 確認已在；SOP 與 systemd 範本就緒。**待補：SEC-1 雜湊/commit 鎖版核對。**
- 待續：① **泰文翻譯模型：使用者表示「除了 Gemma 還有另一個」、非 TranslateGemma**；查遍 spec/docs 僅列 NLLB／Gemma 4／TranslateGemma 三顆，NLLB 已下載——待使用者指認具體模型（可能為 spec 外的泰語特化模型）後再下載；② **vLLM-on-Blackwell PoC（D-16）由他人負責**——本側只備權重與 SOP，不設置 ASR 服務；③ NLLB 服務程式（transformers 雛形／建議 CT2 int8）為後續實作；④ 若要 `gpu_stat` 開機自啟，安裝 `host-helpers/systemd/stt-gpu-stat.service`（user 服務、Linger 已開、免 sudo）。

**② 2026-06-26｜開機自啟（systemd user 服務）**
- 原本：服務都靠手動啟動；使用者問「venv 有沒有開機自啟」。
- 發生：venv 只是隔離環境、無自啟能力；查得本機 `systemd 259`、使用者 `Linger=yes` 已開 → user 級服務可開機即起、免登入、免 sudo。
- 改了什麼：新增 `host-helpers/systemd/stt-gpu-stat.service`（gpu_stat:3601，stdlib＋系統 python3）與 `host-helpers/systemd/stt-nllb.service`（範本、預設不啟用）；SOP 補「開機自啟」章節與安裝指令。
- 遇到困難：開機自啟與 D-06「按需起＋閒置釋放」有張力——GPU 模型不該無腦常駐。
- 又怎麼改：定調——只建議 `gpu_stat`（輕、app 依賴）常駐自啟；app 容器已由 compose `restart: unless-stopped` 顧到；GPU 模型（ASR/NLLB）按需起，NLLB 範本標註僅 CT2 int8 才較適合常駐。
- 最後如何解決：範本與文件就緒，**實際 enable 與否交使用者決定**（觸及 host init、共用生產主機，本側不擅自啟用）。

**③ 2026-06-26｜泰文翻譯模型定案：MADLAD-400 ＋ Typhoon**
- 原本：泰文翻譯模型懸而未決；先前誤以為使用者要 TranslateGemma。
- 發生：使用者澄清「除了 Gemma 還有另一個」、指名 **Typhoon（SCB10X）** 與 **MADLAD-400（Google, T5）** 兩顆。查證：MADLAD `google/madlad400-{3b,7b-mt-bt,10b}` 皆 Apache-2 公開（3b 15.7GB／7b-bt 44.7GB／10b 57.7GB，含內附 gguf）；Typhoon `scb10x/typhoon-translate-4b`(＋`-gguf`) 公開（resolve 307；HF models API 對 scb10x 抽風，改用 `list_repo_files` 取檔名）。
- 改了什麼：背景下載 ① Typhoon GGUF `typhoon-translate-4b-q4_k_m.gguf`（2.5GB）→ **LM Studio 模型庫** `~/.lmstudio/models/scb10x/...`（立即可載）；② Typhoon 完整 safetensors（~8GB）→ HF 快取；③ **MADLAD-400 7b-mt-bt** safetensors（~35GB，`--exclude "*.gguf"` 省 ~13GB）→ HF 快取。SOP §1 表＋§3.E（MADLAD）/§3.F（Typhoon）補服務方式，TranslateGemma 標未選用。
- 遇到困難：(a) Typhoon Translate 官方定位 **英↔泰**，但本管線來源是**中文**——直接拿來做中→泰不對位；(b) Typhoon GGUF 只有單一量化 Q4_K_M（無 Q8），純走 LM Studio 品質受限；(c) MADLAD 尺寸三選一（3b/7b-bt/10b）體積差距大。
- 又怎麼改：(a) 明確分工——**中→泰直譯交 MADLAD（與 NLLB 同類、直吃中文）**，Typhoon 僅作英↔泰／參照，不入中→泰主流程（守 D-03 不串接）；(b) 同時抓 Typhoon 全精度 safetensors 供需要高品質時走 vLLM/transformers；(c) 取品質甜蜜點 **7b-mt-bt**（back-translation 調校），3b（省）/10b（最佳）列為可換選項告知使用者。
- 最後如何解決：下載背景進行中（ID bq7hqxu20）；落點與服務對應已寫入 SOP。**待補：下載完成後雜湊/完整性核對；MADLAD/NLLB 的 :8001 服務包裝（transformers／CT2 int8）正式實作另案。**
