# 規劃：S-09 匯出（docx/md/txt）與批次歷史

> 建立：2026-06-26 ｜ 類型：規劃 ｜ 配對開發日誌：`docs/dev_log/Sprint2-S09-export-history.md`（動工後建）
> 對應：FR-10/16/20/25、NG-3、設計 §5 API-04；依賴 S-05、S-08
> Plan B 可做性：✅ 匯出機制現在可做（python-docx，純後端）；批次歷史「可下載產出」部分依賴 S-04/S-05 落檔

## 1. 想解決什麼問題
各處統一「選格式下拉＋匯出鈕」，把產出（逐字稿/翻譯/文件）匯出成 docx/md/txt（**不做 PDF**，NG-3/D-05）；批次歷史列出過往轉入與可下載產出。

## 2. 要收斂的目標（驗收）
- 三種格式都能正確下載、無 PDF 選項。
- 歷史記錄可重新下載既有產出。
- API-04 `GET /api/jobs/{id}/export?fmt=docx|md|txt&lang=zh|th|en`。

## 3. 怎麼改、為什麼
- `services/export.py`：`render(content, fmt)` → txt（純文字）/md（markdown）/docx（python-docx，套愛愛院字級/標題樣式 §7.2）。
- API-04 匯出端點：依 ref 的 `outputs`（transcript/translation/record）取內容 → render → 串流下載（`Content-Disposition`，檔名用 server id 不含原檔名）。
- 批次歷史：`GET /api/jobs` 已有（清單＋pagination）；補「可下載產出」連結（指向 outputs）。
- 為什麼：python-docx 穩定（D-05）；統一匯出介面（FR-25）。

## 4. 範圍邊界（做 / 不做）
- **做**：`export.py` 三格式 render＋API-04＋pytest（產出 docx/md/txt 可開）。
- **不做**：PDF（NG-3）；真實內容來源（逐字稿/翻譯）需 S-04/S-05 的 outputs 落檔（先用既有 outputs 或種子內容測 render）；前端匯出 UI 屬 S-11。

## 5. 驗收清單
- [ ] `render` 出 txt/md/docx，docx 可正常開啟、有標題樣式
- [ ] API-04 三格式下載、無 PDF 選項
- [ ] pytest：三格式各驗一次
- [ ] 歷史（job 清單）可列既有產出

## 6. 開發日誌
> 見 `docs/dev_log/Sprint2-S09-export-history.md`（動工後逐步追加）
