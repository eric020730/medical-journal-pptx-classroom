# 9/14 課程：從這裡開始

本次統一使用 **classroom 專案版**，不要另裝全域整合版，也不要在課前自行更新程式碼。
課程日期：2026-09-14（一）；教材版：2026.09.14-r1。

**先下載老師提供的完整 ZIP，全部解壓縮，再用瀏覽器開啟 [學生操作指南](docs/CLASSROOM-STUDENT-GUIDE.html)。**
GitHub 預覽 HTML 若只顯示原始碼，請使用已解壓縮的本機檔案，不要只另存單一網頁。

| 你現在要做什麼 | 開啟哪個檔案 |
| --- | --- |
| 第一次安裝、確認資料夾、貼提示詞 | [學生操作指南](docs/CLASSROOM-STUDENT-GUIDE.html) |
| 一頁課前檢核，可列印 | [課前檢核表](docs/CLASSROOM-CHECKLIST.html) |
| 老師安排分流與備援 | [教師流程](docs/CLASSROOM-INSTRUCTOR.md) |
| 貼到班群的通知 | [課前通知](docs/CLASSROOM-ANNOUNCEMENT.txt) |

## 學生只走這條路

1. 使用自己的帳號登入可開啟本機資料夾的 Codex 客戶端。先確認官方支援你的作業系統與處理器；本機 Python 工具支援某系統，不代表桌面 App 一定支援同一硬體。
2. 把整個教材 ZIP 解壓縮至可寫入的資料夾。保留 `.agents` 等隱藏檔案。
3. Mac 雙擊 `setup-macos.command`；Windows 雙擊 `setup-windows.cmd`。安裝會下載套件；這不是離線免安裝包。
4. 安裝完成後，Mac 雙擊 `check-classroom-macos.command`；Windows 雙擊 `check-classroom-windows.cmd`。
5. 在 Codex 開啟**同一個專案根目錄**，執行學生指南的「只讀驗證提示詞」。不要先產生完整簡報。
6. 回報：作業系統、教材版、`doctor` 結果、`smoke-test` 結果、Codex 是否讀到 skill、是否能執行本機指令。

本機檢核不消耗 Codex 模型額度，也不能驗證登入、skill 載入或剩餘額度。檢核結束的 `CODEX_UNVERIFIED` **不是錯誤**，表示仍需完成第 5 步。

## 課堂唯一生成指令

```text
$medical-journal-to-pptx-classroom

請使用 full 模式處理 sample-papers/classroom-demo-paper.pdf。
製作 40–55 張英文教學投影片，每頁附繁體中文講者備註。
明確標示文章及數據皆為虛構教學資料，不是真實臨床證據。
保留重要 Figures、Tables、panel labels 與正確影像灰階方向。
通過建檔前及建檔後 QA 後，將最終 PPTX 放在 outputs。
缺少 PDF 匯出工具時仍先交付 PPTX，並說明未完成的檢查。
```

## 版本與分發

本教材基於 `ee5f0975f403d1edb0e7e1e244482b1fdc136295` 加上教學層修改；實際建置 commit 與逐檔雜湊記在 ZIP 的 `TEACHING-BUILD.json` / `RELEASE-MANIFEST.txt`。
「固定版本」指程式碼與教材，不包含固定的帳號額度、App 版本或離線 Python 套件。不要把它叫作已發布的整合版 v4.4.0。

老師可執行 `python tools/package_teaching_kit.py` 重新打包；只追加明確列入白名單的教材，不會收集學生論文、輸出簡報或個人診斷資料。

官方說明（核對日期 2026-09-12）：[桌面 App](https://learn.chatgpt.com/docs/app)、[Windows](https://learn.chatgpt.com/docs/windows/windows-app)、[Skills](https://learn.chatgpt.com/docs/build-skills)、[方案與額度](https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan)。
