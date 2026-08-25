# 疑難排解

## Codex 沒有看到 skill

確認你打開的是 repository 根目錄，裡面應同時看得到：

```text
README.md
setup-macos.command
setup-windows.cmd
.agents/skills/medical-journal-to-pptx-classroom/SKILL.md
```

接著重新開啟任務或重新啟動 Codex。輸入：

```text
$medical-journal-to-pptx-classroom
```

免費帳號的 Skills 權限以實際帳號為準。無法使用選單時，可嘗試要求 Codex 直接讀取 repository 內的 `SKILL.md`。

## 顯示 Python 3.14 不支援

專案驗證版本是 Python 3.11–3.13，建議使用 Python 3.12。

macOS：

```bash
brew install python@3.12
./setup-macos.command
```

Windows：

```powershell
winget install --id Python.Python.3.12 --exact --source winget
.\setup-windows.cmd
```

如果已經建立錯誤版本的 `.venv`，確認不再需要其中資料後刪除 `.venv`，再重新執行安裝。

## Windows 找不到 winget

請安裝或更新 Microsoft App Installer。受學校或醫院管理的電腦，應由管理員提供 Python、LibreOffice 和 Poppler。

若這些系統工具已經安裝，只需要建立 Python 環境：

```powershell
.\setup-windows.ps1 -SkipSystem
```

## Windows PowerShell 被學校政策禁止

請遵守機構安全規範，交由資訊人員執行 `setup-windows.ps1` 或手動安裝依賴。不要用未知來源的腳本、停用防毒，或繞過組織管理政策。

## macOS 找不到 Homebrew

一般情況直接重新執行：

```bash
./setup-macos.command
```

如果管理員已經先安裝好 Python：

```bash
./setup-macos.command --skip-system
```

## macOS 安裝檔顯示 Permission denied

下載 ZIP 後，有些解壓縮程式會移除 Unix 可執行權限。先確認專案來源可信，再從專案資料夾執行：

```bash
bash setup-macos.command
```

不需要關閉 Gatekeeper，也不要執行來源不明的安裝指令。

## 找不到 LibreOffice 或 soffice

PowerPoint 仍然可以產生；缺少的是 PDF 匯出與部分視覺 QA。

macOS：

```bash
brew install --cask libreoffice
./journal doctor --strict
```

Windows：

```powershell
winget install --id TheDocumentFoundation.LibreOffice --exact --source winget
.\journal.cmd doctor --strict
```

安裝後若 Codex 還是看不到工具，完全關閉並重新開啟 Codex。

## 找不到 Poppler 或 pdftoppm

macOS：

```bash
brew install poppler
```

Windows：

```powershell
winget install --id oschwartz10612.Poppler --exact --source winget
```

專案會自動檢查常見 WinGet 安裝位置。缺少 Poppler 時，PowerPoint 仍可產生；PDF 預覽也會嘗試以 PyMuPDF 替代。

## PPTX 有了，但沒有 PDF

手動執行：

```bash
./journal render "outputs/你的簡報.pptx" --preview
```

Windows：

```powershell
.\journal.cmd render "outputs\你的簡報.pptx" --preview
```

## 額度不足，中途停止

等待帳號額度恢復後，回到同一個 Codex 任務：

```text
請從目前 .skill-work 內已經完成的階段繼續，保留已擷取的圖表，
完成剩餘投影片、繁體中文備註與 QA，不要重新開始完整工作。
```

## 環境報告

macOS：

```bash
./journal doctor --json > diagnostics.json
```

Windows：

```powershell
.\journal.cmd doctor --json > diagnostics.json
```

`diagnostics.json` 可能包含使用者名稱與電腦路徑，傳給老師或公開貼文前請先遮蔽個人資訊。
