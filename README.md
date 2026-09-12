# Medical Journal PPTX Classroom

把醫學論文 PDF 轉成可編輯 PowerPoint：**40–55 張英文投影片、逐頁繁體中文講稿、原文 Figures / Tables，以及圖片與建檔前後 QA**。

## 9/14 課堂最快入口：貼網址給 Codex

學生先**安裝並登入支援本機執行的 Codex，選一個可寫入的空白本機資料夾**。接著把老師提供的本教學版本網址貼進 Codex，加一句：

> 請依 CODEX-START.md 自動準備本機環境與 skill，完成後請我提供論文 PDF。

**[Codex 自動操作入口：CODEX-START.md](CODEX-START.md)**

Codex 會取得完整專案、準備 Python 和必要套件、測試並讀取 skill，然後請你附加論文。下一句只需：

> 請用預設完整模式，把這篇論文做成簡報。

不要求學生手動輸入終端機指令、先裝 Git/Homebrew/WinGet，或複製隱藏的 skill 資料夾。下載與執行仍可能需要批准；不能繞過學校或醫院政策。

**這個新入口目前在 `teaching/classroom-ready-20260914` 教學分支。** 未合併 main 前，請使用該分支或老師提供的固定 commit 網址；不要把舊的 `Releases/latest` 當作本教學版。

## 學生會經過什麼

| 學生做 | Codex 做 |
| --- | --- |
| 登入 Codex，開啟空白本機資料夾 | 確認可以本機讀檔及執行 |
| 貼教學版本網址與安裝要求 | 固定本次來源，下載完整專案，保留隱藏檔 |
| 必要時批准下載／執行 | 建立專案獨立 Python 環境、安裝套件、跑 doctor 與 smoke-test |
| 等待提示提供 PDF | 實際讀取 repository skill，不改其他全域 skills |
| 附加 PDF 或提供本機路徑 | 辨識文章、擷取圖表、產生 full 簡報、執行原有 QA |
| 開啟成品、核對原文 | 回報實際檔名、張數、QA 與未完成項目 |

如果 PDF 附件沒有可讀取的本機路徑，Codex 會指出 `sample-papers` 的確切位置，請學生放進去。不能只因聊天裡看得到檔名就假裝有讀到原文。

## 安裝設計與限制

`setup-codex.sh` / `setup-codex.ps1` 優先重用本專案相容的 `.venv`；沒有時使用固定資產及 SHA-256 驗證的 uv，下載 Python 3.12 至專案內 `.bootstrap`，再建立 `.venv`。套件依 `requirements.txt` 安裝及檢查版本範圍。不改系統 Python、shell profile、全域 PATH 或其他 skills。

**先產生 PPTX，不要求安裝大型 PDF 匯出工具。** LibreOffice / Poppler 為選用；缺少時要如實回報 PDF 匯出／視覺 QA 未完成。Microsoft PowerPoint 不是產生 `.pptx` 的必要條件。

這不是離線免安裝包，也不是零權限提示。第一次需要網路、可使用本機 Codex 的帳號與足夠模型額度。不需要額外 OpenAI API key，不使用 AI 生圖。論文理解與撰稿由模型負責，不能宣稱文字完全不送到模型。

安裝器只證明本機必要環境和技術 smoke-test；**不證明 Codex 已登入、模型已讀 skill、額度足夠、或完整 journal club 已完成**。Codex 必須另行讀完整 SKILL.md 才提示上傳 PDF。

## 成品與安全

```text
sample-papers/        論文 PDF
outputs/              最終 PPTX，以及可用時產生的 PDF
.skill-work/          本次素材、規格、QA 及中間資料
.bootstrap/          專案內的 Python 管理工具與快取
.venv/               本專案的 Python 套件
.agents/skills/      隨專案載入的完整技能
```

Classroom 只使用 `full` 模式，不提供 lite 生成模式。投影片、原文數字、結論、圖表裁切和講者備註仍須人工複核。技術 QA 不是臨床認證；修改成品後需要重新驗證，不可沿用舊的通過聲明。

使用允許處理的論文。不要公開上傳病人個資、期刊原文、生成簡報、工作檔、帳密或 API key。內建範例皆為虛構教學資料。分享前閱讀 [NOTICE.md](NOTICE.md) 及 [資料安全與著作權](docs/PRIVACY.md)。

## 教師與進階文件

- [自動流程及失敗處理](CODEX-START.md)
- [教師流程與 A/B/C 分流](docs/CLASSROOM-INSTRUCTOR.md)
- [原 macOS 安裝與排錯](docs/QUICKSTART-MAC.md)、[原 Windows 安裝與排錯](docs/QUICKSTART-WINDOWS.md)
- [疑難排解](docs/TROUBLESHOOTING.md)、[提示詞參考](docs/PROMPTS.md)、[帳號額度](docs/FREE-PLAN.md)
- [可在其他專案使用的全域整合版](docs/GLOBAL-INSTALL.md)：來源版本 `v4.4.0`，不是這堂課的預設安裝路線；實際公開發布以該 Release 附檔為準。
- [正式發布流程](docs/PUBLISH-TO-GITHUB.md)

r2 教學包可用 `python tools/package_teaching_kit.py` 重新產生，附 SHA-256、來源 commit 與逐檔 manifest。全班使用同一份核對過的程式碼；Python 套件仍依宣告範圍下載，不能把它稱為完整鎖版或離線 runtime。

舊版 `START-HERE.md`、學生 HTML/PDF 與手動檢核工具保留為教師排錯備援，不再要求學生先照做一遍。舊 PDF 不會因 repository 改動而自動更新。
