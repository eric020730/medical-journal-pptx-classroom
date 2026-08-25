# Medical Journal -> Teaching PPTX

Current version: `v0.2.38-bg-aware-trim`

## Portable Global Runtime And Output

This reference preserves the complete upstream v0.2.38 workflow inside the
globally installed integrated skill. Resolve the skill directory from this
reference, execute bundled helpers through `scripts/run.py`, and select
`--style standard` or `--style nice` independently of `--mode full`.

Resolve the active workspace and final output directory from the user's request
and applicable `AGENTS.md`; never require a classroom repository, user-specific
Python path, or source PDF's cloud directory. Save completed PowerPoint and
optional PDF files directly in that resolved output directory. Keep intermediate
assets, manifests, deck specifications, and previews in a private
`.skill-work/<run-id>/` folder.

This version ADDS background-aware edge trimming to the `trim` and `labels`
commands of `scripts/postprocess_assets.py`. It does not replace the existing
white-based crop — it is layered on top of it (see the "Background-Aware Edge
Trimming" section below). Every other behaviour is preserved unchanged from
`v0.2.37-native-panel-labels`.

This version adds an optional **native post-build panel-label** method (see the
"Native Post-Build Panel Labels" section below and
`scripts/recompose_panels_banded.py`, `scripts/add_panel_labels.py`,
`scripts/measure_label_gaps.py`). It stamps A/B/C/D onto the finished `.pptx` as
fixed-point-size text so every label has the SAME actual on-screen size
regardless of each figure's scale, with precise control of the gap above (to its
own panel) and below (to the next row). The prior burned-in label methods
(`recompose_panels_aligned.py` and the builder's `panel_labels`) remain
available and unchanged for backward compatibility.

This version preserves the complete `v0.2.10-panel-microcrop-flowchart-safe`
workflow and generalizes it for any medical journal article. Do not carry over
article-specific titles, authors, citations, crop boxes, figure dimensions, or
example diagnoses from prior runs.

- Non-flowchart figure panels may receive a conservative 2 px inward
  micro-crop after normal trimming to reduce thin white edge pixels.
- Flowchart figures do not receive panel micro-crop; preserve flowchart boxes,
  arrows, connectors, text, and accepted outer-frame edges.
- Tables never receive panel micro-crop; use preservation padding or verified
  extractor crops so complete table content and gridlines remain visible.
- Final table assets must preserve a stable outer white safety margin on all
  four sides. Do not deliver table crops that are tight to the text or grid.
  Use `TABLE_SAFETY_MARGIN_PX = 12` as the default final padding; acceptable
  range is 8-24 px after visual QA.
- For a generous, consistent look, the final table white margin should match
  the vector-figure (flowchart) white pad AS IT APPEARS ON SCREEN, not just in
  source pixels. Because each asset is scaled by a different factor to fit the
  slide image box, equal source px do NOT give equal on-screen white. Target the
  vector-figure on-screen margin (the flowchart's 44 px at 300 DPI fit ~ 0.176
  in on a 12.10x4.85 in box) and solve the per-table source margin for the
  limiting dimension:
      margin_px = target_in * content_dim_px / (box_dim_in - 2 * target_in)
  using width for wide tables (the usual case) and height if height-limited.
  This makes every table's on-screen white band equal to the flowchart's. The
  8-24 px rule still governs the minimum safety gap so content/gridlines never
  touch the edge.
- The Dr. Leether logo must render at the upper-right of all non-title and
  non-thank-you slides. If a user-supplied or generated `meta.logo_path` is
  invalid, fall back to the skill's bundled default logo and fail QA if no logo
  is embedded.

Convert a medical journal PDF into a polished 40-55 slide presentation (target 40-50):
English slide-visible text, Traditional Chinese speaker notes, and dedicated
slides for important Figures and Tables.

## Hard Rules

- One-figure-one-slide invariant (HARD GATE). Each paper Figure maps to EXACTLY
  ONE `figure` slide and EXACTLY ONE final `image` asset. Splitting a labeled
  multi-panel figure into per-panel crops is an INTERMEDIATE step only: its
  outputs (`panel_a.png`, `panel_b.png`, ... or any `*_panel_*` file) MUST be
  recomposed back into a single image (via `recompose_panels_aligned.py` or
  `postprocess_assets.py recompose-panels`) BEFORE that figure enters
  `deck_spec.json`. Never reference an individual panel crop as a slide `image`.
  Never emit one paper Figure as two or more slides (e.g. `Figure 3A`,
  `Figure 3B` as separate slides). The deck spec must not contain the same paper
  Figure number on more than one `figure` slide. Splitting a single paper TABLE
  into `Table 1A`/`Table 1B` for height reasons is the only allowed
  multi-slide-per-item case and follows section 4A. `audit-final` enforces this
  gate.
- Slide-visible text is English only: titles, bullets, outline items, footers,
  captions, authors, and citations.
- Outline slides should use numbered emoji markers such as `1️⃣`, `2️⃣`,
  `3️⃣` plus slide-range hints when the final sequence is known, e.g.
  `1️⃣ Background — slides 3-7`. `build_outline` renders each item as a card:
  a numbered accent badge, the topic title (leading emoji/number stripped), and
  a right-aligned `Slides X–Y` pill on a rounded row band. Rows are split as
  `"<emoji> Topic — Slides A-B"`; the builder parses the title and range. Cards
  are evenly distributed and vertically centered for any row count, kept clear
  of the footer line, and the title/badge/pill type auto-scales down when there
  are many rows so a long outline stays uncramped.
- Content slide-visible body text must use a structured teaching style rather
  than a flat list of same-level bullets. Prefer 2-4 short English section-label
  blocks such as `• Study design:`, `• Key finding:`, `• Imaging meaning:`, or
  `• Clinical implication:` followed by 1-2 concise supporting lines.
- For slide-visible body logic, use `→` for interpretation/consequence and a
  single restrained visible emoji such as `✅` only for a take-home, clinical
  impact, or conclusion line. Decorative emoji scatter is invalid.
- A normal content slide that is only 4-6 undifferentiated bullets with no
  section labels, no implication line, and no takeaway fails slide-body QA.
- Slide-visible body detail rules: do not use more than 3 consecutive lines
  that start with the same marker; include a blank-line section break on most
  content slides; use a final landing line on evidence, definition,
  recommendation, and takeaway slides when clinically appropriate.
- Speaker notes are Traditional Chinese. On first use, write English medical
  terms as `**Term**（中文翻譯）`; the builder converts `**...**` into real bold
  notes text.
- Speaker notes must be scan-friendly and structured, not all prose paragraphs.
  Use lead emojis and bullet/sub-emoji scaffolding for outline, content,
  figure/table, references, and thank-you notes. A completed deck with notes on
  every slide but zero emoji in the notes is invalid.
- Figure/Table notes must explicitly map to visible panels or table parts when
  present, using labels such as `【A 圖】`, `【B 圖】`, `Table 1A`, or
  `Table 1B` rather than generic image commentary.
- When the user asks to create, remake, regenerate, or redo a presentation,
  regenerate the complete deck from the source paper: Figure/Table assets,
  slide outline, slide-visible text, captions, and speaker notes. Do not reuse
  old deck specs, old PPTX content, old speaker notes, or old extracted assets
  as the content source unless the user explicitly asks for reuse.
- Prior versions may be used only as regression references or QA comparison
  material. If any old content is intentionally reused, document exactly what
  was reused, why, and the user's explicit reuse instruction in `RUN_MANIFEST.md`.
- For Eric's medical journal decks, use full teaching-script speaker notes as
  the quality and depth benchmark: clinical decision context, diagnostic search
  paths, radiology interpretation points, and figure/table-specific
  explanations. Regenerate those notes from the current paper; do not rely on
  external prior-version note content.
- Use the current v0.2.11 asset pipeline for figures and tables: fresh PDF
  extraction, crop review, panel-level post-processing, table same-width
  normalization, panel-label normalization, `audit-final`, and the build gate.
- Every Figure and Table in the paper must be accounted for. If the final deck
  omits one, document why in the working notes.
- Prefer article-level Figure/Table assets over raw PDF object-level crops.
- Keep manual crop repairs reproducible in `crop_overrides.json` when automatic
  crops are incomplete.
- Multi-panel figure labels must be normalized. Remove original A/B/C/D labels
  from the figure image crop and re-add them through `panel_labels` in the deck
  spec. Do this consistently rather than mixing original embedded letters with
  externally rendered labels.
- Labeled non-flowchart multi-panel figures MUST ALWAYS be split into individual
  panel crops before final deck assembly. There is no documented-exception path
  for these figures: delivering the original journal composite (panels left
  joined with source-page white between them) is not permitted. Remove
  source-page white gutters between panels, trim each panel independently, and
  rebuild with controlled layout gaps whose fill color is `bg_page` so no white
  strip remains between panels.
- For labeled multi-panel figures, `panel_labels` alone is not sufficient when
  panel geometry cannot be inferred. The deck spec must include per-panel slot
  geometry, `panel_boxes`, `panel_label_x_fracs`, or an equivalent validated
  map so labels render outside each panel at the lower-right edge. Missing
  geometry is a build/QA failure.
- Figure crops should be tight to the image content. Remove surrounding white
  margins from figure assets so the visible crop contains the figure itself,
  not excess page whitespace. Do not crop away image anatomy, annotations,
  arrows, axes, legends, scale bars, or other semantic content.
- For non-flowchart figure panels on dark slides, a final 2 px inward
  micro-crop is allowed after normal content trimming when visual QA shows
  thin white edge pixels. Keep this conservative and do not use it if it would
  cut labels, axes, legends, anatomy, arrows, risk tables, or annotations.
- Do not apply panel micro-crop to flowcharts, algorithms, or vector diagrams.
  Preserve all outer frame edges when they help protect internal boxes,
  connectors, arrows, text, or semantic layout.
- Do not apply panel micro-crop to tables. Tables use `table_micro_crop_px = 0`
  and should preserve complete content, gridlines, titles/captions, headers,
  first/last columns, footnotes, abbreviations, and source lines.
- Table final assets must not use zero-margin trimming. A table sidecar with
  `command: trim` or `command: labels` and `margin: 0` is invalid for final delivery
  unless a documented exception in `RUN_MANIFEST.md` proves that an alternate white
  canvas/padding step was applied after trimming. Default table final margin is
  `TABLE_SAFETY_MARGIN_PX = 12`; acceptable range is 8-24 px.
- If any table text, gridline, caption, footnote, abbreviation, source line,
  first/last row, or first/last column touches the final crop edge, QA fails.
  Rebuild from the verified source crop with table safety margin instead of
  applying inward crop.
- Do not trust automatic PDF image crops blindly. Always run the crop review
  gate before writing the deck spec.
- Final Figure/Table assets must pass `scripts/postprocess_assets.py` before
  deck assembly. The helper writes a `.postprocess.json` sidecar for every
  accepted final asset; `build_deck.py` fails by default when a Figure/Table
  slide points to an asset without that sidecar.
- Logo path handling is a hard gate. Do not write fragile generated paths that
  omit the workspace root. If `meta.logo_path` is absent, invalid, or stale, use
  the bundled `assets/dr_leether_logo.png`. Final QA must verify that the logo
  asset is embedded and visible on representative non-title/non-thank-you
  slides.
- Do not let article-specific `prepare_*.py` scripts write direct page-region
  crops into the final deck path unless those assets are immediately processed
  through `trim`, `labels`, `microcrop`, `split-table`, or `same-width` as
  appropriate. Direct page-region crops are intermediate sources, not final
  assets.
- Slide titles must follow the paper's native heading/subheading hierarchy
  whenever possible. Use paper headings and subheadings as the title source,
  not freely invented teaching headlines.
- Border removal must be conservative and type-aware. Do not remove a dark line
  merely because it touches the crop edge. Only remove a decorative outer table
  frame when QA can distinguish it from content, panel labels, flowchart boxes,
  axes, legends, or table text.
- Save final output in the user's workspace, not only a temporary directory.

## Vector Figure (Flowchart / Tree) Detection And Cropping

Before applying the multi-panel photo pipeline to a Figure, classify it as a
RASTER photo figure or a VECTOR figure (flowchart, tree, algorithm, diagram).
These use different cropping logic.

### Detection (content-based, automatic)

A paper Figure is a vector figure when, in its page region, there is a
substantial cluster of vector drawings (closed boxes + connector lines) and
that cluster contains essentially no embedded raster-image pixels. In practice
this is also implied when a paper Figure number has NO matching extracted raster
image: the missing figure is almost always a vector diagram. Tables are NOT
figures and are excluded (they are handled by the table pipeline).

Use `scripts/crop_vector_figure.py --detect-only` which reports
`is_vector_figure`, the diagram `bbox`, `raster_frac`, and box count.

### Cropping logic for a vector figure

Do NOT use embedded-image-rect crops, panel splitting, row alignment, or
A/B/C/D labels. Instead:

1. Collect the page's vector drawing rectangles, ignoring header/footer rules
   and any full-width page rule lines.
2. Merge them by 2D proximity into clusters; the largest cluster is the diagram.
3. The diagram bbox already encloses its label text (text sits inside the
   boxes), so do not expand the bbox with nearby body text or the caption.
4. Render that bbox at high DPI with a small safe margin, preserving ALL boxes,
   arrows, connectors, and text. Apply no panel micro-crop and no border removal
   that could touch the diagram.

```bash
python3 scripts/crop_vector_figure.py SRC.pdf final_assets/Figure_2.png --page 3
# detection only:
python3 scripts/crop_vector_figure.py SRC.pdf --page 3 --detect-only
```

### Optional: strip the outer frame and pad even white margins

Some flowcharts/trees are enclosed in a decorative outer rectangle frame. When
the user wants a cleaner look, remove that outer frame, trim to the actual
diagram content, then add a uniform white margin on all four sides:

```bash
python3 scripts/crop_vector_figure.py SRC.pdf final_assets/Figure_2.png \
  --page 3 --strip-outer-frame --white-margin 44
```

The cut targets the CONTENT bbox (union of all inner boxes + text, excluding
the outer frame rect) rather than a fixed inward inset. This is important when an
inner box sits only ~2 pt inside the frame edge (e.g. a bottom compartment box):
a fixed inset would clip it, but the content-bbox cut keeps it whole while still
excluding the frame stroke. The content bbox is clamped to stay >=1 pt inside the
frame, rendered, trimmed to content, then padded with even white margins. Internal boxes, arrows,
connectors, and text are preserved. This is opt-in: the default preserves
flowchart frames.

### QA additions

- [ ] Each paper Figure is classified raster vs vector before cropping.
- [ ] Vector figures keep every box, arrow, connector, and text label.
- [ ] No body text or caption is captured inside the vector crop.
- [ ] Charts/diagrams (flowcharts/trees) and tables get NO added thin border or
      hairline keyline. Only the clean diagram/table on even white margins.
      (A residual thin edge line is acceptable to remove only on raster photo
      panels, never added to charts or tables.)
- [ ] Vector figures are not panel-split, row-aligned, or given A/B/C/D labels
      unless the diagram itself is genuinely a labeled multi-panel figure.

## Multi-Panel Figure Layout (Row Alignment + Outside Labels)

This section governs labeled non-flowchart multi-panel figures. It does not
apply to flowcharts, algorithms, diagrams, or tables.

### Row-height alignment

Split labeled multi-panel figures into individual panel crops, then recompose so
that **all panels in the same row share one height**. Scale each panel to a
common row height (default = the minimum panel height in the figure, so panels
are only downscaled and stay crisp) while preserving each panel's aspect ratio.
Same-row panels must have aligned top and bottom edges even when the source
panels differ in size (e.g. a wide axial MRI panel and a square arthroscopy
panel in one row). Center each row horizontally and fill all gaps with the slide
background color (`bg_page`, default `#061428`) so gaps never appear white.

### Equal row width (align left/right edges across rows)

When a figure has multiple rows whose total widths differ (e.g. a wide A/B row
above a narrower C/D row), scale each row uniformly so **every row has the same
total width**. This aligns the left and right edges of all rows, so the figure
reads as a clean outer rectangle instead of ragged/centered rows. The narrower
row is enlarged to match the widest row. Skip this for single-row figures. This
is the default behavior of `recompose_panels_aligned.py` (`--equal-row-width`,
on by default; use `--no-equal-row-width` to center rows instead).

### Panel labels rendered OUTSIDE each panel

Remove the original printed A/B/C/D letters from each panel crop (crop to the
panel's image content so the printed letter is excluded). Re-add labels in the
**gap below each panel, right-aligned to that panel's right edge**.

- Label color = caption color (`text_secondary`, default `#8FA8C8`).
- Label weight = regular (non-bold) by default. Pass `--label-bold` only if
  bold A/B/C/D is explicitly wanted.
- Label size: prefer **consistent ON-SCREEN size across slides**. A fixed source
  px (e.g. 54) is NOT consistent on screen, because each figure is scaled by a
  different factor to fit the slide image box (a short figure like a 1-row pair
  is enlarged most, so its label looks biggest). Use
  `--label-screen-height-in 0.20` so the script derives the per-figure source px
  (compensating for each figure's fit scale) and every slide's label renders at
  the same visual height (~0.20 in). Pass the real slide image-box size via
  `--slide-box-w-in/--slide-box-h-in` if the template differs from 12.10x4.85 in.
- Do not pass `panel_labels` to `build_deck.py` for these figures; labels are
  already burned into the recomposed asset. The builder's `panel_labels` path
  only supports a single bottom row and would misplace labels on a 2xN grid.

### Helper command

```bash
python3 scripts/recompose_panels_aligned.py final_assets/Figure_3.png \
  --inputs panel_a.png panel_b.png panel_c.png panel_d.png \
  --cols 2 --labels A,B,C,D \
  --font-size 54 --label-color "#8FA8C8" --bg "#061428" --gap 16
```

`recompose_panels_aligned.py` now paints a thin `bg_page`-colored frame over
each panel's outer rim by default (`--panel-frame 3`). This hides residual
light-grey / film border lines that the near-white edge-trim (threshold 238)
does not remove, so no thin light edge shows against the dark slide. Keep it at
2-3 px; set `--panel-frame 0` only if a panel has essential content at the very
edge that must not be covered. Use `--panel-frame-color` to override the frame
color (defaults to `--bg`).

Panel crops should come from a high-DPI page re-crop using each panel's exact
embedded-image rectangle (this naturally excludes the printed panel letter).
After recomposing, write a `.postprocess.json` sidecar next to the asset so the
`build_deck.py` post-processing gate passes.

### QA additions

- [ ] Same-row panels share one height; top and bottom edges align.
- [ ] All gaps are `bg_page` color, no white strips between panels.
- [ ] No thin light-grey/white rim remains on any panel edge; the bg rim frame
      (`--panel-frame`, default 3 px) covers residual film/border lines.
- [ ] A/B/C/D appear below each panel at its right edge, in caption color.
- [ ] Every figure uses the same 54 px label size.
- [ ] Flowcharts and tables are unaffected by this logic.

## Native Post-Build Panel Labels (recommended for uniform label size)

The burned-in label methods above scale the A/B/C/D letters together with the
figure image. Because each figure is scaled by a different factor to fit the
slide image box, burned labels can render at different ON-SCREEN sizes across
slides (a tall 2xN figure shrinks more than a wide 1x2 pair, so its letters look
smaller). The `--label-screen-height-in` option of `recompose_panels_aligned.py`
mitigates this for burned labels, but the most robust solution is to add the
labels AFTER the deck is built, as native fixed-point-size text.

Use this method when you want (a) identical actual label size on every slide
regardless of figure scale/layout, (b) precise control of the gap above (to the
label's own panel) and below (to the next row), and (c) selectable/editable
label text in the final `.pptx`.

It is a three-step flow and uses three bundled scripts:

1. `scripts/recompose_panels_banded.py` — lay out the panel crops into one image
   WITHOUT burned labels, reserving a `bg_page`-colored band below every row, and
   emit per-panel label geometry (fractions of the composite) into a shared
   `panel_geometry.json`.
2. `scripts/build_deck.py` — build the deck as usual. Reference each recomposed
   image as an ordinary `figure` slide image. Do NOT pass `panel_labels` (labels
   are added in step 3). The recompose step writes a `.postprocess.json` sidecar
   so the build/audit asset gate passes.
3. `scripts/add_panel_labels.py` — stamp A/B/C/D onto the built `.pptx` as native
   text boxes at a fixed point size, positioned from `panel_geometry.json`.

```bash
# 1) recompose each multi-panel figure (no labels) + accumulate geometry
python3 scripts/recompose_panels_banded.py final_assets/Figure_3.png \
    --inputs panel_a.png panel_b.png panel_c.png panel_d.png \
    --cols 2 --labels A,B,C,D --geometry panel_geometry.json \
    --gap-above-in 0.06 --gap-below-in 0.12 --label-pt 18 \
    --bg "#061428" --slide-box-w-in 12.10 --slide-box-h-in 4.85

# 2) build the deck normally
python3 scripts/build_deck.py deck_spec.json --out deck.pptx

# 3) stamp native fixed-size labels onto the finished deck
python3 scripts/add_panel_labels.py deck.pptx deck_labeled.pptx \
    --spec deck_spec.json --geometry panel_geometry.json \
    --label-pt 18 --color 8FA8C8
```

Gap control. `--gap-above-in` / `--gap-below-in` are the on-screen gaps you want
(measured to the label glyph). The reserved band height equals
`gap_above + glyph_height + gap_below`, where `glyph_height = label_pt/72 *
glyph_ratio`. The band is solved in pixels so it renders at the requested
on-screen inches for each figure's fit-scale; combined with the fixed-point-size
native label, both the label size and the two gaps come out identical on every
figure.

Calibration (LibreOffice/PowerPoint Calibri/Carlito defaults):
`--label-pt 18` → glyph height ≈ 0.155 in; `--glyph-ratio 0.62`;
`--center-offset-in 0.0525`. If you change font/size/renderer, run
`scripts/measure_label_gaps.py` on a rendered slide and nudge `--center-offset-in`
(shifts both gaps oppositely) and `--glyph-ratio` (changes the band split) until
the printed `gap_above`/`gap_below` match your target (1-2 iterations).

```bash
soffice --headless --convert-to pdf --outdir qa deck_labeled.pptx
python3 scripts/measure_label_gaps.py deck_labeled.pptx qa/deck_labeled.pdf \
    --spec deck_spec.json --geometry panel_geometry.json --figure Figure_3
```

`--label-pt` MUST be the same in steps 1 and 3. Figure slides are matched to
geometry entries by the `image` basename in `deck_spec.json`; the figure picture
is located as the largest picture on the slide so the corner logo is ignored.
Single-row figures only have a meaningful `gap_above` (no next row below).

### QA additions (native labels)

- [ ] `--label-pt` matches between recompose and add_panel_labels.
- [ ] Measured `gap_above` / `gap_below` match the target within ~1 px.
- [ ] All A/B/C/D render at one identical actual size across every figure slide.
- [ ] Labels are real text (selectable), in caption color, at each panel's
      lower-right, hugging their own panel (smaller gap above than below).
- [ ] Tables and flowcharts receive no panel labels.

## Future Version Hygiene

Every future version of this skill must remain generic across medical journal
types. Do not promote any single completed deck, paper, journal, author group,
diagnosis, or fixed crop coordinate into the reusable workflow.

Article-specific material may be kept only in that paper's run folder,
`RUN_MANIFEST.md`, `crop_overrides.json`, or a clearly labeled legacy/regression
note. It must not become a default rule in `SKILL.md`, references, scripts, or
top-level examples.

For each new version, run an article-specific-content audit before release:

- search for prior article titles, author names, acronyms, diagnoses, journal
  citations, DOI fragments, fixed crop bboxes, and expected pixel sizes;
- replace reusable examples with placeholders or generic medical-journal
  examples;
- keep scripts and rules parameterized by the current input PDF, not by a
  previous paper.

## Output Structure

Aim for 40-50 slides (acceptable band 40-55):

1. Title slide.
2. Outline slide with numbered emoji markers and slide-range hints when known.
3. Section dividers, one per major paper section or teaching block.
4. Background/context slides.
5. Definitions or terminology slides.
6. Methods/study design slides.
7. Results/evidence slides.
8. Figure/Table slides, one per paper item.
9. Clinical implications or algorithm slides.
10. Key Takeaways.
11. Clinical Recommendations.
12. Key References.
13. Thank You slide.

Use `references/slide_structure.md` for planning heuristics.

## Visual Style

Use the bundled builder unless the user requests a different template:

```bash
python3 scripts/build_deck.py <spec.json> --out <output.pptx>
```

The default deck style is dark academic:

- Widescreen 16:9.
- Near-black navy page background.
- 1.00" mid-navy header band.
- Bright light-blue divider line under the header.
- Muted footer citation and zero-padded slide number.
- Dr. Leether logo in the upper-right on non-title/non-closing slides.
  Use the symbol-only transparent logo. Do not use a logo with a white
  rectangular box, opaque background, or lower `Dr. Leether` text.
- Figure and table images sit on bright white paper-like regions against the
  dark background.

See `references/visual_style.md` and `references/deck_spec_schema.md` for the
exact schema and geometry.

## Workflow

### 1. Read The Paper

Start every new requested deck or remake as a fresh content run. Create or
update `RUN_MANIFEST.md` before building the deck spec and record:

- source PDF path and timestamp;
- skill version;
- `content_generation: fresh_full_regeneration`;
- whether any prior deck/spec/PPTX/assets were referenced for QA only;
- `reused_content: none`, unless the user explicitly requested reuse.

Do not begin by copying a prior `deck_spec.json` and swapping image paths. A
prior spec may be opened to compare quality or catch regressions, but the new
outline, slide-visible text, image/table assets, and speaker notes must be
generated from the current source paper and current reviewed assets.

Extract/read enough PDF text to identify:

- title, authors, journal, year, DOI, volume/issue/page;
- abstract and headline conclusion;
- section headings, subheadings, and their order/hierarchy;
- study population and reference standard;
- all Figures and Tables with captions;
- key results, numbers, limitations, and clinical impact.

### 2. Extract Figures And Tables

Run the bundled extractor:

```bash
python3 scripts/extract_from_pdf.py <path-to-pdf> --out <work-dir>/extracted/
# tables are dense text: they render at 600 DPI by default (--table-dpi).
# Pages/figures use --dpi (200); raise table DPI further only when needed.
```

This produces:

- `text.md` — extracted text by page.
- `page_<N>.png` — full-page renders.
- `image_pXX_YY.*` — raw embedded images.
- `figures/Figure_<N>.png` — candidate figure crops from PDF image placements.
- `unique/Figure_<N>.png` — aHash-deduplicated candidate representatives.
- `tables/Table_<N>_page_<P>.png` — candidate table crops.
- `manifest.json` — extraction metadata, bbox, dedup, ignored images, crop QA,
  and border-cleanup QA.
- `contact_sheet.png` — review sheet of all candidate figure/table crops.
- `crop_review.md` — warning summary and manual review checklist.

### 3. Crop Review Gate

After extraction, inspect:

- `extracted/contact_sheet.png`
- `extracted/crop_review.md`
- `extracted/manifest.json`

Treat the deck as not ready if any of these are true:

- `crop_review.md` contains warning crops that have not been manually inspected.
- Figure/Table numbers in the paper do not match the final asset list.
- A multi-panel figure is split into separate candidate crops but should be one
  article-level Figure slide.
- A vector/flowchart figure is missing because it was not an embedded image.
- A table is missing the first column, final column, notes/abbreviations,
  caption, or continuation rows.
- A crop includes unrelated body text, page footer, watermark, running header,
  or another Figure/Table.
- A crop has `border_cleanup.manual_review_required: true`.
- Border removal changed the crop but before/after QA was not visually checked
  in the contact sheet.
- A figure/flowchart lost an internal box, arrow, axis, label, or panel letter.

Important distinction:

- Automatic extractor output is PDF object-level: one PDF image placement may
  become one crop.
- Final deck assets should be article Figure/Table-level: one complete paper
  Figure/Table item per slide.
- Build the expected Figure/Table list from caption-like text and visual
  review, not from inline references alone.

If automatic candidates are incomplete, crop from `page_<N>.png` using manual
coordinates or `crop_region()`. Save final assets with clear names, such as:

```text
figures/fig1.png
figures/fig2.png
figures/table1.png
```

Do not use `unique/` as final truth. It is a planning aid only; aHash can merge
similar but clinically distinct panels.

For multi-page, continued, or very tall tables, split into `Table 1A` /
`Table 1B` only at a natural row/section boundary. Do not split through a row.
Preserve the original table title band and column-header row on every split
image, and normalize all split images to the same pixel canvas width before
building the deck.

For every final table asset, preserve an outer safety margin:

- Use `TABLE_SAFETY_MARGIN_PX = 12` by default; 8-24 px is acceptable after visual QA.
- Preserve the white margin on all four sides after table border cleanup,
  same-width normalization, and split-table rebuilding.
- Do not run final `trim --margin 0` on tables. Zero-margin trim is allowed only as
  an intermediate step if a later padding/white-canvas step restores the table
  safety margin and the sidecar/provenance documents that restoration.
- If a postprocess sidecar for a final table says `margin: 0`, treat the asset as
  not final unless another sidecar or `RUN_MANIFEST.md` records the later padding
  step.
- Do not use figure tight-crop or panel micro-crop rules to justify table crops
  that touch table text or gridlines.

For multi-panel figures, use strict panel-label normalization:

- Treat any non-flowchart figure with visible A/B/C/D/E/F labels as a labeled
  multi-panel figure.
- Split non-flowchart multi-panel figures into individual panel crops before
  final deck assembly. This is mandatory; there is no documented-exception path
  for non-flowchart multi-panel figures.
- Remove original source-page white gutters between panels; rebuild the final
  layout with controlled uniform gaps.

  Use the bundled helper to do this reproducibly (trims each panel, removes
  source gutters, normalises panel height, rebuilds a regular grid with one
  uniform gap):

  ```bash
  # auto-split a single (high-DPI) composite grid image, then rebuild as an
  # aligned grid with no white edges:
  python3 scripts/postprocess_assets.py recompose-panels final_assets/Figure_2.png \
    --composite extracted/figures/Figure_02.png --rows 2 --cols 3 \
    --inset 2 --fit fill --gap 8 --bg "#061428"

  # or from individual panel crops
  python3 scripts/postprocess_assets.py recompose-panels final_assets/Figure_2.png \
    --inputs panel_a.png panel_b.png panel_c.png panel_d.png \
    --cols 2 --inset 2 --fit fill --gap 8 --bg "#061428"
  ```

  Key options:
  - The composite is split at gutter BOUNDARIES, so the white/grey separator
    line between panels is excluded from every cell (not cut down the middle).
  - Each panel is then automatically edge-trimmed: every one of its 4 sides is
    cropped repeatedly until no white strip remains. A border line is removed if
    it is near-white (`--edge-white-thr` 238 at `--edge-white-frac` 0.7) OR a
    uniform light-grey line (`--edge-light-thr` 222 at `--edge-light-frac` 0.92).
    The uniform-light test catches grey separator/background residue while the
    high fraction protects textured image content (CT bone, vessels).
  - `--inset 1|2` is an optional extra inward crop after the edge-trim (usually
    unnecessary now).
  - `--fit fill` (default) scales every panel to a uniform cell and centre-crops
    the small overflow, so columns/rows line up and all four outer edges are
    flush — the figure reads as one complete rectangle. Use `--fit pad` to avoid
    any cropping (letterbox on `--bg`) or `--fit stretch` for an exact-cell fit.
  - On a dark slide pass `--bg "#061428"` so the uniform gaps never look white.
  - `--panel-frame 2|3` draws a thin frame (colour = `--bg` by default) around
    each panel. This is the recommended way to handle a panel whose IMAGE CONTENT
    is bright at an edge (e.g. a vessel reaching the bottom, CT soft tissue at the
    side, or a light DSA film). Those bright edges are real content, not
    separator artifacts, so they must not be cropped away — the frame instead
    covers the outermost rim so the bright content does not touch the gap. Set
    `--panel-frame-color` for a non-bg frame.
  - Prefer a high-DPI page re-crop as the `--composite` source for sharpness.
- Remove the original A/B/C/D labels from the image crop, even when they are
  still visible in the source page render.
- Trim each panel independently. If thin white edge pixels remain after normal
  trim, apply conservative `microcrop --px 1` or `microcrop --px 2` only after
  visual safety check.
- Add `panel_labels` to the figure slide, such as
  `"panel_labels": ["A", "B", "C", "D"]`.
- The builder places `panel_labels` at the lower-right edge of each rendered
  panel slot. For unequal panel widths or nonuniform layouts, provide
  `panel_label_x_fracs`, `panel_boxes`, or equivalent per-panel geometry.
  Speaker notes should reference those same labels with `【A 圖】`, `【B 圖】`,
  etc.
- Do not deliver a labeled multi-panel figure with missing labels, mixed
  labeling styles, preserved source-page gutters, or `panel_labels` without
  validated panel geometry unless the exception is documented in
  `RUN_MANIFEST.md`.

Use the bundled helper for strict figure post-processing:

```bash
python3 scripts/postprocess_assets.py labels \
  input_figure.png \
  final_assets/Figure_1.png \
  --labels A,B,C,D
```

For figure assets, the bundled helper may use `--margin 0` for `trim` and
`labels` so excess outer white margins are removed. This default is for figures,
not tables. If the original panel letters are not detected cleanly, use
`--cut-bottom-px <pixels>` after visual review.

For non-flowchart panels that still show a thin white edge on dark slides after
normal trimming, apply the conservative micro-crop:

```bash
python3 scripts/postprocess_assets.py microcrop \
  final_assets/Figure_3_panel_A.png \
  final_assets/Figure_3_panel_A.microcrop.png \
  --px 2
```

Use `microcrop` only for non-flowchart figure panels. Do not use it for
flowcharts or tables.

For figures without panel labels, still remove excess white margin:

```bash
python3 scripts/postprocess_assets.py trim \
  input_figure.png \
  final_assets/Figure_2.png
```

For tables, use a positive safety margin in the final table asset:

```bash
python3 scripts/postprocess_assets.py trim \
  input_table.png \
  final_assets/Table_1.png \
  --margin 12
```

If table cleanup needs a zero-margin intermediate crop, rebuild onto a white
canvas or re-run table trim with `--margin 12` before the asset is referenced by
the deck spec.

**Tables as high-DPI raster (standard, most compatible).** By default tables are
rendered as PNG at 600 DPI (`--table-dpi`), the same image approach as figures.
At 600 DPI table text is crisp on any normal display and the PNG renders
everywhere (Windows/Mac PowerPoint, Google Slides). This is the recommended
default. Trim with a white safety margin as usual:

```bash
python3 scripts/postprocess_assets.py trim \
  extracted/tables/Table_01_page_4.png final_assets/Table_1.png \
  --asset-type table --margin 24
```

**Vector tables (optional, sharpest; Windows-PowerPoint best).** A raster
table is always a fixed-pixel image and softens when zoomed/projected. PDF table
text is vector, so for true original quality keep it vector all the way into the
deck as an EMF. This is resolution-independent (razor-sharp at any zoom) and
preserves the journal's exact layout:

```bash
python3 scripts/postprocess_assets.py vector-table \
  <source.pdf> final_assets/Table_1.emf \
  --page 4 --bbox 48.7,495.1,540.9,740.6 --pad-top 16 --pad-bottom 24
```

Use the table bbox (PDF points) from `extracted/manifest.json`. The command
prints the `image_aspect`; put both in the deck spec:

```json
{ "type": "figure", "title": "...", "image": "final_assets/Table_1.emf",
  "image_aspect": 1.836, "caption": "Table 1. ...", "notes": "..." }
```

`build_deck.py` detects the `.emf` extension and places it on a white card on
the dark slide (vector tables have no white background of their own). EMF assets
bypass the PNG postprocess/audit gates by design. For stacked tables on one page
(e.g. Table 2 above Table 3), use small `--pad-top`/`--pad-bottom` so a table
does not capture its neighbour. The raster path (`--table-dpi`, default 600)
remains available when a vector route is not wanted.

Before building the deck, audit final assets:

```bash
python3 scripts/postprocess_assets.py audit-final final_assets --spec deck_spec.json
```

This gate catches accidental bypasses of the post-processing stage and verifies
that split table parts such as `Table_1A` / `Table_1B` have equal pixel widths.
Treat audit failure as a hard stop, not a warning.

Recommended override shape:

```json
{
  "Figure 3": {
    "page": 5,
    "bbox_px": [120, 1065, 1265, 1995],
    "source": "manual_full_page_render",
    "note": "Merged A-D panels"
  }
}
```

### 4. Safe Outer Border Removal

Use safe outer-border removal as a post-processing step, not as primary crop
logic.

Default behavior:

1. Classify the final asset as `table`, `flowchart`, `figure`, or `unknown`
   using the expected item label, caption text, source method, and visual
   structure.
2. If the asset is a table and the outer border appears to be a decorative
   frame, remove only the outermost frame line, then add stable white margin.
3. If the asset is a flowchart, algorithm, or diagram, preserve all internal
   semantic boxes, connectors, arrows, and text. Keep the outer frame when
   removing it could touch or visually weaken the diagram structure.
4. If the asset is a figure, plot, MRI image panel, or unknown, do not remove
   border lines automatically. Prefer padding expansion.
5. If edge QA fails after padding or border cleanup, mark the crop as warning
   in `crop_review.md` and require manual inspection.

Record every automatic border decision in `manifest.json` as
`border_cleanup`, including `status`, `asset_type`, `action`, `reason`, and
`manual_review_required`.

### 4C. Background-Aware Edge Trimming (v0.2.38)

The `trim` and `labels` commands of `scripts/postprocess_assets.py` now apply a
background-aware edge refinement that is LAYERED ON TOP of the existing
white-based crop, not a replacement for it. This fixes two failure modes of a
pure-white-only assumption:

1. Light-grey journal pages (some journals use ~#F8F8F8, not #FFFFFF): the old
   white test treats the grey margin as content and never trims it.
2. A thin light scanner/film hairline at the outer edge of a figure that sits
   on a black canvas (brightness ~150-200): it differs from white even more
   than the canvas, so the white test keeps it (this is what left a residual
   white line on the top of one figure and the left of another).

How it works:

- The legacy `content_bbox()` white-based crop (plus margin and optional
  bottom-label removal) runs first and remains the baseline.
- A refinement step then detects the asset's ACTUAL background colour from its
  border ring and, only when that colour is not essentially pure white, peels
  any remaining background margin and thin CONTINUOUS hairline rim relative to
  that colour, re-adding the requested `margin` in the SAME detected colour so
  the table safety-margin contract still holds.
- A sparse text line (a table title or footnote that is mostly background with
  a few dark glyphs) is never stripped, because a rim must be a continuous
  strip (>= 60% of its pixels differ from the background) while a pure-margin
  line must be ~all background (>= 99%).
- Two detection passes handle assets with two backgrounds (a light page margin
  around a black image canvas): pass 1 removes the page margin, pass 2
  re-detects the canvas colour and clears the residual hairline.

Control flags (both default to safe behaviour):

```bash
# default 'auto': refine only when background is not pure white
python3 scripts/postprocess_assets.py trim IN OUT --asset-type figure
python3 scripts/postprocess_assets.py trim IN OUT --asset-type table --margin 12

# force the refinement on, or fall back to exact legacy white-only behaviour
python3 scripts/postprocess_assets.py trim IN OUT --bg-aware on
python3 scripts/postprocess_assets.py trim IN OUT --bg-aware off
```

Backward compatibility: `--bg-aware off` reproduces the pre-v0.2.38 output
exactly. In `auto`, pure-white tables/figures are returned unchanged (the
detector sees white and skips), so existing white-page decks do not regress.
The `.postprocess.json` sidecar records `bg_aware`, `bg_aware_applied`, and the
`detected_bg` colour; `audit-final` and the build gate are unaffected.

### 4B. Figure/Table Micro-Crop Rules

Apply these rules after the v0.2.8 crop-review gate and before deck assembly.

**Flowchart, algorithm, and diagram figures**

- Preserve all internal flowchart boxes, arrows, connectors, and text.
- Do not apply panel micro-crop.
- Crop from full-page render when PDF object extraction misses vector content.
- Trim only excess outside white padding after visual QA confirms that no
  internal box, connector, arrow, label, legend, or text is touched.
- Do not use fixed bounding boxes, expected pixel dimensions, or article-specific
  crop recipes unless the user explicitly asks to reproduce that exact prior
  article.

**Non-flowchart figure panels**

- Apply a 2 px inward micro-crop only after normal trimming.
- Use the helper:

```bash
python3 scripts/postprocess_assets.py microcrop INPUT OUTPUT --px 2
```

- Inspect the contact sheet after micro-crop. The crop is valid only if it
  reduces thin white edge pixels without removing meaningful content.

**Tables**

- Set `table_micro_crop_px = 0`.
- Never apply `microcrop` to tables.
- Set `TABLE_SAFETY_MARGIN_PX = 12` for final table assets unless visual QA
  documents a different value within 8-24 px.
- Preserve complete table content and gridlines. Add horizontal and vertical
  safety margin, not just horizontal margin.
- A final table asset made with `trim --margin 0` is invalid unless a later
  documented padding/white-canvas step restores the safety margin before deck
  assembly.
- Use verified extractor crops or rebuild from full-page render when trimming
  would make table text, gridlines, notes, or first/last columns touch the crop
  edge.

### 4A. Split Long Tables Without Losing Headers

When a table is too tall to read on one slide:

1. Inspect the full table crop visually.
2. Identify the repeated header region: table title band plus column headers.
3. Choose a split coordinate at a true row or category boundary. Prefer section
   transitions such as one disease group ending and the next beginning.
4. Rebuild both table halves from the complete source crop:
   - Part A starts at the original top of the table.
   - Part B starts with a duplicate of the original title/header region, then
     continues from the chosen split coordinate.
5. Put both outputs onto the same-width white canvas so the rendered slides do
   not jump in width.
6. Equal PIXEL width is necessary but NOT sufficient for equal ON-SCREEN width.
   When split parts have the same pixel width but different heights, both are
   usually height-limited in the figure box (default 12.10 x 4.85 in, aspect
   ~2.50, while tables are taller), so `add_image_fit` scales the taller part
   down more and it renders NARROWER. To force equal on-screen width, give every
   split part the SAME `image_width_in` in the deck spec, set to the on-screen
   fit width of the TALLEST part:
       image_width_in = box_h_in * (common_pixel_width / tallest_part_pixel_height)
   (using the default box_h_in = 4.85). This width also keeps the tallest part
   within the box height, so every part fits; because all parts share the same
   pixel width and the same `image_width_in`, their text also renders at one
   size. Example: Table_1A 4292x2782, Table_1B 4292x2304 -> 4.85*4292/2782 =
   7.48 in; set both slides to `"image_width_in": 7.45` (just under the max).
7. Render the affected slides and compare them side by side before delivery;
   confirm the split parts are the same visible width.

Use the bundled helper when coordinates have been confirmed:

```bash
python3 scripts/postprocess_assets.py split-table \
  extracted/tables/Table_01_page_2.png \
  final_assets/Table_1A.png \
  final_assets/Table_1B.png \
  --repeat-header-y <title-plus-column-header-bottom-y> \
  --split-y <natural-row-boundary-y>
```

For this pattern, do not decide by color. A title band may be blue, gray,
white, black, or another style. If visual/semantic review confirms that a
region is the table title band, every split table image should keep that band,
matching the visual completeness of unsplit tables such as `Table 2`.

### 5. Plan The Deck

Sketch the outline before writing the JSON spec. First build a paper-native
heading map from the PDF text for the specific article being converted.
Preserve that article's major headings and subheadings as the backbone of the
deck.

Avoid invented teaching titles when a paper-native heading or subheading
clearly identifies the source section. Put the teaching frame inside the slide
body instead.

### 5A. Generate Consistent Slide Titles From Paper Headings

Use heading-consistent title generation:

1. Assign every content, figure, and table slide to the nearest source heading
   or subheading in the article.
2. If the slide covers an entire major section, use the exact major heading as
   the slide title.
3. If the slide covers a named subsection, use the exact subheading as the main
   title. When helpful for context, use `Major Heading: Subheading`.
4. If multiple slides come from the same heading/subheading, keep the heading
   language stable and vary only a short qualifier after a colon, such as
   `<Subheading>: <short slide-specific qualifier>`.
5. For figure/table slides, title the slide by the nearby heading/subheading,
   not by a newly invented image summary. Put `Figure 2` or `Table 1` detail in
   the caption and notes.
6. Do not rewrite every slide title into a standalone teaching headline unless
   that wording is the paper's actual heading/subheading or the only clear
   source label.
7. Keep section divider titles, outline items, content slide titles, and
   Figure/Table slide titles aligned to the same heading map so the deck reads
   like a coherent walkthrough of the article.

Before writing the final spec, audit the title sequence by itself. It should
show the article's paragraph flow and hierarchy without needing to read the
slide bodies.

### 5B. Place Tables And Figures Near Source Mentions

Use the v0.2.3 placement style for visual assets:

- Put each Figure/Table slide near the article section or paragraph that
  introduces, cites, or interprets that item.
- Use caption text, inline references such as `Table 1` / `Fig. 3`, and nearby
  section headings as anchors.
- Do not automatically move overview, classification, differential-diagnosis,
  or red-flag tables to the beginning solely because they are useful teaching
  maps.
- Do not group all visual assets at the end unless the paper itself discusses
  them as an end-of-article summary/checklist.
- If a table or figure is cited repeatedly, place it near the first substantive
  discussion, not near a passing parenthetical mention.
- Disease-specific figures should still stay close to the relevant disease or
  concept section, but the deciding anchor is the paper's local discussion
  rather than a separate teaching-function reorder.

In short: preserve the article's narrative order. Visual slides should feel
like they appear where the paper is actually using them.

### 6. Write The Deck Spec

Create a JSON file using `references/deck_spec_schema.md`.

Minimum shape:

```json
{
  "meta": {
    "footer_label": "<FirstAuthor> et al - <Journal Year>  |  <Short Article Topic>"
  },
  "slides": [
    {
      "type": "title",
      "title": "<Article Title>",
      "authors": "<Authors from PDF>",
      "citation": "<Journal Year; volume:pages or DOI>",
      "notes": "各位好，今天介紹這篇醫學文獻..."
    },
    {
      "type": "figure",
      "title": "<Nearest Paper Heading>",
      "image": "figures/table_or_figure.png",
      "caption": "<Exact Figure/Table caption from the article>",
      "notes": "【圖片說明 — <Figure/Table label>：<brief teaching focus>】..."
    }
  ]
}
```

### 6A. Slide-Visible Body Style

Use the v0.2.5-v0.2.9 teaching-body style while keeping the current v0.2.11
asset, notes, table, panel, and logo gates. This is a style transplant, not a
version rollback.

For normal content slides, the visible body should usually be 2-4 compact
blocks, each with a short label and one or two support lines. Preferred labels
are paper- and topic-specific, for example:

```text
• Study design:
  Prospective multicenter cohort with predefined imaging endpoints

• Key finding:
  High-risk plaque features were independently associated with outcome

• Clinical implication:
  Imaging can refine risk stratification beyond luminal stenosis alone

✅ Take-home: Vessel-wall features shift the question from narrowing to risk.
```

Allowed visible-body markers:

- `• Label:` for short section labels. A plain `Label:` is acceptable when
  spacing is cleaner, but the deck should not become all unlabeled prose.
- `→` for causal logic, interpretation, implication, or workflow consequence.
- `✅` for a final take-home, conclusion, or clinical impact line. Use at most
  one visible emoji on most content slides.
- Avoid more than 3 consecutive visible lines starting with the same marker.
- Use blank-line breaks to separate section-label blocks on most content slides.
- Evidence, definition, recommendation, and takeaway slides should usually end
  with one final landing line using `✅`, `⚠️`, or `→`.

Do not make every content slide a uniform flat bullet list. Avoid this pattern
unless the slide is explicitly a checklist, list of criteria, or outline:

```text
• Point one
• Point two
• Point three
• Point four
```

Before finalizing `deck_spec.json`, run a slide-body QA pass over all normal
content slides:

1. Identify slides whose body text is only same-level bullets.
2. Rewrite them into labeled teaching blocks when the content has natural
   subtopics, evidence/result/meaning structure, or clinical implications.
3. Add one implication or take-home line to major result, discussion, and
   conclusion slides when clinically appropriate.
4. Keep visible text concise; move detailed explanation to speaker notes.
5. Confirm all visible body text remains English.

Fail the build/review if most content slides lack section labels or if the deck
loses the v0.2.5-v0.2.9 teaching-body hierarchy after regeneration.

### 6B. Logo Path And Header Branding

Use the bundled Dr. Leether logo unless the user explicitly requests a
different brand asset.

- Default logo path is resolved from the skill directory:
  `assets/dr_leether_logo.png`.
- Do not hard-code paths by walking up a run directory with fragile
  `../../../..` expressions. Resolve from the known workspace/skill root or omit
  `meta.logo_path` so the builder uses its default.
- If `meta.logo_path` is supplied but does not exist, the builder should warn
  and fall back to the bundled default logo instead of silently disabling the
  logo.
- Non-title and non-thank-you slides should show the symbol-only logo at the
  upper-right. Title and thank-you slides intentionally remain logo-free unless
  the user asks otherwise.
- The logo asset itself must be visually clean: transparent outside background,
  symbol-only, no white rectangular box, and no lower `Dr. Leether` wordmark.
- QA must inspect at least one outline/content slide, one part divider, and one
  figure/table slide for logo visibility.

### 7. Build And Review

Build:

```bash
python3 scripts/build_deck.py <spec.json> --out <output.pptx>
```

`build_deck.py` also enforces the post-processing gate by default. Use
`--allow-unprocessed-assets` only for legacy debugging, never for final
delivery.

Required checks before delivery:

- [ ] `extracted/contact_sheet.png` reviewed.
- [ ] `extracted/crop_review.md` has no unresolved crop warnings.
- [ ] `scripts/postprocess_assets.py audit-final final_assets --spec <spec>`
      passes.
- [ ] Final assets match every paper Figure/Table number.
- [ ] Multi-panel figures are merged when the paper presents them as one figure.
- [ ] Manual crop coordinates or notes are preserved in `crop_overrides.json`
      when automatic output was corrected.
- [ ] Multi-panel figure assets have original panel letters removed and
      restored through `panel_labels`.
- [ ] Figure assets have excess white margins removed while preserving all
      image content, annotations, arrows, axes, legends, and scale bars.
- [ ] Every labeled non-flowchart multi-panel figure is split into panel crops
      (no exception); source-page gutters are removed and inter-panel gaps are
      filled with `bg_page` (no white strips); labels appear outside each panel
      at lower-right with validated geometry.
- [ ] Table assets retain 8-24 px outer white safety margin on all four sides,
      with 12 px as the default.
- [ ] Split table parts (e.g. `Table_1A` / `Table_1B`) render at the SAME
      on-screen width, not just equal pixel width: give each the same
      `image_width_in` = box_h_in * common_pixel_width / tallest_part_pixel_height.
- [ ] No final table asset has only `trim/labels margin: 0` provenance unless a
      later documented padding/white-canvas step restores the safety margin.
- [ ] The logo path exists, the PPTX embeds the logo asset, and representative
      non-title/non-thank-you slides show the upper-right logo.
- [ ] The logo render is symbol-only with transparent outside background, no
      white rectangular box, and no lower wordmark.
- [ ] Border cleanup status was reviewed for every crop where
      `border_cleanup.status != skipped`.
- [ ] Every Figure/Table has a slide or documented reason for omission.
- [ ] Total slide count is in the 40-55 band unless the paper is unusually
      short or long.
- [ ] Slide titles have been audited as a standalone sequence and follow the
      paper's heading/subheading map unless an exception is documented.
- [ ] Every slide has speaker notes.
- [ ] Title-slide speaker notes include publication context when available:
      country/region, institution, journal, submitted/accepted/online dates, and
      version-of-record or publication date.
- [ ] Speaker notes are Traditional Chinese, scan-friendly, include lead
      emojis/bullets, and do not degrade into all-prose paragraphs.
- [ ] Speaker-note emoji count is not zero across the completed deck.
- [ ] Final PPTX speaker notes do not show literal `**` markup.
- [ ] Outline slide uses numbered emoji section markers and slide-range hints
      when the final slide sequence is known.
- [ ] Slide-visible text contains no Chinese unless the user explicitly asked.
- [ ] Normal content slides use structured visible-body blocks with short
      section labels where appropriate, rather than mostly flat same-level
      bullet lists.
- [ ] Content slides avoid more than 3 consecutive same-marker lines and use
      blank-line section breaks where the body has multiple visual blocks.
- [ ] Major result, discussion, and conclusion slides include an implication,
      consequence, or take-home line when clinically appropriate, using `→` or
      restrained `✅` style if helpful.
- [ ] Part dividers include Traditional Chinese transition notes.
- [ ] Final PPTX opens or converts with LibreOffice/PowerPoint tooling.

Recommended QA commands:

```bash
python3 - <<'PY'
from pptx import Presentation
prs = Presentation("output.pptx")
print("slides", len(prs.slides))
print("notes", sum(1 for s in prs.slides if s.notes_slide.notes_text_frame.text.strip()))
PY

soffice --headless --convert-to pdf --outdir <out-dir> output.pptx
pdftoppm -jpeg -r 120 output.pdf <out-dir>/slide
```

Inspect a slide contact sheet or key rendered slides before sending the file.

## Speaker Notes

Use `references/notes_style.md` heavily. Core rules:

- Traditional Chinese, scan-friendly, not long prose.
- Use lead emojis for structure on every normal note type.
- Use bullets and sub-emojis so notes are easy to scan during speaking.
- Bold English medical terms on first use with Chinese gloss.
- The final PPTX notes must not display literal `**` markdown markers.
- Title-slide notes should include publication context when available: study
  country/region, main institution, journal, submitted date, accepted date,
  first-online date, and version-of-record/publication date.
- A deck with complete notes but zero note emojis fails QA.
- Figure/Table slides open with `【圖片說明 — <label>】`.
- For case-style figure legends, keep slide-visible captions short and move
  clinically relevant case details into the speaker notes.
- End content slides with a clear clinical or teaching takeaway.
- Use full teaching-script depth, not short templated notes. Each content note
  should usually include clinical framing, why the point matters, imaging
  findings or decision logic, and a radiology teaching takeaway.
- Figure/Table notes should be asset-specific. For split tables or multi-panel
  figures, do not reuse one generic note across parts unless the parts truly
  show the same information. Explain the exact table half, panel group, labels,
  or diagnostic feature visible on that slide.
- Prior deck notes may be opened as QA examples only. Do not copy their wording
  into a new deck unless the user explicitly requests reuse.

## Common Pitfalls

- Do not put broken PDF object-level crops into final Figure slides.
- Do not emit one slide per panel for a multi-panel figure. Figure 3 with
  panels A-F is ONE slide with ONE recomposed image, not six `Figure 3A` ...
  `Figure 3F` slides. If the deck spec references `panel_a.png` / `*_panel_*`
  files directly, the recompose step was skipped: merge them into one image
  first.
- Do not let `unique/` hide missing panels.
- Do not skip flowcharts or vector figures just because `page.get_images()`
  missed them.
- Do not crop away table notes, abbreviations, p-value columns, legends, risk
  tables, or axis labels.
- Do not leave panel letters missing or embedded inconsistently. In v0.2.11,
  remove original panel letters from figure crops and re-add them with
  `panel_labels`.
- Do not leave excessive white margins around figure panels. Tighten figure
  crops to image content unless doing so would remove semantic content.
- Do not apply 2 px micro-crop to tables or flowcharts.
- Do not deliver table crops with `margin: 0` final sidecars or table text/grid
  touching the crop edge; restore an 8-24 px white safety margin first.
- Do not ship a deck with an invalid `meta.logo_path` that disables the
  upper-right logo. Fall back to the bundled logo and verify it is embedded.
- Do not ship a logo render with an opaque white box, nontransparent background,
  or lower wordmark.
- Do not run tab
