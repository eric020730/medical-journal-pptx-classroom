# Windows 安裝與第一次使用

## 1. 安裝 ChatGPT／Codex

請依照 [OpenAI 官方 Windows 桌面應用程式文件](https://learn.chatgpt.com/docs/windows/windows-app) 安裝並登入自己的 ChatGPT 帳號。

## 2. 下載並完整解壓縮

從 GitHub 按 **Code → Download ZIP**。在檔案總管對 ZIP 按右鍵並選擇「全部解壓縮」，再進入解壓縮後的資料夾。

推薦位置：

```text
%USERPROFILE%\Documents\medical-journal-pptx-classroom\
```

不要放在 `C:\Program Files`、唯讀網路磁碟，或尚未解壓縮的 ZIP 視窗內。

## 3. 執行安裝

連按兩下：

```text
setup-windows.cmd
```

安裝程式會使用 WinGet：

```powershell
winget install --id Python.Python.3.12 --exact --source winget
winget install --id TheDocumentFoundation.LibreOffice --exact --source winget
winget install --id oschwartz10612.Poppler --exact --source winget
```

接著建立：

```text
.venv\Scripts\python.exe
```

並安裝所有 Python 套件、建立虛構範例論文、執行完整 PowerPoint 測試。

如果 Windows 詢問是否允許安裝程式變更電腦，請確認發布者與安裝來源後再決定是否同意。若學校有裝置管理政策，請由資訊管理員操作。

## 4. 開啟 Codex 專案並產生簡報

在 ChatGPT／Codex 桌面應用程式打開專案根目錄，再輸入：

```text
$medical-journal-to-pptx-classroom

使用 lite 模式處理 sample-papers/classroom-demo-paper.pdf，
製作英文投影片與繁體中文講者備註，將簡報存到 outputs。
```

完成後開啟：

```text
outputs\
```

## 原生 Windows 與 WSL

本專案預設使用**原生 Windows** 的 Python、PowerShell、LibreOffice 與 WinGet，不要求安裝 WSL。

如果你在 WSL 內執行 Codex，WSL 與原生 Windows 是不同環境；Windows 安裝的 Python 與 LibreOffice 不會自動變成 Linux 工具。非必要時請直接使用 Windows 桌面應用程式與原生 PowerShell。

## 路徑與 PATH

Windows 安裝 LibreOffice 後，`soffice.exe` 常位於：

```text
C:\Program Files\LibreOffice\program\soffice.exe
```

Poppler 也可能位於 WinGet 的使用者套件資料夾。專案診斷工具會自動尋找這些位置，不要求學生手動編輯 PATH。

## 常用檢查

```powershell
.\journal.cmd doctor
.\journal.cmd doctor --strict
.\journal.cmd smoke-test
.\journal.cmd paths
```

若 Python 安裝後尚未被目前視窗辨識，關閉終端機與 Codex，重新開啟後再次執行 `setup-windows.cmd`。
