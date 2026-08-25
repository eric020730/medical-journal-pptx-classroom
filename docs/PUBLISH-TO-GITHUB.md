# 發布到 GitHub

## 先決定公開或私人

本專案含有使用者提供的原始技能與 Dr. Leether Logo。確認權利之前，建議先使用 **private repository**。

請先檢查：

```bash
git status --short
git check-ignore sample-papers/private-paper.pdf
git check-ignore outputs/student-deck.pptx
```

確認沒有學生論文、病人資料、PowerPoint、虛擬環境或 API key。

也可以先建立經過白名單過濾的發佈 ZIP：

```bash
./journal package
```

Windows 使用 `journal.cmd package`。產物位於 `dist/`，同時會建立 `.sha256` 校驗檔；ZIP 內的 `RELEASE-MANIFEST.txt` 會列出每個檔案的雜湊值。這項自動排除不取代人工授權與隱私檢查。

## 使用 GitHub 網頁

1. 在 GitHub 建立新的私人 repository，例如 `medical-journal-pptx-classroom`。
2. 不要額外初始化新的 README，避免與本地檔案衝突。
3. 在本地專案資料夾執行：

```bash
git add .
git commit -m "Add portable medical journal PPTX classroom project"
git remote add origin https://github.com/YOUR_ACCOUNT/medical-journal-pptx-classroom.git
git push -u origin main
```

將 `YOUR_ACCOUNT` 換成自己的 GitHub 帳號或組織。

## 使用 GitHub CLI

先登入：

```bash
gh auth login
```

然後：

```bash
git add .
git commit -m "Add portable medical journal PPTX classroom project"
gh repo create medical-journal-pptx-classroom --private --source=. --remote=origin --push
```

若你的技能、Logo 和教材皆已確認可以公開散布，才將 `--private` 改為 `--public`。

## 分享給學生

私人 repository：邀請學生 GitHub 帳號，或提供學校 GitHub 組織權限。

公開 repository：學生可以按 **Code → Download ZIP**，不用先學 Git。

教師也可以在 GitHub 建立 Release，將 `dist/` 裡的 ZIP 與 `.sha256` 上傳為附件。這個 ZIP 明確包含隱藏的 `.agents/skills`，也不會夾帶本機 `.venv` 或學生作業，比直接壓縮 Finder／檔案總管資料夾安全。

熟悉 Git 的學生可以：

```bash
git clone https://github.com/YOUR_ACCOUNT/medical-journal-pptx-classroom.git
```

更新時：

```bash
git pull
```

## 自動測試

GitHub Actions 會在 macOS、Windows 和 Ubuntu 執行 Python 套件安裝、單元測試與端對端的虛構 PDF → PowerPoint 測試。CI 不會讀取學生 PDF，也不需要 OpenAI API key。
