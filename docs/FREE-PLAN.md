# 免費方案與低額度教學

官方文件目前說明 ChatGPT Free 包含 Codex，但功能比較表未單獨列出 Free 的完整 Skills 權限。是否能使用本機自訂 skill、可選模型，以及可用額度，必須由學生實際登入帳號驗證。

官方參考：[Codex／ChatGPT 價格與額度](https://learn.chatgpt.com/docs/pricing)。

## 第一次先確認完整簡報所需額度

```text
$medical-journal-to-pptx-classroom

請使用 full 模式，製作 40–55 張投影片。
處理 sample-papers/classroom-demo-paper.pdf，使用英文投影片及繁體中文講者備註，
保留所有重要 Figures 和 Tables，完成 QA 後輸出到 outputs。
```

本專案只支援完整的 `full` 模式；若帳號額度不足，請先執行 `journal doctor` 和 `journal smoke-test` 確認環境，或由教師示範完整簡報。

## 如果 skill 沒有出現在選單

1. 確認 Codex 開啟的是整個專案資料夾。
2. 開啟新任務或重新啟動桌面應用程式。
3. 嘗試直接輸入 `$medical-journal-to-pptx-classroom`。
4. 如果帳號不能使用 skill 選單，但 Codex 可以讀取本機專案，請嘗試：

```text
請先讀取 .agents/skills/medical-journal-to-pptx-classroom/SKILL.md，
依照其中的 full 模式處理 sample-papers/classroom-demo-paper.pdf，
製作 40–55 張英文投影片與繁體中文講者備註。
```

上述替代方式仍取決於學生帳號與目前產品提供的本機能力，不能保證對每個免費帳號都有效。

## 避免浪費額度

- 一次只加入一篇 PDF。
- 使用一段清楚的提示詞，避免反覆重新開始。
- 第一次先用三頁虛構範例。
- 不要求 AI 生圖；PDF 既有圖表擷取在本機處理，不依賴帳號是否具備圖像生成功能。
- 先用 `journal smoke-test` 確認環境正常，再開始完整 40–55 張簡報。
- 使用同一個任務續做，不要每次建立新的完整工作流程。

如果額度用完，請等待帳號額度恢復、採用學校提供的方案，或改用付費帳號。不要把 API key 當作免費替代方案；API 使用通常另行計費。

## 教學目標

免費方案適合練習：

```text
讀取文章 → 辨認 Figure／Table → 撰寫完整教學簡報 → 輸出 PPTX → 通過 QA
```

完整的 40–55 張正式 journal club 簡報，通常較適合有足夠額度的帳號。
