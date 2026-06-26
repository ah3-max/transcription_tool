# 開發日誌：裝置專屬 UX（device-specific-ux）

> 類型：開發日誌（事中／事後，逐步追加）
> 配對規劃：`docs/plan-log/device-specific-ux.md`
> 格式：原本怎麼樣 → 發生什麼 → 改了什麼 → 遇到什麼困難 → 又怎麼改 → 最後如何解決

---

**① 2026-06-26｜內網可開的裝置自適應原型 `web/proto.html`（設計預覽，未連後端）**
- 原本：裝置專屬 UX 只有 Artifact 示意（claude.ai、需外網）；使用者要「**內網實機**」能開，且依手機/平板/桌機呈現對應 UI/UX。
- 改了什麼：新增 `web/proto.html` —— 自包含單檔互動原型。用**真實 viewport 的 media query**（≤600 手機／≤1024 平板／桌機）＋ **JS 依裝置渲染不同版面**：手機＝stack/卡片/底部動作表單、平板＝master-detail 雙欄、桌機＝console/表格＋預覽。五畫面可導覽；即時翻譯逐句串流（§3.1a 留白節奏、draft→落定、A±）；設定進階「手機唯讀＋提示／平板桌機可編」。吃自家狗糧用 `100dvh`、`viewport-fit=cover`（iOS 安全區）。mock 資料、串流為模擬。
- 遇到困難：Artifact 版省略 `<!DOCTYPE>/<head>/viewport`（平台代包），但 FastAPI 直送原檔，需完整 HTML 文件，否則手機不會正確縮放。
- 又怎麼改：以 `sed` 在 `</style>` 後注入 `</head><body>`、前置 `doctype+charset+viewport`、尾附 `</body></html>`，組成完整文件寫入 `web/proto.html`。
- 最後如何解決：靜態服務為 `web/` **bind-mount**（compose `./web:/web`，`StaticFiles(html=True)` 掛 `/`）→ 免 rebuild、即時生效。驗證：容器 `stt-app` healthy；`curl localhost:3600/proto.html` → **HTTP 200、34KB**、含 `viewport` 與內容標記；結構檢查 doctype/head-close/html-close/script-close 皆正確。**內網 URL：`http://192.168.1.216:3600/proto.html`**（BIND `0.0.0.0`、APP_PORT=3600）。
- 待續：真機回饋後微調（字級／分欄比例／即時節奏）；確認設計後進 **Phase 1** 正式寫進 `index.html`（屆時 `proto.html` 留作對照或移除）。
