# 9/14 教師流程與備援

## 課程目標

每組至少完成：辨識正確來源 PDF、啟動本機 skill、理解 Figure/Table 處理、核對一張結果投影片與繁中講稿。**不把每個人當場完成 40–55 張當成唯一及格標準。**

## 課前固定版本

發給全班同一份 `medical-journal-pptx-classroom-teaching-2026.09.14-r1.zip` 與 `.sha256`；不要發 Releases/latest 作為這堂課的下載入口。程式碼基線是 `ee5f0975f403d1edb0e7e1e244482b1fdc136295`，實際打包 commit 在 `TEACHING-BUILD.json`。保留該 ZIP，不要課前追 main。

若 GitHub Actions 有此教材建置的成功紀錄，確認 commit 一致後下載 artifact 中的 ZIP；Actions artifact 有保存期限，請另存至學校核准的位置。只有教材檔與程式碼固定，套件安裝仍需網路與相容的 Python。

## 9/12–9/13 要完成的事

- 發送 `CLASSROOM-ANNOUNCEMENT.txt`，收作業系統、doctor、smoke-test、Codex 讀取 skill 與執行本機 doctor 的結果。不收密碼、完整診斷原文或病人資料。
- **用教室實際網路與至少一台 Mac、一台 Windows 做安裝驗收**。CI 的成功不是教室網路、登入或管理員權限的驗證。
- 準備一台已登入且能生成簡報的教師電腦；確認外接螢幕只顯示投影片，講稿留在教師畫面。
- 用虛構示範 PDF 先跑一次 full 流程並人工複核。若沒有完成 full，將備援標為「技術 smoke 範例」，不能把 5 張 smoke 簡報宣稱為完整論文轉換成果。
- 備妥原始 PDF、已完成 PPTX、相同版本的 deck_spec / QA 結果，以及三個要比較的頁面：結果數字、Figure、繁中講稿。只存授權素材，不公開上傳真實期刊或病人資料。

## 三組分流（人工判定）

| 組別 | 判定條件 | 課堂安排 |
| --- | --- | --- |
| A：可實作 | doctor 必要項目通過 + smoke-test 通過 + Codex 可讀 skill 且可跑本機 doctor | 一篇 PDF、一個任務，開始 full；繼續監看額度 |
| B：部分工具缺少 | A 的核心條件通過，但 LibreOffice / Poppler 不完整 | 先產生 PPTX，明確記錄 PDF / 視覺檢查缺項 |
| C：需協助 | 必要套件、登入、硬體相容或本機權限任一未過 | 與 A 同學共看操作或教師示範；不分享帳密、不繞過政策 |

新檢核器永遠保留 `CODEX_UNVERIFIED`，不自動替你判成 A 組。App 未被 doctor 自動找到也不是斷言 App 不存在。

## 建議 90 分鐘課程（教學配置，非生成耗時保證）

| 時段 | 活動 | 可觀察成果 |
| --- | --- | --- |
| 0–10 分 | 看一份成品，說明 PDF → skill → 本機工具 → PPTX | 知道 AI 與 Python 各負責什麼 |
| 10–20 分 | 確認課前檢核、分成 A/B/C | 全班不一起卡在安裝 |
| 20–30 分 | 只讀驗證提示詞；核對 PDF 路徑及虛構標記 | Codex 確實在正確專案工作 |
| 30–50 分 | A/B 啟動一次 full；C 共看操作 | 一篇 PDF、一個工作階段 |
| 50–70 分 | 以教師備援檔核對數字、Figure/panel 與備註 | 無須等待所有人生成完畢 |
| 70–85 分 | 看 QA 結果、練習中斷續作、討論限制 | 分清技術 QA 和人工內容複核 |
| 85–90 分 | 回報檔案位置、成功項目、待處理項目 | 留下可追蹤成果，不只說「完成了」 |

## 當場救援順序

每次先問「卡在哪一關」，不要直接整個重裝。教師／助教可把單一問題處理上限設定為 5 分鐘，超過先分流，再於課後處理。

| 症狀 | 優先處理 | 不應做 |
| --- | --- | --- |
| 雙擊 Mac 安裝檔沒權限 | 核對來源，在專案終端機執行 `bash setup-macos.command` | 關閉 Gatekeeper |
| Windows 沒 winget／被政策擋 | 洽資訊人員；改共看操作 | 關閉防毒、改執行政策規避組織限制 |
| 只有 LibreOffice/Poppler 缺少 | 必要套件已在時走文件中的 skip-system；接受 PPTX-only | 說「不能產生 PowerPoint」 |
| skill 選單不出現 | 重開任務、核對根目錄、直接讀 SKILL.md | 斷言免費帳號一定不能使用 |
| 額度不足 | 保留同一任務與 `.skill-work`，先看教師成品 | 反覆從頭重跑或要求 API key |
| 安裝腳本成功但 Codex 無法執行 | 核對本機資料夾、Windows native、針對單一安全操作批准 | 要求全面 full access |

## 操作截圖驗收

目前教材的步驟是文字操作指南，**未偽造任何 Mac / Windows / Codex 實機畫面**。請由教師在自己的已授權電腦補拍三張：

1. 已解壓縮的根目錄，同時看得到 setup、check-classroom、sample-papers、outputs。
2. Codex 已選取教材資料夾，且回覆成功讀取 skill。截圖遮住帳號與其他專案。
3. 檢核器結果畫面，保留 `LOCAL_...` 和 `CODEX_UNVERIFIED`，遮住個人路徑。

可在課堂直接示範這三個畫面；不要把官方頁面的不同版本示意介面當作本次成功驗證的證據。

## 教師驗收清單

- [ ] 確認 ZIP 與 SHA-256 相符，來源 commit 可追溯。
- [ ] 教室 Mac 真機安裝與 Codex 驗證完成。
- [ ] 教室 Windows 真機安裝與 Codex 驗證完成。
- [ ] 至少一個免費帳號完成本機 skill 驗證。
- [ ] 已準備完整 full 備援成品，或明確標示只有技術 smoke 範例。
- [ ] 已人工核對數字、圖表、推論／原始研究區別與備註。
- [ ] 已告知所有同學 A/B/C 分流，不共用帳密。

## 來源

專案：`docs/QUICKSTART-MAC.md`、`docs/QUICKSTART-WINDOWS.md`、`tools/classroom.py`、`.agents/skills/medical-journal-to-pptx-classroom/SKILL.md`（上述基線 commit）。

官方產品說明核對於 2026-09-12：
- https://learn.chatgpt.com/docs/app
- https://learn.chatgpt.com/docs/windows/windows-app
- https://learn.chatgpt.com/docs/build-skills
- https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
