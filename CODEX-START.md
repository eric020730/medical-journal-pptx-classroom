# Codex 自動準備 → 放入論文 → 產出並渲染檢查簡報

這是本專案唯一的安裝與製作流程。學生不用操作終端機、Python、Git、Homebrew、WinGet，或手動匯入 skill。所有工作由取得授權的本機 Codex 執行。

## 學生只做三件事

1. 開啟支援本機執行的 Codex，選擇可寫入的空白 Local 資料夾。Windows 使用原生 Windows，不臨時切換 WSL。
2. 貼上本專案 GitHub 首頁網址。只有網址且尚未表明安裝意圖時，Codex 用一句話確認；已有明確要求就直接執行。只批准這個專案必要的下載與執行，不提供帳密、API key 或全面存取權。
3. Codex 宣告完整品質環境通過後，附加論文 PDF 或提供可讀取的本機路徑；收到檔案後直接接續製作。已在課堂指示中表明安裝意圖時，不再追加確認。

預設成果：40–55 張英文投影片、繁體中文逐頁講稿、原文 Figures／Tables、雙階段 QA、PDF 與 slide preview，輸出至 `outputs/`。

---

## 給 Codex：這是操作任務，不是安裝說明題

### A. 核對本機能力並取得固定版本

必須有可寫入的 Local workspace 與 shell。只有一般聊天、遠端 Cloud 或 GitHub connector 讀檔，不代表已取得學生電腦的執行權限。

若使用者只有貼網址，先問：「要在目前本機資料夾安裝這個論文轉簡報工具嗎？完成完整渲染測試後我會請你提供 PDF。」已有明確安裝要求時不重複詢問。

一般專案首頁先解析 `main` 的完整 commit SHA，固定本次版本後下載完整 repository；不要只複製 `SKILL.md`，不要混用其他版本的檔案；指定版本網址必須保留其版本，不改抓 main。Git 不存在時可使用 codeload ZIP。空白 workspace 將內容放在根目錄；若已有其他內容、舊版或同名檔案，不得直接覆蓋或清空。

下載後依序讀取本機 `AGENTS.md`、本文件、對應 setup script 與 `tools/codex_setup.py`。

### B. 自動準備完整品質環境

由 Codex 在專案根目錄執行，不把指令當作學生作業：

macOS／Linux：

```bash
bash setup-codex.sh
```

Windows 原生 PowerShell：

```powershell
.\setup-codex.ps1
```

流程會在專案內建立：

- `.bootstrap/`：受管理 Python、固定版本 LibreOffice、Pixi 與 Poppler
- `.venv/`：此專案必要 Python 套件
- `.skill-work/`：測試、QA 與後續執行紀錄

不修改系統 Python、全域 PATH、shell profile 或其他 skills；不安裝 Homebrew／WinGet。所有下載都有固定版本及 SHA-256 驗證。

安裝結束前必須完成：

1. 嚴格 `doctor`：Python 套件、LibreOffice、Poppler 全部為 OK。
2. 合成論文 smoke-test：抽圖、影像 polarity、asset audit、spec QA、PPTX build、final QA。
3. 真實渲染測試：合成 PPTX 經 LibreOffice 轉 PDF，再由 Poppler 產生 slide preview/contact sheet。

任何必要項目失敗都必須停在 `SETUP_BLOCKED`，不得改用 PPTX-only 或跳過渲染檢查。不可關閉防毒、忽略 TLS／雜湊、變更執行政策或繞過機構限制。

### C. 讀取 repository skill，再請學生提供 PDF

只有本次 setup 命令退出碼為 0，且 `.skill-work/codex-setup.json` 為：

```text
FULL_QA_READY_SKILL_PENDING
```

才可進入本階段。

實際讀取完整檔案：

```text
.agents/skills/medical-journal-to-pptx-integrated/SKILL.md
```

同時讀取旁邊的 `VERSION`。預設 standard，只有學生要求時才改 nice，不用先詢問版型。

Skill 已隨 repository 存在，不需安裝到全域位置。選單未刷新時仍可直接讀取完整 `SKILL.md`；檔案存在或 setup 通過不能假稱模型已讀取。

讀取後告訴學生：

> 完整品質環境已通過，包括 PPTX 產生、PDF 匯出與 slide preview 測試；論文轉簡報 skill 已讀取。請附加要製作的 PDF，或提供本機路徑。我會建立 40–55 張英文投影片、繁中講稿，並完成渲染檢查後輸出到 outputs。

### D. 收到 PDF 後直接執行完整 skill

先確認檔案實際可讀且是本次論文；附件沒有本機路徑時，請學生放入明確指出的 `sample-papers`。一次有多篇才請選一篇。

開始時回報文章標題與頁數。除非錯篇、缺頁、加密、個資或明顯讀取問題，正常情況不要用大綱核准或多輪提問阻塞流程。

完整保留 prepare、原文圖表來源、灰階／反相保護、qa-spec、build、final QA 及 render。不得為通過測試而改 QA 規則。最終 deck 必須：

1. 通過 spec QA 與 PPTX QA。
2. 以 `journal render <pptx> --preview`（Windows 用 `journal.cmd`）實際產生 PDF 與 preview。
3. 檢視每一頁渲染結果，逐一對照原文 Figure/Table，確認 panel、表頭、末列、註腳完整，修正跑版、截字與不可讀問題，再重新 QA/render。
4. 依 skill 的視覺驗收說明，記錄目前 render snapshot、已檢視頁碼、原文圖表核對與發現事項；實際完成檢視後才呼叫 `journal visual-review`。
5. 執行 `journal qa-status <pptx> --spec <spec.json> --style <standard|nice> --require-delivery`，完整交付狀態必須通過。只有 render 成功不能代替視覺檢視。

不得改用 historical classroom fixture 的 builder 或 QA。`journal` 必須使用 integrated 核心，保留來源 caption 綁定、接縫證據、備註品質與 canonical rebuild。

渲染或檢視未完成時，不得宣稱達到本技能完整品質標準。

交付實際檔案路徑、張數、QA 結果、PDF／preview 結果及人工複核提醒。中斷時保留 `.skill-work/<run-id>`，從既有紀錄接續，不反覆重裝或重做已完成階段。
