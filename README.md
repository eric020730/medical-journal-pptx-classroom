# 論文 PDF → PowerPoint

**唯一流程：把本專案連結交給本機 Codex → 自動準備環境與 skill → 提示提供 PDF → 製作簡報。**

專案連結：<https://github.com/eric020730/medical-journal-pptx-classroom>

## 學生只做這些事

先登入可執行本機工作的 Codex，選一個可寫入的空白本機資料夾。把上面的 GitHub 連結貼進去即可開始引導；需要確認安裝意圖或下載／執行權限時，依提示批准。Codex 準備完成後會請你提供論文 PDF，收到可讀取的論文後接續製作。

為了明確表達安裝意圖，也可以把連結和這一句一起貼上：

> 請依 CODEX-START.md 自動安裝本機環境、匯入並讀取 skill；完成後提示我提供 PDF，收到論文後直接製作簡報。

不用學生先下載 ZIP、安裝 Python/Git/Homebrew/WinGet、操作終端機，或手動複製隱藏資料夾。

## 給讀到此頁的 Codex

**立即讀取同一版本的 [CODEX-START.md](CODEX-START.md)，進入安裝引導；不要只介紹專案或丟回一份手動安裝教學。**

只有網址不代表已授權執行軟體：尚無安裝意圖時，用一句話確認；已有安裝要求就不要重複詢問。尊重本機批准程序、上層工作資料夾規則及機構政策。遠端 Cloud 或一般聊天沒有學生電腦的本機執行權限，請先引導開啟 Local 工作資料夾。

一般專案網址使用 `main`，先解析為本次固定 commit，再取得完整專案。只有一套 repository skill，不使用歷史 Releases、教學分支或其他全域安裝路線。

## 會得到什麼

**40–55 張英文投影片、每頁繁體中文講者備註、原文 Figures／Tables，以及原有圖片與建檔前後 QA。** 最終 PPTX 放在 `outputs/`，中間素材與規格留在 `.skill-work/`。不捏造原文沒有的數值、作者或結論；完成後仍須人工對照原文。

技能位於 `.agents/skills/medical-journal-to-pptx-classroom/`，匯入範圍只在目前專案。Codex 必須實際讀取完整 `SKILL.md`；檔案存在、選單出現或本機測試通過，都不能代替模型讀取。

安裝使用專案內 `.bootstrap/` 與 `.venv/`，不更改系統 Python、全域 PATH、其他 skills 或安全設定。第一次需要網路與足夠 Codex 額度；不需要 API key，不使用 AI 生圖。Microsoft PowerPoint 不是建立 PPTX 的必要條件。

LibreOffice／Poppler 是選用工具，不阻擋第一份 PPTX。缺少時必須明確標示 PDF 匯出／視覺檢查未執行。技術 smoke-test 不是完整論文簡報，也不代表帳號額度、教室網路或學生操作已通過驗收。

## 必要文件

[Codex 操作流程](CODEX-START.md) · [問題處理](docs/TROUBLESHOOTING.md) · [隱私與內容複核](docs/PRIVACY.md) · [授權責任](NOTICE.md)

只使用允許處理的論文，不公開提交 PDF、成品、病人個資或帳密。AI 會理解論文內容，不能宣稱全文完全離線或不送到模型。

維護者：根目錄 `VERSION` 是專案發行版本。`python tools/release_version.py` 檢查版本一致性；`python tools/package_release.py` 只產生一種完整專案包。CI 驗證三平台自動安裝、回歸測試與 ZIP 白名單。舊教材及舊安裝路線已從目前版本移除，歷史僅留在 Git 記錄。
