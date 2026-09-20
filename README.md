# 論文 PDF → PowerPoint

**唯一流程：把本專案連結交給本機 Codex → 自動準備完整品質環境與 repository skill → 提示提供 PDF → 製作並渲染檢查簡報。**

專案連結：<https://github.com/eric020730/medical-journal-pptx-classroom>

## 學生只做三件事

1. 登入可執行本機工作的 Codex，選一個可寫入的空白 Local 資料夾。
2. 貼上本專案網址；需要下載或執行權限時，依畫面批准。
3. Codex 顯示「完整品質環境已通過」後，附加自己的論文 PDF。

也可以直接貼：

> 請依 CODEX-START.md 自動準備完整品質環境、匯入並讀取 skill；完成後提示我提供 PDF，收到論文後直接製作、渲染及檢查簡報。

學生不用先安裝 Python、Git、Homebrew、WinGet，不用修改 PATH、開終端機、複製 `.agents` 或安裝 global skill。

## 給讀到此頁的 Codex

**立即讀取同一版本的 [CODEX-START.md](CODEX-START.md)，進入實際安裝引導；不要只介紹專案或回傳手動教學。**

只有網址不代表已授權執行軟體；尚無安裝意圖時只確認一次。已有明確安裝要求時不要重問。一般聊天、遠端 Cloud 或只有 GitHub connector 都不等於能修改學生電腦，必須先使用 Local workspace。

本流程固定本次 `main` commit，再取得完整 repository。Skill 位於 `.agents/skills/medical-journal-to-pptx-classroom/`，只作用於目前專案；Codex 必須實際讀取完整 `SKILL.md`。

## 完整品質門檻

安裝器會在專案自己的 `.bootstrap/` 與 `.venv/` 內準備：

- Python 3.12 與必要 Python 套件
- 固定版本 LibreOffice
- 固定版本 Poppler
- 合成測試論文的抽圖、建檔與 QA
- `PPTX → PDF → slide preview/contact sheet` 實際渲染測試

不更改系統 Python、shell profile、全域 PATH、其他 skills 或安全設定。所有必要工具與渲染測試都通過後，receipt 才會成為 `FULL_QA_READY_SKILL_PENDING`。缺少或失敗時必須停止，不能改以低品質模式處理學生論文。

## 會得到什麼

預設產出 **40–55 張英文投影片、每頁繁體中文講者備註、原文 Figures／Tables、建檔前後 QA、PDF 與 slide preview**。最終檔案放在 `outputs/`，中間素材與證據放在 `.skill-work/`。

工具通過不能保證內容完全正確；完成後仍須人工對照原文及檢視渲染頁面。不捏造原文沒有的數值、作者或結論。

## 隱私與限制

第一次安裝需要網路與足夠磁碟空間，也會消耗 Codex 額度；不需要 OpenAI API key，不使用 AI 生圖。論文內容會交由模型理解，不能宣稱全文完全離線。只處理獲准使用的論文，不把 PDF、成品、病人個資或帳密提交至 GitHub。

必要文件：[Codex 操作流程](CODEX-START.md) · [問題處理](docs/TROUBLESHOOTING.md) · [隱私](docs/PRIVACY.md) · [授權責任](NOTICE.md)
