# 自動流程遇到問題

本文件給協助學生的 Codex／教師使用。唯一入口仍是 [CODEX-START.md](../CODEX-START.md)，從失敗階段接續。

| 卡住的位置 | Codex 應採取的下一步 |
| --- | --- |
| 只有一般聊天或遠端 Cloud | 引導學生使用支援 Local workspace 的 Codex；不能宣稱已安裝到學生電腦。 |
| 工作資料夾已有其他內容 | 不清空、不覆蓋；辨識同一版本或改用新的空白資料夾。 |
| 下載、TLS、雜湊或防毒阻擋 | 說明哪一項失敗及最小必要批准；不關閉防毒、不忽略驗證、不繞過機構政策。 |
| 磁碟空間不足 | 清出足夠空間後從 setup 接續；LibreOffice、Poppler、Python 與 cache 需要額外空間。 |
| `.venv` 損壞或版本不相容 | 保留現況，說明後再取得刪除／重建授權。 |
| `setup.lock` 已存在 | 確認是否仍有安裝程序；不可盲目刪鎖或同時執行兩次。 |
| LibreOffice／Poppler 安裝或版本檢查失敗 | 停在 `SETUP_BLOCKED`；不得降級為 PPTX-only。檢查網路、架構、磁碟與機構政策後重跑同一 setup。 |
| 合成 PPTX 可建檔但 render 失敗 | 視為完整環境未通過；查看 LibreOffice/Poppler 階段，修復後重跑，不要求學生先交論文。 |
| skill 選單未出現 | 直接讀取完整 repository `SKILL.md`；檔案存在不能代替模型讀取。 |
| PDF 附件沒有本機路徑 | 指出本專案 `sample-papers` 完整位置，請學生放入；不得猜測掛載路徑。 |
| 多篇、加密、錯篇、缺頁或病人個資 | 暫停，只問解除阻礙所需的一個問題。 |
| 額度不足或工作中斷 | 保留 `.skill-work` 與輸出，恢復後接續，不重新安裝或重做已完成階段。 |
| spec/final/render QA 失敗 | 修正規格或素材，再跑原 gate；不得修改檢查標準取得通過。 |

## 安裝與驗證

由 Codex 在專案根目錄執行 `bash setup-codex.sh` 或 `.\setup-codex.ps1`。完整成功條件是：

- Python 與必要套件通過
- 固定版本 LibreOffice、Poppler 通過
- 合成 smoke-test 通過
- 合成 PPTX 實際轉成 PDF
- slide preview/contact sheet 實際產生

只有 `.skill-work/codex-setup.json` 顯示 `FULL_QA_READY_SKILL_PENDING`，Codex 才能讀 skill 並要求論文。舊 receipt 不能取代本次命令。

## 隱私

回報教師的是失敗階段與去識別摘要，不是完整路徑、原始日誌、論文全文或帳密。不要把 PDF、PPTX、`.bootstrap`、`.venv` 或 `.skill-work` 提交到 GitHub。
