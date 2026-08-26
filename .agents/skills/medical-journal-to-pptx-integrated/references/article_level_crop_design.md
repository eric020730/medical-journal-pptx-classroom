# Article-Level Crop Design

## Goal

Produce one usable crop per article Figure/Table item, not one crop per PDF image object.

## Pipeline

1. Render pages and extract their text and word-position metadata.
2. Manually build the expected figure/table list from caption-like text.
3. Use object candidates, page renders, and table crops as planning inputs.
4. For each expected label, verify nearby candidate components against the paper.
5. Merge components into article-level final assets when needed.
6. Preserve manual crop coordinates or notes in `crop_overrides.json`.
7. Add unresolved crop concerns to the working notes and `crop_review.md`.
8. Keep intermediate panel crops unpadded. After all crop and seam decisions are
   complete, add the exact 16 px final safety canvas; include it in multi-panel
   fit and native-label geometry rather than appending it afterwards.

## Caption Detection Heuristics

Accept caption-like labels when:

- line starts with `Fig`, `Figure`, or `Table` after optional whitespace;
- followed by an integer or supplement label;
- followed by dash, em dash, colon, period, or enough caption text;
- line bbox is not inside a long body paragraph.

Reject likely inline references when:

- label is inside parentheses mid-sentence;
- line contains many body-text words before the label;
- label appears in a References section.

## Panel Grouping Heuristics

Group on same page when:

- candidate bboxes lie in same caption search zone;
- pairwise horizontal/vertical gaps are small relative to panel size;
- bboxes form rectangular grid alignment;
- OCR/text layer has A/B/C/D labels near panels;
- caption text references A/B/C/D.

## Failure Mode

If confidence is low, do not silently choose. Use a manual full-page-render crop
and record the decision in `crop_overrides.json`.
