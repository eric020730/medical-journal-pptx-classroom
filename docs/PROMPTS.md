# 可直接複製的課堂提示詞

## 第一次安裝後的示範

```text
$medical-journal-to-pptx-classroom

請使用 full 模式處理 sample-papers/classroom-demo-paper.pdf。
製作 40–55 張英文教學投影片，每張投影片都要有繁體中文講者備註。
保留所有重要 Figure 和 Table，並清楚說明文章與數據皆為虛構示範。
完成 QA 後把 PowerPoint 儲存到 outputs。
```

## 完整範例文章練習

```text
$medical-journal-to-pptx-classroom

使用 full 模式產生 40–55 張投影片，處理我附上的 PDF。
使用英文投影片、繁體中文講者備註及所有重要圖表。
不要生成 AI 圖片；通過 QA 後輸出 PPTX。
```

## 正式放射科 journal club

```text
$medical-journal-to-pptx-classroom

使用 full 模式處理我附上的醫學期刊論文，建立完整放射科 journal club 教學簡報。
請包含研究背景、臨床問題、研究設計、收案條件、影像技術、主要結果、
重要 Figures／Tables、統計意義、影像判讀重點、研究限制與臨床應用。
投影片文字全部使用英文；每張投影片提供完整繁體中文講者備註。
請比對原始 PDF 與擷取影像，避免 CT、X 光或 MRI 黑白反相；
完成 image polarity audit、建檔前 qa-spec、PowerPoint QA 及可用的 PDF 匯出後再交付。
```

## 住院醫師教學導向

```text
$medical-journal-to-pptx-classroom

使用 full 模式製作住院醫師教學簡報。
每個影像案例請說明觀察順序、典型徵象、重要鑑別診斷、常見誤判與臨床下一步。
所有重要原文圖片維持一個 Figure 對應一張投影片；繁體中文講者備註需逐圖說明。
若 Figure 包含 A／B／C／D 多張影像，請檢查每個 panel 的灰階方向、來源與標籤位置。
```

## 指定自己的 PDF

```text
$medical-journal-to-pptx-classroom

使用 full 模式處理 sample-papers/my-journal.pdf，
製作 40–55 張英文教學投影片與繁體中文講者備註。
```

請先將 `my-journal.pdf` 改成實際檔名。路徑包含空白或中文也可以使用。

## 中斷後接續

```text
請繼續同一個簡報任務，讀取目前 .skill-work 裡的 run.json、RUN_MANIFEST.md
與已經產生的 deck_spec.json，從尚未完成的階段接續。
不要覆寫既有成品，完成 QA 後將 PPTX 儲存在 outputs。
```

## 只需要診斷環境

```text
請先執行本專案的 journal doctor，說明 Python 套件、LibreOffice、Poppler
及 Codex skill 是否正常，再告訴我缺少哪些項目。
```
