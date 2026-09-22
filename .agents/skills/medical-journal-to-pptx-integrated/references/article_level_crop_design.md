# Article-Level Crop Design

## Goal

Produce one usable crop per article Figure/Table item, not one crop per PDF image object.

## Pipeline

1. Render pages and extract their text and word-position metadata.
2. Build the expected figure/table list from caption-like text. Never infer the
   article number from `extracted/figures/Figure_XX.png`; `XX` is extraction order.
3. Write `article-asset-map.json` (`medical-journal-article-asset-map/v1`) with
   the source PDF and extraction-manifest hashes. For every `figure:N` or
   `table:N`, record the caption page/bbox, canonical caption text/hash, bound
   manifest file/hash/page, and a supported spatial association method.
4. Validate the map with `scripts/run.py run article_asset_map -- <map.json>`.
   The validator re-extracts caption text and replays nearest-caption geometry.
5. Use object candidates, page renders, and table crops as planning inputs.
6. For each expected label, verify nearby candidate components against the paper.
7. Merge components into article-level final assets when needed.
8. Preserve manual crop coordinates or notes in `crop_overrides.json`; do not
   use that mutable planning file in place of the authenticated article map.
9. Add unresolved crop concerns to the working notes and `crop_review.md`.
10. Keep intermediate panel crops unpadded. After all crop and seam decisions
    are complete, finalize clinical images with a 0 px outer raster canvas,
    nonclinical figures/flowcharts with exactly 16 px, and tables with 8–24 px
    white (default 16). Include the applicable margin in fit and label geometry.

## Touching Clinical-Grid Seams

When adjacent clinical panels have no white gutter, an equal canvas split is
not evidence of the true boundary. Rows in the same apparent grid can have
different panel widths after journal layout, PDF placement, or rasterization.

1. Review one row (for an x seam) or one column (for a y seam) at a time. Use a
   narrow search interval around the visible transition, not the whole image.
   Never start from equal widths/heights, a canvas fraction, or the coordinate
   selected for another row or column.
2. Run `postprocess_assets seam-review INPUT REPORT OVERLAY --axis x|y --band
   START END --search START END --selected PX` and inspect the green selected
   line on the native-resolution overlay. The pixel score only checks that the
   selected coordinate follows the strongest local raster transition; it does
   not replace visual review.
3. Attach every passing report to each constrained `panel-crop` edge by
   repeating `--seam-review REPORT --seam-edge right|left|bottom|top`. Repeat
   `--require-seam-edge EDGE` for every interior edge expected on that crop.
   The helper stores an edge-keyed multi-seam evidence map and verifies the
   source hash, reviewed band, overlay hash, and exact crop coordinate. A panel
   bounded on three sides must therefore carry three independent bindings.
4. Do not copy a seam coordinate from one row/column to another unless the same
   report band actually covers both crops. Preserve separate reports when the
   transitions differ even by only a few pixels.
5. When the source contains a gutter, its two image boundaries may differ.
   Review and bind the left panel's terminal edge and right panel's starting
   edge separately; do not force the crop rectangles to touch.
6. Record the reviewed coordinates and report paths in `crop_overrides.json`.
   Keep the reports and overlays with the run QA evidence.
7. For a `clinical-image` recomposition, the banded compositor groups exact
   panel crops by authenticated source, infers the nearest overlapping neighbor
   to the right and below, and derives both sides of every internal adjacency.
   It refuses the composite when any inferred edge is absent from either
   `required_seam_edges` or `seam_reviews`. The final sidecar records the
   deterministic `medical-journal-source-seam-topology/v1` graph, and QA
   regenerates and compares that graph. This closes the legacy path where a
   caller omitted `--require-seam-edge` entirely.
8. Treat every required edge with a matching seam review as locked. The
   recomposer's embedded-label recovery may reconcile a rough, unreviewed crop,
   but it must never move a locked edge. A bright acquisition frame or an
   adjacent panel letter near a reviewed row boundary is not permission to
   expand the upper panel into the lower panel.

## Reviewed PDF-coordinate crop plans

For tables and PDF-rendered multi-panel figures, use `source_crops.py` with a
new output directory and a plan bound to the source PDF SHA-256. The plan must
enumerate every expected asset. Table entries require page, PDF-point bounds,
and title/header/last-row/footnote text anchors. Figure entries require ordered
panel labels and reviewed panel bounds; `export_image_panels: true` creates
image-only inputs for the banded compositor while preserving the source-review
grid as review evidence only.

Reject out-of-page bounds, partial text, partial raster objects, and partial
vector rectangles. Validate source bounds before adding padding. Padding belongs
on a new canvas and must never expand the PDF crop into adjacent prose. Compare
the original page, generated asset, and rendered slide; the generated QA report
is structural evidence and still requires visual review.

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

When a five-panel clinical figure contains one portrait reference panel plus a
2×2 group, a reviewed `left-span-2x2` layout may preserve the portrait panel at
full height. Use it only with exactly five panels and embedded source labels.
Use `right-span-2x2` when the third input panel is the full-height right-hand
span and panels 1–2/4–5 form the upper/lower 2×2 group. Keep semantic input
order; never move a right-spanning source panel to the left merely to fit a
template.

When a four-panel clinical figure contains two full-height panels followed by
two half-height panels stacked in one right-hand column, preserve that topology
with `two-span-right-stack`. Do not flatten it to four equal-height panels: even
when every individual aspect ratio remains intact, that rewrite doubles the
stacked panels' scale relative to the spanning panels and changes the source's
visual evidence hierarchy. The template requires exactly four panels with
preserved embedded labels. Verify that every output panel aspect ratio differs
from its cleaned source by less than 0.6%, and that the stacked panel/full-height
panel height ratio remains within 0.05 of the source ratio after adding the
reviewed gutter.

If an expected panel letter is visually absent, do not create a hand-written
sidecar. Run `panel-crop --label <A> --label-placement absent`; the helper binds
the reviewed full panel to a decoded-RGB SHA-256. Unknown or altered evidence
must remain unresolved and cannot authorize a native label.

## Failure Mode

If confidence is low, do not silently choose. Use a manual full-page-render crop
and record the decision in `crop_overrides.json`.

## Caption-bound table crops omitted by extraction

Do not modify an extraction manifest to insert missed tables. A v1 article asset
map may instead bind a table to an authenticated reviewed crop plan. Keep the
map's existing PDF and extraction-manifest hashes and `caption_evidence` fields.
Use exactly one source binding for this route (no mixed manifest/crop bindings):

```json
{
  "asset_id": "table:2",
  "kind": "table",
  "number": 2,
  "source_bindings": [{
    "type": "reviewed-pdf-crop-plan-v1",
    "plan": "source-crop-plan.json",
    "plan_sha256": "<SHA-256 of exact reviewed plan file bytes>",
    "asset_id": "table2",
    "page": 1,
    "bbox_pt": [230, 10, 435, 195],
    "header_bbox_pt": [230, 10, 435, 70]
  }],
  "association": {
    "method": "caption-in-reviewed-table-header-v1",
    "review_note": "Title, column headers, last row and footnote compared with the PDF."
  }
}
```

This fragment omits `caption_evidence` for brevity; that evidence remains
mandatory, including its exact PDF text, normalized-text hash, page, and bbox.
Resolve `plan` relative to the map; resolve the plan's `pdf` relative to the
plan file. The selected plan asset must be a table with matching ID, page,
bbox, source PDF/hash, DPI, and nonempty expected-text anchors. Its ID need not
encode the article number: the replayed caption establishes the article number.

The logical header must start at the crop's top edge, span its full width,
contain the complete caption bbox, and begin with the authenticated caption
text. For a natively split plan, it must lie within the repeated header.
This logical region does not crop or truncate a vector table frame. The full
crop still undergoes the source-crop text/image/vector clipping checks. Crops
containing references to a different numbered table fail closed and require a
more precise reviewed crop; a whole-page/PDF hash is never table identity.

Final raster provenance must reach the exact selected crop asset object and
renderer settings. Helper-generated splits and composites may share that root;
branches from another table or from a manifest page/image fail. The existing
source-crop v1 sidecar embeds the asset object, so no sidecar rewriting or new
manifest entries are needed. Changes to the plan file invalidate the map hash;
updating that hash does not authorize stale crops with different embedded asset
parameters. QA receipts traverse these nested plan references and the plan's
source PDF, so either dependency changing invalidates receipt reuse. Existing
manifest-based figure/table bindings retain their original route and checks.
