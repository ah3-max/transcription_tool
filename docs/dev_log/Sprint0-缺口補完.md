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

## G2　模型/輔助端點不對 LAN 外露（S-01 / NFR-4・SEC-9）　【gpu_stat 完成；LM Studio 待點頭】

- **原狀**：`gpu_stat.py` 綁 `0.0.0.0:3601`、LM Studio 綁 `0.0.0.0:1234`，LAN 任一機器可直連。
- **查證（先偵察不動手）**：
  - compose 網路 `transcription_tool_default` 閘道＝`172.25.0.1`(br-25743e434e03)；docker **預設 bridge** 閘道＝`172.17.0.1`(docker0)。
  - compose 用 `extra_hosts: host.docker.internal:host-gateway`；容器內 `getent hosts host.docker.internal` → **`172.17.0.1`**。
  - ⇒ **計畫原建議「綁 compose 網路閘道 172.25.0.1」是錯的**：容器經 host-gateway(172.17.0.1) 連出、不是經專案網路閘道，綁 172.25.0.1 容器會連不到。**正確目標＝docker0 閘道 172.17.0.1**。
  - 172.17.0.1 在 docker0、172.25.0.1 在 br-xxxx，**皆非 LAN NIC**（LAN 為 eth0 192.168.1.216/22）。
  - gpu_stat **目前沒在跑**（`ss` 無 :3601、user unit inactive）；LM Studio **正在 0.0.0.0:1234 跑**。
- **改動（可控、在 repo）**：
  - `host-helpers/gpu_stat.py`：新增 `_iface_ipv4("docker0")`（stdlib ioctl SIOCGIFADDR）；綁定優先序 `GPU_STAT_HOST 明設 > 自動偵測 docker0 閘道 > 退回 0.0.0.0(印 SECURITY 警告)`。預設即安全。
  - `host-helpers/systemd/stt-gpu-stat.service`：移除 `Environment=GPU_STAT_HOST=0.0.0.0`，改靠自動偵測；加註解＋確認方式。
  - `docs/model-setup-SOP.md`：埠表「綁定」欄與啟動指令同步為「自動綁 docker0 閘道」。
- **驗收（實機，啟動自有服務驗後即停，未碰 LM Studio／防火牆）**：
  - 偵測 HOST＝`172.17.0.1`；`ss` 顯示**僅** `172.17.0.1:3601` 監聽（非 0.0.0.0）。
  - 容器 `curl host.docker.internal:3601/gpu` → **HTTP 200**（nvidia-smi 在此 host 可用，回 GPU 數字）。
  - LAN `curl 192.168.1.216:3601/gpu` → **HTTP 000（連線被拒）**＝已擋。測試服務已 kill。
- **剩餘/卡點（需你決定）**：**LM Studio（:1234，共用服務）仍對 LAN 外露**。依計畫二擇一、且動 host 前需你明確同意：
  1. LM Studio 設定關閉「Serve on Local Network」/ 綁 127.0.0.1；或
  2. host 防火牆限制 tcp 1234（及未來 8000/8001）只允許 docker 橋接子網＋127.0.0.1、其餘 LAN DROP（規則只針對這幾個埠、套用前先備份/列規則給你確認）。
  - 另：真正部署 gpu_stat（`systemctl --user enable --now stt-gpu-stat`）也屬 host 動作，待你要上線時再執行。

---

## G4　上傳深度驗證：解碼＋音訊串流＋時長上限（S-04 / SEC-2）　【2026-06-26 完成】

- **原狀**：`POST /api/jobs` 只驗副檔名白名單＋累計大小；`config.max_file_min`(120) 定義卻沒人用；偽音檔（.wav 內容是文字）也會入庫。
- **改動**：
  - `server/Dockerfile`：apt 裝 `ffmpeg`(含 `ffprobe`)；並把 apt 來源由 http 改 https（見下「困難」）。
  - `server/services/preprocess.py`（新）：`probe_duration_seconds(path)`——ffprobe(JSON、`subprocess timeout=15s`) 驗可解碼＋含音訊串流，回時長秒數；不合法丟 `BadAudio`。集中為「前處理入口」，未來 DeepFilterNet3/VAD 掛同層、避免重複解碼。
  - `server/routes/jobs.py`：落檔後、入庫前逐檔 probe；不可解碼/非音檔→`400 bad_file`、`> max_file_min*60`→`413 too_long`，兩者皆 `_cleanup` 清掉本請求所有檔（不留孤兒）。時長寫入新欄並回傳。
  - `server/models_db/db.py`：jobs 加 `duration INTEGER` 欄＋冪等遷移 `_migrate()`（既有 DB 補欄）。`_job_dict` 同步輸出 `duration`（顯示/解析全鏈路）。
  - `server/tests/test_jobs.py`：`_wav()` 改產生真正可解碼的 WAV（`wave` 模組 PCM16 mono 靜音）；新增 bad_file→400、too_long(monkeypatch max_file_min=0)→413、合法→202＋duration。
- **困難→解法**：`docker compose build` 裝 ffmpeg 時多個相依（glib/jxl/openjpeg/theora/jack…）`apt` 經 `http://deb.debian.org` 回 **403 Forbidden**；實測改 **https** 來源即全數取得（Dockerfile 內 `sed` 切換 http→https 後再 apt）。
- **驗收**：
  - `docker compose up -d --build` 成功、`ffprobe` 在 `/usr/bin/ffprobe`、health ok。
  - 容器內 `pytest`：**45 passed**（含 G4 三案；既有 S-04/S-09 全綠）。
  - 即時 app smoke：壞檔(.wav 內容是文字) → `400 {"error":"bad_file"}`，且 `/api/jobs` 無孤兒。
- **剩餘/全鏈路待辦**：
  - 與 S-04 真前處理（DeepFilterNet3/VAD，`services/preprocess.py` 後續擴充）整合時，解碼/時長應沿用本入口、勿重複解碼。
  - 前端尚未顯示時長；DB 既有 `duration` 可供 S-11 顯示用。
  - （可選）MIME 嗅探未加：ffprobe 解碼成功已強於 MIME，暫不引入 `python-magic`。

---

- _（G3、G5 待續：G3 需第二台 LAN 機器；G5 介面先行、實機整合待 S-06。）_
