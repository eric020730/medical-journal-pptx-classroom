# 教師授課建議

## 課前一週

1. 建立私人 GitHub repository，或確認公開分享的授權。
2. 執行 `journal package`，抽查 `dist/` ZIP 內沒有學生論文、病人資料或舊簡報。
3. 使用一台 macOS 和一台 Windows 電腦，各完成一次全新安裝。
4. 使用至少一個免費帳號測試 Codex 與自訂 skill 是否可用。
5. 確認教室網路允許 Homebrew、WinGet、PyPI 與 OpenAI 登入。
6. 如果學生使用受管制的醫院／學校電腦，請先聯絡資訊部門。
7. 準備沒有病人個資、且允許教學使用的 PDF；不要把受版權保護的期刊直接放進公開 repository。

## 建議 60–90 分鐘課程

| 時間 | 活動 | 成果 |
| --- | --- | --- |
| 0–10 分鐘 | 說明 Codex、Skills、Free 與付費額度差異 | 學生理解限制 |
| 10–25 分鐘 | 安裝 repository 與系統環境 | `journal doctor` 通過 |
| 25–35 分鐘 | 執行 `journal smoke-test` | 確認可以產生 PowerPoint |
| 35–55 分鐘 | 使用虛構論文與 `full` 模式 | 開始製作 40–55 張簡報 |
| 55–75 分鐘 | 換成經授權的真實文章 | 比較不同 prompt 與圖表選擇 |
| 75–90 分鐘 | 討論臨床正確性、版權、幻覺及 QA | 完成內容複核 |

## 免費帳號與付費帳號分流

- 免費帳號：先用示範 PDF 確認可用額度足以完成 `full` 簡報。
- Plus／Pro／學校授權帳號：可使用 `full` 模式處理較長文章。
- 若免費帳號無法載入自訂 skill，先請 Codex 直接讀取 repo 裡的 `SKILL.md`；若仍不支援，改以教師示範或共用學校授權電腦。

## 教師應檢查的成果

- 是否真的使用正確論文，而不是沿用舊簡報內容。
- 英文投影片是否正確呈現研究方法與結果。
- 繁體中文講者備註是否完整且沒有捏造文獻資訊。
- Figure／Table 裁切是否保留圖例、箭頭、標註及欄位。
- CT、X 光、MRI 與組圖各 panel 是否和原 PDF 具有相同黑白方向。
- `qa-spec` 是否在建檔前通過，且 `journal qa` 是否驗證完成的 PowerPoint。
- 一個 Figure 是否只出現在一張主要圖表投影片。
- AI 推論與原始研究數據是否清楚區分。
- 是否誤放病人個資或受版權保護的內容到 GitHub。

## 更新學生版本

使用 Git 下載的學生：

```bash
git pull
```

macOS 再執行：

```bash
./setup-macos.command
```

Windows 再執行：

```powershell
.\setup-windows.cmd
```

下載 ZIP 的學生請重新下載新版，並自行保留 `outputs/` 內的成品。
