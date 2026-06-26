# 開發日誌：Sprint 0 缺口補完（G1–G5）

> 類型：開發日誌（事中／事後，逐步追加）｜ 配對規劃：`docs/plan-log/Sprint0-缺口補完.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決
> 執行者：每完成一個 G 項補一條；依賴後續 Story 的部分如實標「現在做到哪、卡在 S-0x」，勿假裝完成。

---

## G1　`src_lang` 驗證（S-04 / FR-13）　【2026-06-26 完成】

- **原狀**：`POST /api/jobs` 的 `src_lang: str = Form("zh")` 只存不驗，任意字串（含 `foo`）都收進 DB。
- **發生**：稽核發現 FR-13 只允許「國語／國語＋英文／純英文」三種來源語，後端缺驗證。
- **查證**：
  - `server/routes/jobs.py:23` 既有 `VALID_LANGS={"zh","en","th"}`（那是 **out_langs** 用，含泰文）。
  - 前端 `web/index.html:430` 的「辨識語言」是 v6 雛形的 `<div class="seg">` 內 3 顆 `<button>`（國語／國語＋英文／純英文），**無 `value`**；且 `web/app.js` **不存在**＝前端尚未配線送 `src_lang`。故無「既有前端值」需要遷就。
- **改動**：
  - `server/routes/jobs.py`：新增 `VALID_SRC={"zh","zh_en","en"}`（th 非合法來源語），並在 `create_jobs` 最前面（零副作用）擋 `src_lang not in VALID_SRC` → `400 {"error":"bad_request","message":"辨識語言不支援"}`（用既有 `_err()`）。
  - `server/tests/test_jobs.py`：新增 `test_bad_src_lang_rejected`（`foo`→400；`zh_en`/`en`→202）。
- **困難/取捨**：host 無 pytest（`python`/`pytest` 皆缺），測試須在容器內跑：`docker compose exec -T stt-app sh -c "cd /app && python -m pytest tests -q"`。
- **驗收**：容器內 pytest **18 → 19 passed**（新增 1 case 全綠）；`src_lang=foo`→400、`zh/zh_en/en`→202。
- **剩餘/全鏈路待辦**：前端「辨識語言」按鈕日後配線時，務必送 `{zh,zh_en,en}` 代碼（非中文字串），與後端 `VALID_SRC` 同步——此為改欄位的「顯示／傳輸」尚未補的一段，待前端 Story（S-11）配線時一起做。

---

- _（G2–G5 待續：涉及 host 防火牆/綁定/systemd/第二台機器者，依 §2 先取得使用者明確同意再執行。）_
