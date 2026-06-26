# 開發日誌：Sprint 0 收尾接線 ＋ S-04 jobs 骨架（API-01/03/05）

> 類型：開發日誌（事中／事後）｜ 配對規劃：`docs/plan-log/Sprint1-S04-jobs.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**① 2026-06-26｜接線 reserve／路由解析／503 ＋ jobs 骨架**
- 原本：S-03 的 `can_reserve` 是沒人呼叫的函式、無 `resolve_endpoint`、沒有任何地方真的回 503；`/api/jobs` 未做。（先前我誤把 S-03 這三項標完成，使用者指正。）
- 發生：需用實際消費者把零件接起來，並補 S-04 的 API-01/03 讓 Sprint 0 里程碑三條 curl 真的通。
- 改了什麼：① `services/routing.py` `resolve_endpoint(function)`→該功能 active 端點（FR-21）；② `routes/jobs.py` API-01/03/05：POST 多檔→副檔名白名單→`can_reserve` 守門（不過回 503 `error:"resource"`＋`degrade`）→id 命名落檔(uploads)→建 `queued` job；GET 清單(pagination)／單筆(progress stub)／DELETE(刪檔＋列)；③ `main` 掛 jobs router。
- 遇到困難：503 路徑要 `RES_CAP=0` 才觸發，真機資源充裕逼不出來。
- 又怎麼改：容器內以 `TestClient` monkeypatch `settings.res_cap=0` 驗 503 路徑。
- 最後如何解決：**驗證通過**——POST→202 建 `j_3c30fc83dc88`(queued)、檔案落 `/data/uploads/3c30fc83dc88.wav`（id 命名、非原檔名）；GET 清單＋pagination、單筆＋progress；`.txt`→400 `bad_file`；POST asr 端點→`resolve_endpoint('asr')` 取得；`RES_CAP=0`→POST 回 503 `error:"resource"` `degrade:true`；DELETE 清檔、uploads 歸零。**里程碑三條 curl（建立工作／查清單／設定端點）全通 → Sprint 0 里程碑達成。**
- 待續：真前處理（DeepFilterNet/VAD）／切段／ASR 為 S-04 其餘、翻譯 S-05；MIME＋實際解碼＋時長上限（SEC-2 完整版）S-04/S-13；進度真值 S-04。
