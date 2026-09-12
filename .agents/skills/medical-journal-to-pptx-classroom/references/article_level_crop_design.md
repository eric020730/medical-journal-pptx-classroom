# Article-Level Crop Design

## Goal

Produce one usable crop per article Figure/Table item, not one crop per PDF image object.

## Table acceptance across formats

PNG and EMF follow the same source-boundary and semantic review requirements.
For `vector-table`, repeat `--expected-text` for the reviewed title, column heading,
last row and footnote text. The command checks partial text/image/vector boundaries
before export and records provenance. Padding creates blank canvas outside the
validated crop, without reading additional source-page content.

Anchors do not detect all unwanted prose: a crop can include every anchor and still
include a neighboring paragraph. Inspect the original page, final asset and rendered
slide individually at readable size. Check all four edges, all rows/columns and
footnotes, and reject neighboring headings, body text or page furniture. Record each
asset's source page, reviewed bounds, row coverage, footnotes and visual result in
the run review. Structural pass is provisional until this comparison is complete.

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
  For photographic panels, set `export_image_panels: true` to additionally
  export `<Figure_ID>_<label>_image.png`. Each reviewed panel must contain
  exactly one complete image object. The tool uses that object's full bounds
  plus any coincident rectangular frame's actual stroke width, rechecks clipping, and records
  the actual output bounds. It never subtracts a fixed bottom-pixel strip.

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

## Preserve the Figure design independently of Table fixes

The white Figure grids from `source_crops` are **source-review previews**.
They preserve printed letters for source matching, but do not preserve the
classroom deck's composition. Do not replace an existing dark, equal-height
Figure slide with such a grid while repairing tables.

For the standard classroom photographic Figure design:

1. Match each panel to its original letter/caption and export image-only panels
   as above. Vector flowcharts or ambiguous raster-object groups need a reviewed
   custom panel boundary; do not force them through image-only export.
2. Compose those panels using the existing banded tool, in verified label order:

   ```text
   journal run recompose_panels_banded FINAL.png --inputs A_image.png B_image.png --cols 2 --labels A,B --geometry geometry.json --no-trim --bg "#061428" --label-pt 18
   ```

   `--no-trim` preserves the validated image extent. The compositor scales
   proportionally, aligns heights within each row, and reserves dark label
   bands. Do not add white padding to its input images. Preserve custom slide
   colors and spacing when the user supplies another design.
3. Build the deck with the final composite as its image; do not also set
   `panel_labels` for the builder (that would add a duplicate label set).
   Then add the native labels using the matching geometry:

   ```text
   journal run add_panel_labels base.pptx final.pptx --spec deck_spec.json --geometry geometry.json --label-pt 18 --color 8FA8C8
   ```

4. Run final QA on the labeled deck and render that exact file. Verify original
   label-to-image mapping, visible fixed-size labels, gutters, equal-height
   alignment and unchanged table pages, in addition to crop completeness.

Set `meta.panel_crop_plan` in the deck spec to the reviewed source plan path.
Keep `export_image_panels: true` in that plan for photographic figures. Final
QA uses this inventory and composite sidecar geometry to require exactly one
native 18pt #8FA8C8 label per expected panel at the reserved lower-right position,
even when builder `panel_labels` is absent. Never fall back to white review
crops with embedded black letters when image-only export fails. Investigate
the source boundary and retain a visible unresolved failure until repaired.
Font line-box overlaps may be excluded only when traced character bounds are
entirely outside the image crop; table crop validation remains unchanged.

For every new paper, inspect the full source pages to establish fresh bounds.
At minimum, Table review checks title, all columns, first and last rows, complete
row groups across splits, and every footnote. Anchor checks are a guard against
wrong regions, not a proof of arbitrary-paper correctness. If the text layer is
missing/unreliable, document the limitation and use full-page visual comparison;
never claim an automated completeness pass for unverified scanned content.
