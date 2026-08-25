# Medical Journal PPTX Classroom

把一篇醫學期刊 PDF 交給 Codex，產生可編輯的 PowerPoint：**英文投影片、繁體中文講者備註、論文 Figures／Tables，以及自動品質檢查**。

本專案保留 `medical-journal-to-pptx v0.2.38-bg-aware-trim` 的完整圖片處理與簡報製作流程，另外加入 macOS／Windows 安裝程式、跨裝置可攜式路徑，以及適合學生練習的輕量模式。

> 這不是無需 AI 帳號的離線產生器。Python 腳本負責讀取 PDF、處理圖片、組裝與驗證 PowerPoint；理解論文、撰寫英文投影片及繁體中文講稿，仍需要可使用 Codex 的帳號。

## 先確認你需要什麼

- 一台 macOS 或 Windows 電腦。
- 可以登入 Codex 的 ChatGPT 帳號。
- 可下載 Python 套件與系統工具的網路連線。
- 安裝系統工具時，電腦可能要求管理員密碼或學校資訊人員協助。
- 不需要 Microsoft PowerPoint 才能產生 `.pptx`；LibreOffice 用於 PDF 匯出與版面檢查。

官方入口：[ChatGPT 桌面應用程式](https://learn.chatgpt.com/docs/app)、[Windows 桌面應用程式](https://learn.chatgpt.com/docs/windows/windows-app)、[Codex Skills](https://learn.chatgpt.com/docs/build-skills)。

## 三分鐘了解整個流程

1. 從 GitHub 按 **Code → Download ZIP**，下載並完整解壓縮。
2. 第一次使用時執行對應的安裝檔。
3. 用 ChatGPT／Codex 桌面應用程式開啟整個專案資料夾。
4. 加入 PDF，貼上下面的提示詞。
5. 完成後到 `outputs/` 拿取 `.pptx`，以及可用時產生的 `.pdf`。

### macOS

在 Finder 連按兩下：

```text
setup-macos.command
```

如果 macOS 第一次阻擋檔案，請使用 Finder 的右鍵「打開」，並確認檔案來源可信。Apple Silicon 與 Intel Mac 都使用同一份安裝程式。

### Windows

在檔案總管連按兩下：

```text
setup-windows.cmd
```

安裝程式使用 Windows Package Manager 安裝 Python、LibreOffice 和 Poppler。若學校電腦限制 PowerShell 或軟體安裝，請交由資訊管理員協助，不要規避機構安全政策。

### 第一個練習提示詞

```text
$medical-journal-to-pptx-classroom

請使用 lite 模式處理 sample-papers/classroom-demo-paper.pdf，
製作 8–16 張英文教學投影片，講者備註使用繁體中文。
清楚標示這是一篇虛構教學文章，完成 QA 後把 PPTX 儲存在 outputs。
```

`classroom-demo-paper.pdf` 由本專案自動產生；所有結果都是虛構，不是真實臨床證據。

### 處理自己的論文

將 PDF 放入 `sample-papers/`，或者直接附加到 Codex 任務，然後使用：

```text
$medical-journal-to-pptx-classroom

請使用 full 模式處理我提供的醫學期刊 PDF，製作完整 journal club 教學簡報。
投影片使用英文，講者備註使用繁體中文；保留重要 Figures 和 Tables，
說明研究背景、方法、主要結果、臨床意義及限制。
完成所有圖片、講稿與 PowerPoint QA 後，將最終 PPTX 和可用的 PDF 儲存在 outputs。
```

## 兩種模式

| 模式 | 投影片 | 適合情境 | 使用量 |
| --- | --- | --- | --- |
| `lite` | 8–16 張 | 第一次上課、範例練習、有限額度 | 較低 |
| `full` | 40–55 張 | 正式 journal club、完整住院醫師教學 | 較高 |

免費方案可以嘗試 `lite`，但 **Codex 使用額度與自訂 Skills 是否開放，仍以個人帳號及官方當下政策為準**。專案不需要額外 OpenAI API key，也不依賴 AI 圖像生成。詳見 [免費方案教學指引](docs/FREE-PLAN.md)。

## 系統會自動安裝什麼

| 項目 | macOS | Windows | 用途 |
| --- | --- | --- | --- |
| Python 3.12 | Homebrew 或既有 3.11–3.13 | WinGet 或既有 3.11–3.13 | 執行本機工具 |
| Python 虛擬環境 | `.venv/bin/python` | `.venv\Scripts\python.exe` | 隔離各專案套件 |
| PyMuPDF、pdfplumber | pip | pip | 讀取 PDF、擷取文字與圖表 |
| python-pptx | pip | pip | 建立 PowerPoint |
| Pillow、NumPy | pip | pip | 圖片處理與品質檢查 |
| LibreOffice | Homebrew cask | WinGet | 匯出 PDF、視覺 QA |
| Poppler | Homebrew | WinGet | 高品質 PDF 預覽 |

Python 3.14 暫不列入本專案已驗證版本。即使電腦原本的 `python3` 指向 3.14，安裝程式也會優先尋找或安裝 Python 3.12。

## 確认安裝是否成功

macOS：

```bash
./journal doctor
./journal smoke-test
```

Windows PowerShell 或命令提示字元：

```powershell
.\journal.cmd doctor
.\journal.cmd smoke-test
```

`smoke-test` 會實際產生虛構 PDF、執行圖片擷取與裁切、建立 PowerPoint，再檢查繁體中文講稿與 Logo，不會把測試簡報混進正式 `outputs/`。

## 專案結構

```text
medical-journal-pptx-classroom/
├── .agents/skills/medical-journal-to-pptx-classroom/
│   ├── SKILL.md                         學生版 skill 入口
│   ├── VERSION                          原始 v0.2.38 版本
│   ├── scripts/                         完整圖片與 PowerPoint 管線
│   ├── references/full_workflow_v0.2.38.md
│   └── assets/                          簡報 Logo 等資源
├── docs/                                詳細安裝、教學與疑難排解
├── sample-papers/                       範例與學生自行放入的 PDF
├── outputs/                             最終 PPTX／PDF
├── tools/                               跨平台診斷、測試、QA 與發佈封裝
├── setup-macos.command                  macOS 一鍵安裝
├── setup-windows.cmd                    Windows 一鍵安裝
├── journal                              macOS 指令入口
└── journal.cmd                          Windows 指令入口
```

Codex 會自動讀取專案 `.agents/skills`，因此學生只需要打開**整個專案資料夾**，不需要自行複製隱藏資料夾或變更個人 Codex 設定。

## 跨裝置使用

這個 skill 跟著 repository 走，不依賴某一台電腦的個人 Codex 資料夾，也不必等待 ChatGPT 帳號同步。換到另一台裝置時：

1. 重新下載 ZIP 或執行 `git clone`／`git pull`。
2. 在該裝置重新執行 macOS 或 Windows 安裝程式；`.venv` 與系統工具不能直接跨系統複製。
3. 用 Codex 開啟整個專案資料夾，繼續用同一個 `$medical-journal-to-pptx-classroom` 指令。

基於隱私，`sample-papers/` 裡的學生論文、`.skill-work/` 與 `outputs/` 成品預設都不會同步到 GitHub。需要帶走成品時，請只複製已去識別化且有權分享的 `.pptx`／`.pdf`，或放到學校核准的私人雲端空間。

## 教師建立可分享 ZIP

完成內容檢查後執行：

```bash
./journal package
```

Windows：

```powershell
.\journal.cmd package
```

封裝檔與 SHA-256 校驗檔會放在 `dist/`。發佈器會包含完整 skill、安裝程式、文件與虛構範例 PDF，並排除 `.venv`、學生論文、工作檔和輸出簡報。第一次公開前仍必須人工確認 [NOTICE.md](NOTICE.md) 所列的技能與 Logo 散布權。

## 延伸文件

- [macOS 完整安裝](docs/QUICKSTART-MAC.md)
- [Windows 完整安裝](docs/QUICKSTART-WINDOWS.md)
- [免費方案與輕量模式](docs/FREE-PLAN.md)
- [可直接複製的提示詞](docs/PROMPTS.md)
- [教師上課流程](docs/INSTRUCTOR-GUIDE.md)
- [疑難排解](docs/TROUBLESHOOTING.md)
- [資料安全與著作權](docs/PRIVACY.md)
- [發布到 GitHub](docs/PUBLISH-TO-GITHUB.md)

## 隱私與授權

學生論文、輸出簡報與工作檔預設不會進入 Git。上傳 GitHub 前，仍須確認 Logo、教材、原始技能及任何外部文章的授權；請參閱 [NOTICE.md](NOTICE.md)。不要把包含病人姓名、病歷號、生日、未去識別影像或 API key 的資料上傳到公開 repository。
