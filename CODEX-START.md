# Codex 自動準備 → 放入論文 → 產出簡報

這是 **2026-09-14 課堂的新預設入口**。學生不用學習終端機、Python、Git、Homebrew 或手動匯入 skill。舊版 `START-HERE.md` / HTML 指南保留給教師排錯，不再要求學生逐步照做。

## 學生只做三件事

1. 安裝並登入支援本機執行的 Codex 客戶端，開啟一個可寫入的空白本機資料夾，例如「論文簡報」。選 Local；Windows 用原生 Windows，不臨時切 WSL。
2. 貼上老師提供的**本教學版本網址**，加一句：「請依 CODEX-START.md 完成本機環境與 skill 準備，完成後請我提供論文。」只在必要時批准下載或執行，不提供帳密、API key 或全面存取權。
3. Codex 確認準備完成後，附加自己的 PDF 或提供它可讀取的檔案路徑，說：「請用預設完整模式產出簡報。」沒有可讀取的 PDF 時，Codex 會請你把檔案放到它指出的資料夾，不會假裝已收到。

預設：40–55 張、英文投影片、繁體中文逐頁講稿、原文 Figures / Tables、原有圖片與雙階段 QA，輸出 `.pptx` 到 `outputs`。PPTX 生成不要求 Microsoft PowerPoint。缺少 LibreOffice/Poppler 時先產出 PPTX，不宣稱已完成 PDF 匯出或所有視覺 QA。

---

## 給 Codex：這是操作任務，不是請你講解安裝

### A. 核對本機執行能力與來源

先遵守當前工作資料夾的上層規則。必須有可寫入的本機 workspace 與 shell；只有一般聊天、只有 GitHub connector 讀檔、或目前在遠端 Cloud 環境，都不等於已取得學生電腦的執行權限。沒有本機 workspace 時，只要求學生完成這個必要步驟，不列出長串安裝指令。

本次下載及執行已由使用者的安裝要求授權，但仍必須遵守 Codex/作業系統的批准程序與機構政策。取得本教學版本的完整原始碼，不要下載 `Releases/latest`，不要拿整合版單一 SKILL.md 代替專案。

- 若使用者給 `/tree/<40位commit>` 或 `/blob/<commit>/CODEX-START.md`，使用同一個 commit。
- 若給 branch，先解析該分支當前完整 commit SHA 並固定本次下載，回報採用的 SHA；不要中途追蹤更新。
- 可用 Git 或 GitHub 的 `https://codeload.github.com/eric020730/medical-journal-pptx-classroom/zip/<commit>` 下載。**不要求學生先裝 Git**：Mac 可用 curl/unzip；Windows 可用 Invoke-WebRequest/Expand-Archive。先在本 workspace 的暫存子資料夾解壓，再搬入所需位置，保留 `.agents` 等隱藏檔案。
- 空白 workspace：把專案內容放到 workspace 根目錄（不是留在 ZIP 裡、不是多嵌一層）。若有同名檔案、舊版本或另一個專案，禁止直接覆蓋或清空；辨識後安全重用同一版本，或請使用者選擇新的空白資料夾。
- 下載完成後讀取本機 `AGENTS.md`、本文件、`setup-codex.sh` / `setup-codex.ps1`、`tools/codex_setup.py`，再執行。若目前根目錄已是本版本，直接重用，不重新下載。

### B. 自動建立必要環境

在專案根目錄執行，讓 Codex 做，不把指令交回學生：

macOS / Linux：
```bash
bash setup-codex.sh
```

Windows 原生 PowerShell：
```powershell
.\setup-codex.ps1
```

此流程會：
- 優先重用本專案相容的 `.venv`，不使用別的專案環境；若沒有，透過固定版本、SHA-256 驗證的 uv 下載受支援的 Python 3.12，放在 `.bootstrap`，建立 `.venv`。
- 在 `.venv` 安裝 `requirements.txt` 中的必要套件。不改系統 Python，不改 shell profile、不設定全域 PATH、不安裝 Homebrew/WinGet、不寫全域 skills。
- 檢查每個套件的宣告版本範圍，執行本機 `doctor` 與虛構 smoke-test，寫入不含私人路徑的 `.skill-work/codex-setup.json`。
- 不會讀取或產生學生論文，不會做完整 40–55 張模型生成。smoke-test 只是工具驗證。

網路批准範圍：GitHub/codeload/raw 與其 release 資產主機、Python 套件索引及檔案主機；uv 管理的 Python 來自 Astral python-build-standalone。下載程式有固定 checksum；Python 清單取決於固定 uv 版本；套件使用 repo 宣告範圍，**不是所有相依都鎖版，也不是離線包**。

若網路、組織腳本政策、執行權限或防毒阻擋：說明最小必要操作並停在該關，不關閉防毒、不調整執行政策、不忽略 TLS/雜湊、不改 Codex 的全域安全設定。若 `.venv` 已損壞或版本不支援，不刪除它來掩蓋問題；先說明並取得處理授權。

### C. 載入本專案 skill，然後提示放論文

只有安裝命令退出碼為 0、剛產生的 receipt 狀態為 `LOCAL_READY_SKILL_PENDING`，才進入此階段。

**實際讀取完整檔案：**
`.agents/skills/medical-journal-to-pptx-classroom/SKILL.md`

技能已隨完整專案放在本工作資料夾的 `.agents/skills`；這就是這堂課的「匯入」，不需複製到個人全域位置。若技能選單還沒刷新，同一任務可以先直接讀完整 SKILL.md 並按其規則操作；不要求為了選單顯示就重裝。不要把「檔案存在」或 shell receipt 假稱為「模型已載入」。

讀取成功後簡單告訴學生：
> 必要環境已通過測試，論文轉簡報 skill 已讀取。請把要製作簡報的 PDF 加到這段對話，或提供本機檔案路徑。我會使用預設的 40–55 張英文投影片＋繁中講稿，輸出到 outputs。

同時如實註明是否缺少選用的 PDF 匯出工具。不要要求學生再貼三段長提示詞。不要自動開始處理內建示範 PDF。

### D. 收到 PDF 後直接執行原 skill

先確認檔案實際可讀、是本次論文。附件沒有對應的本機路徑時，請學生將 PDF 放到明確指出的 `sample-papers` 路徑，不能猜測掛載路徑。一次多篇時先請學生選一篇。

在開始時回報讀到的文章標題與頁數；有錯篇、缺頁、加密、個資或明顯讀取問題才停下來確認。正常情況直接生成，不再以大綱審查或多輪追問阻塞這條簡化路線。

實際執行先讀 `references/full_workflow_v0.2.38.md` 與其按需參考，完整保留 prepare、圖表來源/灰階保護、qa-spec、build、qa、可用時 render 的規則。禁止為通過測試而改 QA 規則。原始 PDF 不修改；正文、數字與引用不能憑空補齊。最終檔案保留不覆蓋的安全命名，存到 `outputs`；中間檔存到 `.skill-work/<run-id>`。中斷後重用同一工作紀錄，不從頭反覆安裝或生成。

交付真實的檔案路徑、張數、QA 結果與人工複核提醒。網路額度與模型用量不由安裝器保證；論文內容會交由模型理解，不能宣稱整個工作流離線或文字完全不送到模型。不要公開上傳論文、生成簡報或私人紀錄。

### E. 選用 PDF 匯出（不擋第一份 PPTX）

使用者明確要求 PDF 或完整視覺匯出時，再依原平台文件安裝 LibreOffice / Poppler；需要系統層改動時說明並取得必要批准。不把 PPTX-only 結果宣稱為完整 PDF/視覺 QA。

## 官方依據與版本邊界

核對日期：2026-09-12。
- Codex 本機 skills：https://learn.chatgpt.com/docs/build-skills
- Codex 本機與權限：https://learn.chatgpt.com/docs/security
- Windows 原生環境：https://learn.chatgpt.com/docs/windows/windows-app
- uv 自動下載 Python：https://docs.astral.sh/uv/concepts/python-versions/
- bootstrap 固定資產與雜湊：https://github.com/astral-sh/uv/releases/tag/0.8.22

工具測試成功不等於所有學生的帳號、教室網路和電腦都已實測。本文件不允許繞過任何機構政策。
