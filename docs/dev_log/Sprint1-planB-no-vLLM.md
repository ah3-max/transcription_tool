# 開發日誌：Plan B — S-05 批次翻譯扇出服務（不依賴 vLLM）

> 類型：開發日誌 ｜ 配對規劃：`docs/plan-log/Sprint1-planB-no-vLLM.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**① 2026-06-26｜translate.py 扇出 ＋ pytest ＋ 真機冒煙**
- 原本：S-04 核心／S-06 卡 vLLM（PoC 並行中）；翻譯能力尚未存在。
- 發生：趁 PoC 進行，做不依賴 ASR 的 S-05 翻譯服務（走已就緒的 LM Studio Gemma）。
- 改了什麼：
  - `services/translate.py`：`translate_fanout(zh, targets)` 對**每個**目標語言獨立呼叫 `batch_tr` 端點（OpenAI `/chat/completions`），**扇出不串接**（D-03）；`zh` 來源直接帶過；system prompt 把逐字稿當「資料」、與指令分離（SEC-4）；無端點 → `TranslateError`（不 500）。
  - `server/tests/test_translate.py`：無端點報錯、扇出每語言各一次且皆從源文、注入隔離 prompt → **pytest 18 passed**。
  - 註冊真實 `batch_tr` 端點：LMS `google/gemma-4-31b`（`host.docker.internal:1234`，spec 批次翻譯預設）。
- 遇到困難：真機呼叫先連 400 `Failed to load model "google/gemma-4-31b". Operation canceled`。查 `/api/v0/models`：該 31B 為冷啟動 JIT 載入中被取消；其餘（translategemma-27b、typhoon-4b…）皆 `not-loaded`。
- 又怎麼改：等 31B 暖機（狀態轉 `loaded`）後重試；並以 system+user payload 直打 LMS 確認 payload 本身被接受（200）。
- 最後如何解決：**驗證通過**——`translate_fanout('今天早上王先生血壓偏高，需要持續觀察。', ['zh','th','en'])` 回：
  - `th`：`เมื่อเช้านี้คุณหวังมีความดันโลหิตค่อนข้างสูง จำเป็นต้องเฝ้าสังเกตอาการอย่างต่อเนื่อง`（正確泰文）
  - `en`：`Mr. Wang's blood pressure was slightly high this morning and requires continuous observation.`
  - `zh`：原文帶過。扇出（各自從源文、不串接）成立。
- 待續／提醒：
  ① 冷啟動 JIT 載入會有暫態 400 → S-04 worker 整合時對「模型載入中」錯誤加重試/等待。
  ② 譯文 `outputs` 落檔待 S-04 worker（需先定 outputs 儲存區）。
  ③ 整條 upload→ASR→翻譯端到端待 S-04 worker。
  ④ 中→泰品質正式評比屬 S-12（LMS 另有 `translategemma-27b-it`、`typhoon-translate-4b` 可比較）。
