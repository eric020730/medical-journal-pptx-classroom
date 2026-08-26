# Medical Journal PPTX Classroom

把一篇醫學期刊 PDF 交給 Codex，產生可編輯的 PowerPoint：**英文投影片、繁體中文講者備註、論文 Figures／Tables，以及自動品質檢查**。

本專案提供兩種互相獨立的入口：classroom repository skill，以及 `v4.1.0` **可全域安裝、可在任何專案啟用的整合版 skill**。整合版固定使用 40–55 張的 full 模式，支援 standard／nice 視覺風格、建檔前後雙階段 QA、PDF 灰階反相檢查與完整影像來源追蹤。

> 這不是無需 AI 帳號的離線產生器。Python 腳本負責讀取 PDF、處理圖片、組裝與驗證 PowerPoint；理解論文、撰寫英文投影片及繁體中文講稿，仍需要可使用 Codex 的帳號。

## 推薦：安裝可在任何專案使用的全域整合版

從 [最新 GitHub release](https://github.com/eric020730/medical-journal-pptx-classroom/releases/latest)
下載 `medical-journal-to-pptx-integrated-v4.1.0.zip` 和 `.sha256`，驗證後完整解壓縮。

macOS / Linux：

```bash
bash install-global.sh install
```

Windows PowerShell：

```powershell
.\install-global.ps1 install
```

之後開啟**任何專案**，直接使用：

```text
$medical-journal-to-pptx-integrated

請用 full 模式與 nice 風格處理我提供的醫學期刊 PDF；製作 40–55 張英文
投影片，每頁附繁體中文講稿，保留 Figures、Tables、panel labels 和完整
PDF 灰階／來源檢查，通過兩階段 QA 後儲存到指定輸出資料夾。
```

全域整合版只提供兩種完整教學組合：`standard + full` 與 `nice + full`。
升級使用 `install-global.sh upgrade` 或
`install-global.ps1 upgrade`；解除安裝使用 `uninstall`。安裝、升級及解除
安裝都不會刪除任何其他全域 skills。完整說明請見
[全域安裝、升級與解除安裝](docs/GLOBAL-INSTALL.md)。

以下 classroom 操作仍保留，適合希望整個教材跟著 repository 移動的教學情境。

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

請使用 full 模式處理 sample-papers/classroom-demo-paper.pdf，
製作 40–55 張英文教學投影片，講者備註使用繁體中文。
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

## classroom 版的完整教學模式

| 模式 | 投影片 | 適合情境 | 使用量 |
| --- | --- | --- | --- |
| `full` | 40–55 張 | 正式 journal club、完整住院醫師教學 | 較高 |

所有簡報都使用 `full` 模式。**Codex 使用額度與自訂 Skills 是否開放，仍以個人帳號及官方當下政策為準**。專案不需要額外 OpenAI API key，也不依賴 AI 圖像生成。詳見 [免費方案教學指引](docs/FREE-PLAN.md)。

## 雙階段 QA 與醫學影像反相防護

部分期刊 PDF 使用特殊色彩空間或 `Decode` 設定：直接擷取內嵌灰階圖片時可能變成黑白顛倒，但 PDF 檢視器的畫面仍然正確。`journal prepare` 會把每張原始圖與 PDF 實際渲染結果比對，記錄灰階相關性，並在 `.skill-work/<run-id>/extracted/polarity-report.json` 標記不安全來源。

製作簡報時，請使用已套用 PDF 色彩解碼的 `extracted/figures/` 圖片，不要直接採用 `extracted/image_pXX_YY.*`。單張影像、裁切後的中間檔，以及由 A／B／C／D 組成的 Figure 都會追溯來源；如果發現黑白顛倒的圖進入最終素材，QA 會直接失敗。

建檔前先執行內容與素材檢查，再於建檔後檢查實際 PowerPoint：

```bash
./journal image-qa .skill-work/RUN_ID/extracted/manifest.json
./journal qa-spec .skill-work/RUN_ID/deck_spec.json --mode full
./journal qa outputs/presentation.pptx --spec .skill-work/RUN_ID/deck_spec.json --mode full
```

Windows 使用相同參數，將 `./journal` 改成 `.\journal.cmd`。檢查範圍包含作者與引用、`full` 模式的目錄和 references、英文投影片、每頁繁中講稿、正確 Logo、16:9 畫面、一圖一頁、panel 標籤與位置、表格安全邊界，以及分割表格的像素和顯示寬度一致性。

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

`smoke-test` 會實際產生虛構 PDF、執行影像反相比對與圖片裁切、通過建檔前進階 QA、建立 PowerPoint，再檢查繁體中文講稿與 Logo，不會把測試簡報混進正式 `outputs/`。

## 專案結構

```text
medical-journal-pptx-classroom/
├── .agents/skills/medical-journal-to-pptx-classroom/
│   ├── SKILL.md                         學生版 skill 入口
│   ├── VERSION                          classroom skill 版本
│   ├── scripts/                         完整圖片與 PowerPoint 管線
│   ├── references/                      classroom 完整流程參考
│   └── assets/                          簡報 Logo 等資源
├── .agents/skills/medical-journal-to-pptx-integrated/
│   ├── SKILL.md                         全域整合版簡潔入口
│   ├── VERSION                          v4.1.0
│   ├── scripts/                         雙視覺 builder、雙階段 QA、polarity
│   └── references/                      完整流程、兩種風格、QA 來源鏈
├── docs/                                詳細安裝、教學與疑難排解
├── sample-papers/                       範例與學生自行放入的 PDF
├── outputs/                             最終 PPTX／PDF
├── tools/                               跨平台診斷、測試、QA 與發佈封裝
├── setup-macos.command                  macOS 一鍵安裝
├── setup-windows.cmd                    Windows 一鍵安裝
├── install-global.py / .sh / .ps1       跨平台全域整合版安裝／升級／移除
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
- [可在任何專案使用的全域整合版](docs/GLOBAL-INSTALL.md)
- [免費方案與輕量模式](docs/FREE-PLAN.md)
- [可直接複製的提示詞](docs/PROMPTS.md)
- [教師上課流程](docs/INSTRUCTOR-GUIDE.md)
- [疑難排解](docs/TROUBLESHOOTING.md)
- [資料安全與著作權](docs/PRIVACY.md)
- [發布到 GitHub](docs/PUBLISH-TO-GITHUB.md)

## 隱私與授權

學生論文、輸出簡報與工作檔預設不會進入 Git。上傳 GitHub 前，仍須確認 Logo、教材、原始技能及任何外部文章的授權；請參閱 [NOTICE.md](NOTICE.md)。不要把包含病人姓名、病歷號、生日、未去識別影像或 API key 的資料上傳到公開 repository。
