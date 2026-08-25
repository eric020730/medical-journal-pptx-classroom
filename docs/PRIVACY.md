# 資料安全、病人隱私與著作權

## 不可以放進公開 GitHub 的資料

- 病人姓名、出生日期、病歷號、身分證字號、聯絡方式。
- 包含識別資訊的 DICOM、檢查報告、影像截圖或教學影片。
- 未取得散布授權的期刊 PDF、補充材料或原始影像。
- 學生產生的簡報、逐字講稿、工作檔與診斷紀錄。
- API keys、登入 cookie、存取 token 與帳號密碼。

`.gitignore` 已預設排除學生 PDF、`outputs/`、`.skill-work/`、`.venv/` 和 `.env`，但任何發布前仍應人工檢查：

```bash
git status --short
git check-ignore sample-papers/my-private-paper.pdf
```

## 論文與 Figure 使用

能閱讀某篇文章，不等於有權將 PDF、Figures 或 Tables 放上公開 GitHub。課堂分享應遵循出版社授權、學校訂閱、合理使用規範與當地著作權要求。

## AI 內容複核

AI 生成的研究摘要、統計解釋、臨床建議與投影片內容，都必須對照原始論文由教師或具資格的專業人員複核。本專案不能提供醫療診斷，也不應單獨用於病人照護決策。

## 虛構範例

`sample-papers/classroom-demo-paper.pdf` 是本專案自製的虛構文章；所有作者、研究資料與結果都不是實際臨床證據。

## Logo 與品牌

原始 `v0.2.38` 技能內含 Dr. Leether Logo。公开發布前請確認你擁有重新散布該 Logo 的權利，否則應以經授權的課程 Logo 替代。
