# 全域整合版 Skill：安裝、升級與解除安裝

`medical-journal-to-pptx-integrated v4.0.0` 是真正獨立的全域 Codex
skill。安裝後不必打開 classroom repository；在任何專案或工作資料夾都可以
使用 `$medical-journal-to-pptx-integrated`。

## 功能與模式

全域整合版固定製作 40–55 張完整教學簡報，並提供兩種視覺風格：

| 內容 | 投影片 | 視覺 | 特徵 |
| --- | --- | --- | --- |
| `full` | 40–55 張 | `standard` | 完整 journal-club 與標準視覺 |
| `full` | 40–55 張 | `nice` | 完整 journal-club 與 nice 視覺 |

兩種風格都支援完整圖片處理、英文投影片、繁體中文講稿、單一 Figure
對應單一頁、native A/B/C/D panel labels、EMF vector tables、表格安全邊界、
建檔前／後雙階段 QA、PDF 灰階反相比對與完整影像來源鏈。

### 內容模式

全域整合版只接受 `--mode full`，或省略 `--mode` 以使用相同預設值。
repository 內的 `$medical-journal-to-pptx-classroom` 也只接受 `full`，
兩個 skills 互不覆寫。

## 從 GitHub release 下載

1. 開啟 [GitHub Releases](https://github.com/eric020730/medical-journal-pptx-classroom/releases/latest)。
2. 下載 `medical-journal-to-pptx-integrated-v4.0.0.zip` 及同名 `.sha256`。
3. 驗證 SHA-256，然後完整解壓縮。不要只複製單一 `SKILL.md`；scripts、
   references、logo 與 requirements 都是 skill 必要部分。

macOS / Linux：

```bash
shasum -a 256 -c medical-journal-to-pptx-integrated-v4.0.0.zip.sha256
unzip medical-journal-to-pptx-integrated-v4.0.0.zip
cd medical-journal-to-pptx-integrated-v4.0.0
bash install-global.sh install
```

Windows PowerShell：

```powershell
$archive = "medical-journal-to-pptx-integrated-v4.0.0.zip"
$expected = ((Get-Content "$archive.sha256") -split "\s+")[0]
$actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "SHA-256 mismatch" }
Expand-Archive $archive -DestinationPath .
Set-Location .\medical-journal-to-pptx-integrated-v4.0.0
.\install-global.ps1 install
```

也可以直接連按 `install-global.cmd`。若學校限制 PowerShell、Python 或套件
下載，請交由資訊管理員協助，不要規避機構安全政策。

## 全域安裝位置與 Python runtime

預設全域 skill 位置：

```text
macOS / Linux: ~/.agents/skills/medical-journal-to-pptx-integrated/
Windows:       %USERPROFILE%\.agents\skills\medical-journal-to-pptx-integrated\
```

若已設定 `CODEX_HOME`，改使用 `CODEX_HOME/skills/`。需要另一個 discovery
位置時，可使用 `--target <skills-parent-directory>`。

獨立 Python 3.11–3.13 runtime 位置：

```text
macOS / Linux: ~/.cache/medical-journal-to-pptx-integrated/venv/
Windows:       %LOCALAPPDATA%\medical-journal-to-pptx-integrated\venv\
```

`XDG_CACHE_HOME`、`MEDICAL_JOURNAL_PPTX_RUNTIME` 及
`MEDICAL_JOURNAL_PPTX_PYTHON` 可調整位置；runtime 不依賴 classroom repository
或任何專案的 `.venv`。LibreOffice 和 Poppler 只影響選用的 PDF 匯出／預覽，
不影響可編輯 PPTX 產生。

## 第一次使用

安裝後重新開啟 Codex 任務或重新整理 skills，於任何工作資料夾輸入：

```text
$medical-journal-to-pptx-integrated

請處理我提供的醫學期刊 PDF，使用 full 模式與 nice 視覺風格，製作
40–55 張英文投影片，每頁附繁體中文講稿。保留 Figures、Tables、
native panel labels，以及 PDF 灰階反相防護；完成建檔前／後 QA 後，
將最終 PPTX 和可用的 PDF 儲存到我指定的輸出資料夾。
```

若工作資料夾有 `AGENTS.md` 的輸出規則，skill 會遵守；否則最終 `.pptx` 和
`.pdf` 直接存到目前工作資料夾或使用者指定的位置。中間檔保留在工作資料夾
的 `.skill-work/<run-id>/`，不可提交至 GitHub。

若手邊沒有授權論文，可直接在任意工作資料夾產生完全虛構、沒有病人資料的
示範 PDF；release 不需夾帶任何使用者論文：

```bash
python3 ~/.agents/skills/medical-journal-to-pptx-integrated/scripts/run.py demo \
  --out synthetic-medical-journal-demo.pdf
```

Windows PowerShell：

```powershell
py -3 "$env:USERPROFILE\.agents\skills\medical-journal-to-pptx-integrated\scripts\run.py" `
  demo --out synthetic-medical-journal-demo.pdf
```

## 升級、檢查與解除安裝

下載並驗證新版 release ZIP，完整解壓縮後執行：

```bash
bash install-global.sh status
bash install-global.sh upgrade
bash install-global.sh uninstall
```

Windows：

```powershell
.\install-global.ps1 status
.\install-global.ps1 upgrade
.\install-global.ps1 uninstall
```

需要一併移除獨立 Python runtime 時，加上 `--purge-runtime`。解除安裝只會
移除 `medical-journal-to-pptx-integrated`，不會刪除任何其他 skill。
升級失敗會自動回復原本的整合版。

進階使用者可直接執行跨平台 Python 安裝程式：

```bash
python3 install-global.py install --target /path/to/global/skills
python3 install-global.py upgrade --target /path/to/global/skills
python3 install-global.py uninstall --target /path/to/global/skills
```

`--skip-deps` 只適合已自行管理 Python 套件的 CI 或進階環境。
