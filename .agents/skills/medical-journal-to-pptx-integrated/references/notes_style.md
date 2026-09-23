# Speaker Notes Style Guide

This is the most important reference. The notes make this deck useful for
teaching — without them, you've just made a pretty pptx. Copy these patterns
closely.

## Core rules

1. **Language**: Traditional Chinese (繁體中文). Technical terms stay English,
   wrapped in `**bold**`, with a Chinese gloss in parentheses on first use.
2. **Opening**: Every note block places a lead emoji in its opening scan block
   (the first 96 characters) to telegraph the slide's purpose (📊 for data,
   📌 for key definition, ⚠️ for caution,
   🎯 for core concept, 🔑 for takeaway, 📋 for checklist, 💡 for insight,
   🙏 for thanks, 📧 for contact, 📖 for references).
3. **Structure**: Use visible bullets (`•`), sub-emojis (✅❌→), and short
   lines. Never write flowing paragraphs — the presenter must scan in 2
   seconds.
4. **Closing**: End content slides with a takeaway line led by ✅ 💡 or ⚠️.
5. **Figure/Table slides**: Open with `【圖片說明 — <label>】` and describe
   each labeled sub-image in turn, then close with 💡 clinical meaning.
6. **Page specificity**: Never reuse the same normalized note on more than two
   slides. Short repeated phrases, glyph padding, non-string note values, and
   Simplified-Chinese-only forms fail QA.

## Example 1 — Title slide

```
各位好，今天我要為大家介紹的是這篇 **medical journal article**（醫學期刊論文）。

📌 這篇文章的核心主題是 **<main clinical topic>**（主要臨床主題）。

🎯 研究目的：評估 **<intervention / imaging feature / model / guideline>**（研究介入、影像特徵、模型或指引）對臨床決策的影響。

🔬 核心發現：作者提出的主要結果可改變診斷、分層、治療或追蹤策略。

➡️ 首先，讓我們看這篇文章想解決的臨床問題...
```

**Why it works**: greets the audience, states topic, purpose, and headline
finding, then transitions into the deck.

## Example 2 — Outline slide

```
📋 本次簡報共分為九大部分：

1️⃣ **Background**（背景介紹）— 臨床問題與既有知識缺口

2️⃣ **Methods**（研究方法）— 研究設計、族群與評估方式

3️⃣ **Results**（研究結果）— 主要結果與臨床意義

4️⃣ **Costal PN**（肋骨肋膜附著結節）

...
```

Notes are brief — the slide already shows the list; notes reinforce each
item's purpose.

## Example 3 — Context / background content slide

```
📊 這張投影片說明 **clinical problem**（臨床問題）的重要性。

• 這個問題會影響診斷、預後、治療選擇或資源分配

⚠️ 目前挑戰：
• 既有方法仍有不確定性、變異性或實作困難
• 臨床上需要更可靠的判讀或決策依據

✅ 本文切入點：
• 作者評估新的影像特徵、模型、分類、介入或指引

💡 這說明為什麼這篇文章值得做成 journal club 簡報
```

## Example 4 — Historical timeline slide

```
📜 這張投影片整理本主題的關鍵研究脈絡：

📅 <Year 1> — **Study / guideline name**（研究或指引名稱）
   建立最早的核心概念或分類

📅 <Year 2> — **Larger validation study**（大型驗證研究）
   驗證臨床效益或診斷效能

📅 <Year 3> — **Recent update**（近期更新）
   修正標準、納入新技術，或改變臨床建議

✅ 本篇文章是在這些證據基礎上，回答下一個臨床問題
```

Each 📅 entry: year — **StudyAcronym**（full name，中文gloss），一行結論.

## Example 5 — Definition / concept slide

```
🎯 這是本篇最核心的定義：

📌 **Key term**（關鍵術語）：
請用文章中的原始定義說明，不要自行改寫成另一套標準

適用範圍：

🔹 納入條件
🔹 排除條件
🔹 判讀標準
🔹 臨床使用情境

💡 本篇關鍵是把這個術語轉成可操作的臨床判斷
```

## Example 6 — Evidence / cited-study slide

```
📊 **Firstauthor et al**（Year）研究：

👥 研究族群：<sample size and population>
📈 研究設計：<retrospective / prospective / trial / review>
🔍 主要評估：<imaging feature / test / intervention / outcome>
⏱️ 追蹤或資料期間：<duration if available>

📋 關鍵定義：
用文章原文的標準描述，不自行新增條件

📊 結果：
• <primary result>
• <secondary result>

✅ 這個研究支持本文後續的核心論點
```

Pattern for cited studies: author+year header → cohort size → key definition
→ results → clinical significance marker.

## Example 7 — Table slide (figure slide for a data table)

```
【圖片說明 — Table 2：研究結果或文獻證據匯總表】

此表位於文章的結果或討論章節，匯總了關鍵研究數據。

📊 表格重點：

【第一列 / 第一組】
• 族群：<population>
• 樣本數：<n>
• 主要結果：<result>

【第二列 / 第二組】
• 族群：<population>
• 樣本數：<n>
• 主要結果：<result>

...

📌 核心數據：
請挑出最能支持結論的數字，不要逐格照念

⚠️ 若表格有 subgroup 或限制，必須提醒聽眾解讀邊界。
```

## Example 8 — Figure slide with labeled sub-images

```
【圖片說明 — Figure N：代表性研究影像或圖表範例】

此圖位於文章的相關章節，展示本文最重要的影像、圖表或模型輸出。

📌 各 panel 重點：

【A: <label>（中文）】說明 A panel 的關鍵所見

【B: <label>（中文）】說明 B panel 的關鍵所見

【C: <label>（中文）】說明 C panel 的關鍵所見

【D: <label>（中文）】說明 D panel 的關鍵所見

💡 臨床要點：用 1-2 句說明這張圖如何改變判讀或管理。
```

Always describe every labeled panel (A, B, C, D, E, F or 1, 2, 3…). Use
bracket notation 【X: Name（中文）】 for consistency.

## Example 9 — Takeaways slide

```
🔑 四大核心要點：

1️⃣ **Clinical problem**（臨床問題）
   • 本文處理的是一個會影響臨床決策的問題

2️⃣ **Method**（研究方法）
   • 研究設計與資料來源決定證據強度

3️⃣ **Main result**（主要結果）
   • 最重要的數字或圖表支持作者的核心結論

4️⃣ **Clinical implication**（臨床意義）
   • 說明應如何影響診斷、追蹤、治療、工作流程或 AI 開發
```

## Example 10 — Recommendations by audience

```
📋 對不同對象的建議：

👨‍⚕️ 對臨床專業人員：
✅ 報告中清楚描述本文定義的關鍵研究發現
✅ 說明不確定性與建議下一步

💻 對 AI 開發者：
✅ 將本文可操作的標籤、終點與錯誤類型轉成模型監測項目
✅ 注意資料偏差、外部驗證與臨床可解釋性

👨‍⚕️ 對臨床醫師：
✅ 根據本文證據調整後續檢查、治療或追蹤策略
```

## Example 11 — Thank-you slide

```
🙏 謝謝大家的聆聽！

❓ 有任何問題歡迎提出

📧 通訊作者：
**Corresponding Author Name**
Institution
email@example.com

📖 原文出處：
**Journal Name** Year; volume(issue):pages
**DOI**: <doi>
```

## What to avoid

- **Don't use simplified Chinese** (简体) — the reference deck is traditional.
- **Don't over-translate**. Keep `OR`, `95% CI`, `HR`, `p-value`, `sensitivity`,
  `specificity` in English. These are read as English by clinicians.
- **Don't write paragraphs**. Break every thought into a bulleted line.
- **Don't forget emojis**. They're not decoration — they're scanning landmarks
  for a presenter reading the notes during a talk.
- **Don't duplicate slide body text verbatim** into the notes. The notes add
  the *why* and the *what to say*, not the bullets already on the slide.
- **Don't hallucinate numbers**. If a statistic isn't in the paper, leave it
  out. It's better to have a sparser note than a wrong one.
