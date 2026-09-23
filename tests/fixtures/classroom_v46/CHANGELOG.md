# Changelog

## v0.2.38-bg-aware-trim
- Add background-aware edge trimming to the `trim` and `labels` commands of
  `scripts/postprocess_assets.py`. This is ADDITIVE — layered on top of the
  existing white-based `content_bbox()` crop, not a replacement.
- Detects each asset's real background colour from its border ring and, when it
  is not essentially pure white, trims the margin/hairline relative to that
  colour. Fixes (1) light-grey journal pages whose margin the white-only test
  never trimmed, and (2) thin light scanner/film hairlines left on the edge of
  figures that sit on a black canvas.
- Two-pass detection handles assets with two backgrounds (light page margin
  around a black image canvas). A continuous-strip vs sparse-text guard keeps
  table titles/footnotes near an edge from being stripped. Tables keep their
  8-24px safety margin, re-padded in the detected background colour.
- New CLI flags on `trim`/`labels`: `--bg-aware {auto,on,off}` (default `auto`)
  and `--bg-tol N` (default 26). `--bg-aware off` reproduces pre-v0.2.38 output
  exactly; in `auto`, pure-white assets are returned unchanged (no regression).
- New functions: `detect_bg_color`, `_peel_edges`, `background_aware_bbox`,
  `bg_aware_refine`. `.postprocess.json` now records `bg_aware`,
  `bg_aware_applied`, and `detected_bg`. `audit-final` / build gate unaffected.

## v0.2.37-native-panel-labels
- Add an optional NATIVE post-build panel-label method so A/B/C/D have identical
  actual on-screen size on every figure slide regardless of each figure's scale,
  with precise control of the gap above (to its own panel) and below (to the
  next row), and labels remain selectable/editable text.
- New scripts:
  - `scripts/recompose_panels_banded.py` — recompose panel crops with a reserved
    `bg_page` band below each row (no burned labels) and emit per-panel label
    geometry to a shared `panel_geometry.json`; writes a `.postprocess.json`
    sidecar so the build/audit gate passes.
  - `scripts/add_panel_labels.py` — stamp A/B/C/D onto a built `.pptx` as native
    fixed-point-size text from the geometry (matches figure slides via the
    deck-spec `image` basename; ignores the corner logo).
  - `scripts/measure_label_gaps.py` — QA/calibration helper that measures the
    on-screen gap_above / glyph height / gap_below from a rendered slide.
- New SKILL.md section "Native Post-Build Panel Labels" documents the 3-step
  flow, gap control, and calibration constants (18pt → glyph 0.155 in;
  glyph_ratio 0.62; center_offset 0.0525).
- Prior burned-in label methods (`recompose_panels_aligned.py`,
  builder `panel_labels`) are unchanged and still supported.

## v0.2.36-one-figure-one-slide
- Add hard "one-figure-one-slide" invariant to Hard Rules: each paper Figure =
  exactly one figure slide = one recomposed image; per-panel crops are
  intermediate only and must be recomposed before entering the deck spec.
- Add Common Pitfalls anti-pattern against emitting one slide per panel.
- audit-final now FAILS when (a) a figure slide references a raw `*_panel_*`
  crop, or (b) the same paper Figure number appears on >1 figure slide.
  Escape hatch: per-slide `figure_slide_exception: true` (document in RUN_MANIFEST).
- deck_spec_schema validation checklist updated to match.


## v0.2.35-outline-cards
- Redesigned the outline slide (`build_outline`): each item is a card with a
  numbered accent badge, the topic title (leading emoji/number stripped), and a
  right-aligned `Slides X-Y` pill on a rounded row band. Items are parsed from
  `"<emoji> Topic - Slides A-B"`.
- Cards are evenly distributed and vertically centered for any row count and
  kept clear of the footer line.
- Title/badge/pill font sizes auto-scale with row height so a long outline
  (many rows) stays readable and uncramped.

## v0.2.34-split-table-screen-width
- Split-table guidance now requires equal ON-SCREEN width, not just equal pixel
  width. When split parts share a pixel width but differ in height they are both
  height-limited in the figure box and render at different visible widths. Fix:
  set the same `image_width_in` on every split part, computed as
  box_h_in * common_pixel_width / tallest_part_pixel_height (default box_h_in
  4.85). SKILL.md section 4A + QA checklist updated.

## v0.2.33-nonbold-labels
- `recompose_panels_aligned.py` now renders A/B/C/D panel labels in regular
  (non-bold) weight by default (DejaVu Sans regular). Added `--label-bold` to
  opt back into bold. SKILL.md notes the new default weight.

## v0.2.32-panel-rim-frame
- `recompose_panels_aligned.py` now applies a bg-colored rim frame to every
  panel by default (`--panel-frame 3`, color = `--bg`). This covers thin
  light-grey / film border lines that the near-white edge-trim (>=238) leaves,
  so no faint light edge appears against the dark slide. `--panel-frame 0`
  disables it; `--panel-frame-color` overrides the color.
- SKILL.md + QA updated: added a check that no light rim remains on panel edges.

## v0.2.31-force-panel-split
- Removed the documented-exception path for non-flowchart multi-panel figures.
  Such figures MUST always be split into individual panel crops and recomposed
  (independent edge-trim, row-height alignment, equal row width, inter-panel
  gaps filled with `bg_page`, A/B/C/D re-added outside each panel). Delivering
  the original journal composite with source-page white between panels is no
  longer permitted.
- Updated the QA checklist accordingly: every labeled non-flowchart multi-panel
  figure must be split (no exception) with gaps filled by `bg_page` and no white
  strips between panels.
- Flowcharts/vector diagrams and tables are unchanged (still never split).

# v0.2.30-table-margin-screen-match

- Table outer white margin is now matched to the vector-figure white pad AS IT
  RENDERS ON SCREEN (target ~0.176 in), solving per-table source px for the
  limiting dimension (margin_px = target*content/(box-2*target)). Replaces the
  fixed-88 px physical match so wide tables and the taller flowchart show the
  same on-screen white band.

# v0.2.29-table-margin-match-figure

- Tables now get a more generous outer white margin that matches the white pad
  added to a cropped vector figure (~0.147 in of the page = 44 px at 300 DPI ->
  88 px at the 600 DPI table render). Applied via trim --asset-type table
  --margin 88. The 8-24 px rule still sets the minimum safety gap.

# v0.2.28-label-screen-consistent

- recompose_panels_aligned.py: added --label-screen-height-in (+ --slide-box-w-in
  / --slide-box-h-in). Derives each figure's source label px so the A/B/C/D
  labels render at the SAME on-screen size on every slide, compensating for each
  figure's fit scale (fixes a short 1-row figure showing oversized labels).

# v0.2.27-frame-content-bbox

- Fix: --strip-outer-frame no longer clips inner boxes that sit very close to
  the frame edge (e.g. a bottom compartment box ~2 pt inside the frame). The cut
  now targets the content bbox (all inner boxes + text, excluding the frame
  rect) instead of a fixed inward inset, so the frame is removed while every
  inner box stays whole.

# v0.2.26-frame-clean-nohairline

- crop_vector_figure.py --strip-outer-frame now cuts using the frame's known
  vector coordinates (re-render interior inset by --frame-inset, default 3 pt),
  removing the outer frame cleanly with no residual line, then trims to content
  and pads even white margins.
- Rule: charts/diagrams and tables get no added thin border/hairline; only the
  clean asset on even white margins.

# v0.2.25-vector-frame-strip

- crop_vector_figure.py: added --strip-outer-frame (+ --white-margin). Removes a
  decorative outer rectangle frame around a flowchart/tree, trims to content,
  and pads an even white margin on all four sides. Opt-in; default preserves
  frames.

# v0.2.24-vector-figure-detect

- Added automatic raster-vs-vector figure classification. Vector figures
  (flowcharts/trees/algorithms) now use a separate cropping path: detect the
  diagram via 2D clustering of vector boxes/connectors (low raster coverage),
  then crop that bbox with a safe margin, preserving all boxes/arrows/text. No
  panel split, row alignment, or A/B/C/D labels are applied to vector figures.
- Added scripts/crop_vector_figure.py (supports --detect-only and crop).

# v0.2.23-panel-equal-row-width

- Multi-row multi-panel figures: each row is scaled to a common total width so
  the left/right edges of all rows align (a narrower row, e.g. C/D, is enlarged
  to match a wider A/B row). Default on in recompose_panels_aligned.py.

# v0.2.22-panel-rowalign-outside-labels

- Multi-panel non-flowchart figures: same-row panels are scaled to a common
  height so their top and bottom edges align (row-height alignment); gaps use
  the slide background color.
- A/B/C/D panel labels are rendered OUTSIDE each panel (in the gap below it,
  right-aligned to the panel's right edge), in the caption color (#8FA8C8), at a
  FIXED 54 px size for every figure.
- Added scripts/recompose_panels_aligned.py implementing the above.
- Flowcharts and tables are unaffected.

# Changelog

## v0.2.21-table-raster-600 - 2026-06-13

- Tables are handled as high-DPI raster images by default again (same image
  approach as figures): `extract_from_pdf.py --table-dpi` default raised
  400 -> 600. At 600 DPI table text is crisp on any normal display and the PNG
  renders everywhere (Windows/Mac PowerPoint, Google Slides).
- `SKILL.md`: high-DPI raster is now framed as the standard, most-compatible
  table method; the EMF `vector-table` route remains documented as an optional
  sharper alternative (Windows-PowerPoint best).

## v0.2.20-vector-tables - 2026-06-13

- Fix vector-table title clipping: `vector-table` now injects a full-canvas
  white background `<rect>` into the SVG before EMF conversion, so LibreOffice
  no longer auto-trims the top whitespace (which was shaving the table title).
  The EMF also gains a proper white background.
- `build_deck.py` reads the EMF's true aspect from its header (rclBounds) when
  placing a vector table, so it is never distorted; spec `image_aspect` is now
  only a fallback.

## v0.2.19-vector-tables - 2026-06-13

- New `postprocess_assets.py vector-table`: renders a PDF table region as a
  VECTOR **EMF** (PDF clip -> SVG via PyMuPDF -> EMF via LibreOffice). Tables
  stay vector all the way into PowerPoint, so they are resolution-independent
  (razor-sharp at any zoom) and keep the journal's exact layout — true original
  quality, no rasterisation. Prints `image_aspect` for the spec.
- `build_deck.py`: figure slides now accept `.emf`/`.wmf` images. A vector
  table is fitted by `image_aspect` and placed on a white card on the dark
  slide. EMF assets bypass the PNG postprocess/audit gates by design.
- `SKILL.md`: documented vector tables as the recommended high-quality route;
  raster `--table-dpi` (400) remains the default fallback.

## v0.2.18-table-hidpi - 2026-06-13

- `extract_from_pdf.py`: tables now render at **400 DPI by default** (new
  `--table-dpi`), up from the previous fixed 220. Tables are vector text
  rasterised to PNG; at 220 DPI the text looked soft once scaled onto a slide
  (~124 DPI effective). 400 DPI roughly doubles table pixel width (e.g.
  1525->2730 px) for ~227 DPI on a full-width slide. Page renders and figure
  clips are unchanged (`--dpi` 200 / figure re-crops). Raise `--table-dpi` to
  600 for very small-print tables.

## v0.2.17-panel-frame - 2026-06-13

- `recompose-panels`: added `--panel-frame` (and `--panel-frame-color`). Draws a
  thin frame (default colour = `--bg`) around each panel, covering the outermost
  rim. This is the non-destructive way to deal with a panel whose own image
  content is bright at an edge (vessel/soft-tissue/DSA film): those bright edges
  are real content and must not be cropped, so the frame hides the rim instead
  of cutting anatomy. Sidecar records `panel_frame`, `panel_frame_color`.
- `SKILL.md`: documented `--panel-frame` as the recommended treatment for
  bright content edges on multi-panel figures.

## v0.2.16-panel-edge-clean - 2026-06-13

- `recompose-panels`: two changes so panels show no residual white/grey edge.
  - Composite split now cuts at gutter BOUNDARIES (excludes the whole separator
    band) instead of the gutter centre, so no part of the separator line is left
    inside any panel.
  - Edge-trim is now two-threshold: it removes a border line that is near-white
    (>=238 at frac 0.7) OR a uniform light-grey line (>=222 at frac 0.92). The
    light-grey pass clears grey separator residue that the pure-white test
    missed, while the high fraction protects textured content (CT bone, vessels,
    DSA). New args: `--edge-light-thr`, `--edge-light-frac`.
- `SKILL.md`: documented gutter-boundary split + two-threshold edge-trim.

## v0.2.15-panel-edge-trim - 2026-06-13

- `recompose-panels`: each panel is now cleaned with an ITERATIVE per-edge
  white trim before layout. Every one of the 4 sides is cropped repeatedly
  while that border line is mostly near-white, until no white strip remains on
  any side. This removes residual white edges that a bounding-box trim keeps
  (e.g. a thin white line below a panel whose content reaches the edge).
  Tunable via `--edge-white-frac` (default 0.7) and `--edge-white-thr` (238).
  `--inset` is now an optional extra step after edge-trim. Sidecar unchanged.
- `SKILL.md`: documented the automatic edge-trim in the multi-panel workflow.

## v0.2.14-panel-grid-align - 2026-06-13

- `recompose-panels`: two additions for cleaner multi-panel figures.
  - `--inset N` crops each split panel inward by N px after trimming, removing
    the thin residual white edge so panels show no white border (1-2 px typical).
  - `--fit pad|fill|stretch` lays panels into a UNIFORM grid cell so columns and
    rows align and all four outer edges are flush — the figure reads as one
    complete rectangle. `fill` (default) scales-to-cover + centre-crops the small
    overflow; `pad` letterboxes on `--bg` (no crop); `stretch` resizes to the
    exact cell. Cell size defaults to the median trimmed panel size; override
    with `--panel-width` / `--panel-height`.
  - Sidecar now records `inset`, `fit`, `cell_w`, `cell_h`.
- `SKILL.md`: multi-panel workflow documents `--inset`, `--fit`, dark-slide
  `--bg`, and using a high-DPI page crop as the recompose source.

## v0.2.13-panel-recompose - 2026-06-13

- `postprocess_assets.py`: new `recompose-panels` command. Removes irregular
  source-page white gutters between panels in a multi-panel figure and
  rebuilds a regular grid with a single uniform gap. Accepts either individual
  panel crops (`--inputs`) or a single composite grid image to auto-split
  (`--composite --rows R --cols C`, gutter-detected with even-split fallback).
  Each panel is trimmed independently and normalised to a common height (no
  upscaling); the sidecar records `panel_boxes` and per-panel right-edge x
  fractions to help set label geometry. Gives the SKILL rule "remove
  source-page white gutters; rebuild with controlled uniform gaps" real tooling.
- `recompose-panels`: panels are packed per row with EXACT uniform gaps (no
  uniform-cell centering), so narrower panels no longer get stray white
  padding. Added `--bg` guidance: for figures on a dark slide pass
  `--bg '#061428'` so gaps blend into the slide instead of showing as white
  lines.
- `SKILL.md`: documented the helper in the multi-panel figure workflow.

## v0.2.12-hard-gate-enforced - hard-gate script enforcement - 2026-06-12

Implements the script patches listed in
`references/v0211_hard_gate_script_expectations.md`; those rules are now
enforced in code rather than documented only.

- `build_deck.py`: invalid `meta.logo_path` now WARNS and falls back to the
  bundled default logo (previously silently set `logo_path = None`). Logs the
  logo path actually used.
- `build_deck.py`: figure slides with >1 `panel_labels` but no panel geometry
  (`panel_label_x_fracs` or `panel_boxes`) now raise a build error instead of
  silently distributing labels across a composite image. Override with
  `panel_geometry_exception: true`.
- `postprocess_assets.py`: `trim`/`labels` gain `--asset-type` and
  `--intermediate`. `--asset-type table` defaults to a 12 px safety margin and
  refuses margin < 8 px for final assets unless `--intermediate`. Sidecars now
  record `asset_type` and `table_safety_margin_px`.
- `postprocess_assets.py audit-final`: now fails on final table sidecars with
  `trim`/`labels` margin < 8 px (unless documented via `--allow-table-margin`
  or a RUN_MANIFEST mention) and on multi-panel figure slides missing geometry.
  Added `--no-require-postprocess`.
- `postprocess_assets.py notes-audit`: new command. Fails if notes exist but
  contain zero emoji, or if figure notes reference panel letters absent from
  `panel_labels`; warns on literal `**` markup.

## v0.2.11-generalized-medical-journal - 2026-06-12

- Created from `v0.2.10-panel-microcrop-flowchart-safe`.
- Removed reusable-skill dependence on prior journal-specific content:
  article titles, authors, citations, footer labels, fixed crop boxes, expected
  figure sizes, and topic-specific examples must be regenerated from each input
  PDF.
- Generalized flowchart/algorithm/diagram handling: preserve all internal
  boxes, connectors, arrows, text, and structure; crop from full-page renders
  when vector content is missing from PDF object extraction; never use fixed
  coordinates unless explicitly reproducing a prior article.
- Replaced disease-specific reference examples with neutral placeholders and
  generic medical-journal examples.
- Keeps v0.2.10 behavior for non-flowchart 2 px micro-crop after QA, table
  micro-crop = 0, strict panel label normalization, safe border behavior,
  heading-based titles, source-mention visual placement, split-table protocol,
  and wide-image fitting.

## v0.2.10-panel-microcrop-flowchart-safe - 2026-06-12

- Created from `v0.2.8-strict-panel-labels-tight-figures`.
- Preserves the full v0.2.8 workflow, scripts, references, assets, strict
  panel-label normalization, tight figure crops, safe border behavior,
  heading/subheading title policy, and split-table protocol.
- Adds generalized former v0.2.9 R2 crop behavior:
  - Flowcharts/algorithms/diagrams preserve complete structure and all internal
    boxes/connectors; do not apply panel micro-crop.
  - Non-flowchart figure panels may apply `PANEL_MICRO_CROP = 2` after normal
    trimming to reduce thin white edges on dark slides.
  - Tables use `table_micro_crop_px = 0`; never apply figure panel micro-crop.
- Adds `scripts/postprocess_assets.py microcrop INPUT OUTPUT --px 2` for
  reproducible non-flowchart panel micro-crops.
- Fixed `scripts/build_deck.py` image fitting for very wide table images:
  `add_image_fit()` now preserves width-based fitting instead of overwriting
  `draw_w` with height-based sizing.

## v0.2.8-strict-panel-labels-tight-figures - 2026-06-11

- Created from `v0.2.7-heading-consistent-titles`.
- Preserves v0.2.7 heading/subheading title behavior, v0.2.6 safe border and
  split-table behavior, v0.2.3-style source-mention Figure/Table placement, and
  restored v0.2.5 `panel_labels` rendering.
- Adds strict multi-panel figure label normalization: remove original A/B/C/D
  letters from figure crops and re-add them consistently through
  `panel_labels`.
- Adds strict figure white-margin removal: final figure assets should be tight
  to the image content while preserving anatomy, annotations, arrows, axes,
  legends, scale bars, and other semantic content.
- Adds QA checks for missing or mixed panel-label styles and excessive white
  margins around figure crops.

## v0.2.7-heading-consistent-titles - panel-label restoration update 2026-06-11

- Restored the v0.2.5 `panel_labels` rendering feature inherited missing from
  v0.2.6.
- `build_deck.py` again reads `panel_labels` on figure slides and places A/B/C/D
  labels centered under tightly cropped multi-panel images.
- `references/deck_spec_schema.md` again documents `panel_labels`.
- `SKILL.md` now explicitly requires labeled multi-panel figures to either
  preserve original panel letters or re-add them through `panel_labels`.
- Kept v0.2.7 heading/subheading title behavior unchanged.

## v0.2.7-heading-consistent-titles - 2026-06-11

- Created from canonical `v0.2.6-safe-border-removal`.
- Added Eric's preferred heading-based slide title policy: titles should come
  from the paper's native major headings and subheadings, preserving hierarchy
  and paragraph flow across the deck.
- Kept the rule generic: do not store article-specific heading examples in the
  reusable skill; extract the heading/subheading map fresh for each paper.
- Figure/Table slide titles should use the nearby paper heading/subheading;
  Figure/Table identifiers and summaries belong in captions and notes.
- Kept v0.2.6 behavior for safe border removal, source-mention visual asset
  placement, color-neutral table title-band preservation, natural split points,
  repeated headers, and same-width split canvases.

## v0.2.6-safe-border-removal - title-band color-neutral update 2026-06-11

- Generalized split-table title-band preservation. Do not identify table title
  bands by color; blue is only one possible style.
- If visual/semantic review confirms a region is the table title band, preserve
  it on every split table image regardless of color, fill, border, or journal
  style.

## v0.2.6-safe-border-removal - source-mention placement update 2026-06-11

- Migrated Eric's preferred v0.2.3 Figure/Table placement logic into canonical
  v0.2.6.
- Visual asset slides should be placed near the article section or paragraph
  that introduces, cites, or interprets that Figure/Table, using captions,
  inline references, and nearby section headings as anchors.
- Removed the need to front-load overview/differential-diagnosis/clinical
  decision tables purely by teaching function. v0.2.6 should preserve the
  article's narrative order unless the paper itself uses a visual item as a
  summary/checklist.

## v0.2.6-safe-border-removal - table split protocol update 2026-06-11

- Restored v0.2.6 to the canonical version library at Eric's request.
- Added a reusable long-table split protocol: split only at natural row or
  category boundaries, repeat the original table title band and column-header
  row on every split image, and normalize all split images to the same-width
  canvas before building the deck.
- Added `scripts/postprocess_assets.py split-table` for reproducible
  header-preserving table splits after manual coordinate review.

## v0.2.6-safe-border-removal - restored live version 2026-06-11

- Downgraded the live skill from `v0.2.7-caption-aware-crops` back to
  `v0.2.6-safe-border-removal` at Eric's request.
- Removed live generation of `article_manifest.json` and `article_figures/`.
- Kept manual article-level crop workflow, `contact_sheet.png`,
  `crop_review.md`, `crop_overrides.json`, and safe type-aware
  `border_cleanup` QA.
- Preserved the former v0.2.7 tree under `skill_backups/`.

## retired v0.2.7-caption-aware-crops - 2026-06-11

- Added caption-aware expected Figure/Table detection from PDF text.
- Added `article_manifest.json` as the preferred planning source for deck
  Figure/Table assets.
- Added `article_figures/` output naming for paper-level figure/table crops.
- Added confidence levels (`high`, `medium`, `low`) and low-confidence manual
  review requirements.
- Added fallback guidance for vector figures, flowcharts, PRISMA diagrams,
  algorithms, and multi-panel radiology figures.
- Kept `contact_sheet.png`, `crop_review.md`, and `crop_overrides.json` as the
  QA and reproducibility safety net.
- This branch was later removed at Eric's request. The active preserved
  `v0.2.7-heading-consistent-titles` is a new branch created from v0.2.6, not
  a continuation of this retired caption-aware branch.

## v0.2.6-safe-border-removal - 2026-06-10

- Changed table outer-border cleanup from aggressive normalization to a safe,
  type-aware post-processing step.
- Added automatic asset classification for table, flowchart, figure, and
  unknown crops before border cleanup.
- Preserved flowchart semantic boxes by default; only clear outer page/frame
  lines may be removed.
- Added `border_cleanup` QA metadata and contact-sheet/crop-review reporting.
- Manual confirmation is required only for ambiguous or QA-warning crops, not
  every crop.

## v0.2.5-article-level-crops - 2026-06-10

- Promoted the skill workflow to prefer article-level Figure/Table assets over
  PDF object-level image crops.
- Added expected Figure/Table matching as a required deck-generation check.
- Added `crop_overrides.json` as the durable record for reproducible manual
  full-page-render crops.
- Added `references/article_level_crop_design.md` for the next automation
  step: caption-based block crops and same-page panel grouping.
- Kept v0.2.4 crop-review artifacts (`contact_sheet.png`, `crop_review.md`)
  as the safety net.

## v0.2.4-crop-review - 2026-06-10

- Added automatic crop-review artifacts after PDF extraction:
  `contact_sheet.png` and `crop_review.md`.
- Recorded crop-review paths and counts in `manifest.json`.
- Added CLI controls for contact sheet generation:
  `--no-contact-sheet` and `--contact-sheet-cols`.
- Strengthened the workflow gate: warning crops, split multi-panel figures,
  and mismatched Figure/Table counts must be manually resolved before deck
  generation.

## v0.2.3-main-logo - 2026-06-09

- Added `assets/dr_leether_logo.png` to the main/live skill.
- Updated `scripts/build_deck.py` to use the logo by default when
  `meta.logo_path` is not provided.
- Placed the symbol-only logo at the upper-right corner on all non-title and
  non-closing slides, including Part dividers.
- Kept title and Thank-You slides logo-free. Logo height is `0.55"` and
  vertically centered in the 1.00" header band.

## v0.2.2-part-header - 2026-06-09

- Adjusted Part-divider slides so their top header band and bright-blue divider
  match normal content slides (1.00" header + 0.10" divider).
- Kept the rest of the Part-divider layout unchanged: large centered `PART N`,
  middle section-title band, and bottom hairline remain in the same positions.

## v0.2.1-crop-qa - 2026-06-04

- Added explicit crop QA requirements for all figure/table crops before deck generation.
- Clarified that warning crops require manual inspection before final delivery.
- Kept the dark academic deck builder and figure extraction workflow unchanged.

## v0.2.0-table-crop-fix - 2026-05-28

- Updated `scripts/extract_from_pdf.py` table extraction to prefer caption-first crops.
- Avoided false table-caption detection from inline references such as `(Table 2)`.
- Used PDF rect/background blocks to constrain table boundaries when available.
- Improved bottom padding for table notes and source lines.
- Skipped overlapping `pdfplumber.find_tables()` fragments when a caption fallback crop already covers the table.
- No intentional changes to `scripts/build_deck.py`; the standard deck layout builder remains unchanged.