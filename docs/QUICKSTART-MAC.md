# macOS 安裝與第一次使用

## 1. 安裝 ChatGPT／Codex

請從 [官方桌面應用程式說明](https://learn.chatgpt.com/docs/app) 取得目前支援的安裝方式，使用自己的 ChatGPT 帳號登入。

## 2. 下載課程專案

在 GitHub 頁面按 **Code → Download ZIP**，解壓縮到自己的桌面或文件資料夾。不要直接在 ZIP 內執行檔案，也不要把整個專案放在唯讀資料夾。

## 3. 執行安裝

在 Finder 開啟專案資料夾，連按兩下 `setup-macos.command`。

安裝程式會：

1. 必要時安裝 Homebrew。
2. 選擇 Python 3.12，或現有相容的 Python 3.11–3.13。
3. 安裝 Poppler 和 LibreOffice。
4. 建立專案自己的 `.venv`。
5. 安裝 Python 套件。
6. 產生虛構示範論文。
7. 執行環境診斷與端對端 PowerPoint 測試。

Apple Silicon 預設使用 `/opt/homebrew`；Intel Mac 預設使用 `/usr/local`。安裝程式會自動處理兩者。

如果 macOS 顯示來自未識別開發者，請先確認 repository 來源，再於 Finder 右鍵點選檔案並選擇「打開」。管理員密碼與 Xcode Command Line Tools 安裝畫面屬於 Homebrew 正常安裝流程。

部分解壓縮工具不會保留 `.command` 檔案的執行權限。如果雙擊後出現「Permission denied」，請在 Terminal 切換到專案資料夾，改用：

```bash
bash setup-macos.command
```

安裝程式啟動後會自動修復 `journal` 與安裝檔本身的執行權限。

## 4. 開啟專案

在 ChatGPT／Codex 桌面應用程式中，選擇這個專案資料夾本身，不要只開啟 `sample-papers` 或 `outputs`。

輸入：

```text
$medical-journal-to-pptx-classroom

使用 lite 模式，把 sample-papers/classroom-demo-paper.pdf 製作成
8–16 張英文投影片，所有講者備註使用繁體中文。
完成 QA 後將檔案放到 outputs。
```

## 管理員限制下的替代方式

如果學校已經安裝 Python，而你沒有權限安裝 Homebrew 或 LibreOffice：

```bash
./setup-macos.command --skip-system
```

仍可建立 PowerPoint，但沒有 LibreOffice 時無法匯出 PDF；没有 Poppler 時預覽會使用 PyMuPDF 作為備援。

## 檢查與更新

```bash
./journal doctor
./journal doctor --strict
./journal smoke-test
git pull
./setup-macos.command
```

`git pull` 只適用於使用 `git clone` 下載的 repository；透過 Download ZIP 取得的學生請重新下載新版本。
