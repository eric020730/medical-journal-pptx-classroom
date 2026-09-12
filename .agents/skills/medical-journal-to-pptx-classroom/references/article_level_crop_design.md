# Article-Level Crop Design

## Goal

Produce one usable crop per article Figure/Table item, not one crop per PDF image object.

## Pipeline

1. Render pages and extract text/words as in v0.2.4.
2. Manually build the expected figure/table list from caption-like text.
3. Use object candidates, page renders, and table crops as planning inputs.
4. For each expected label, verify nearby candidate components against the paper.
5. Merge components into article-level final assets when needed.
6. Preserve manual crop coordinates or notes in `crop_overrides.json`.
7. Add unresolved crop concerns to the working notes and `crop_review.md`.

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

## Source-coordinate crop tool

Use `journal run source_crops plan.json --out NEW_DIRECTORY` for reviewed table
and multi-panel crops. Coordinates are `[x0,y0,x1,y1]` in PDF points, with
one-based page numbers. Read the source page before assigning them. The tool
renders the PDF (including vector flowcharts), preserves original panel letters,
and pads rather than trimming or stretching medical images.

The local plan has `pdf`, `source_sha256`, `dpi` (default 300),
`expected_assets` (all article Figure/Table IDs), and `assets`:

- Table: `id`, `type: "table"`, `page`, `bbox`, `expected_text` with source
  title, column-heading, final-row and footnote anchors. For tall tables add
  `header_bottom` and ordered `splits` (PDF y coordinates). The tool repeats
  only the header and partitions the entire body without gaps. Choose splits
  between complete row groups, not within groups. Footnotes remain in the final
  part. All parts have the same horizontal bounds; never crop the right column
  to equalize widths.
- Figure: `id`, `type: "figure"`, `expected_labels` in original reading order,
  and `panels` with `label`, `page`, `bbox`, optional `expected_text` anchors.
  Each crop must include the original printed panel letter. Match the source
  image and caption before recording the letter; a matching letter alone does
  not prove the medical panel is correct. `columns` defaults to 2.

The command rejects partial text/image boundaries, missing anchors, source-hash
changes and inventory mismatches before writing. It saves per-panel images,
composites, a gallery, a contact sheet and provenance with output hashes.
Existing output directories are rejected to preserve earlier reviewed versions.

Limitations: PDF text bounds are conservative and may include invisible text;
the tool cannot establish table identity or semantic completeness from a few
anchors. Scanned text, vector strokes and incorrect-but-self-consistent plans
still require visual review. Inspect all panels, headers, rows and footnotes
against the complete source page. `STRUCTURAL_PASS_VISUAL_REVIEW_REQUIRED`
must not be reported as a final visual pass. Keep article-specific plans and
images in `.skill-work/`, never in git or the released skill.
