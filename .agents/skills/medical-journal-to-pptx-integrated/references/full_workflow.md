# Complete Medical-Journal Teaching Workflow

Convert an authorized medical-journal article into a complete, editable
40–55-slide PowerPoint for any medical specialty. Visible slide text is
English, every slide has substantive Traditional Chinese speaker notes, and
each source figure occupies exactly one dedicated slide. Select `standard` or
`nice` styling without changing the source article, content mode, or QA rules.

## Workspace, privacy, and required inputs

Resolve the skill root from the installed skill and the output directory from
the user's request and applicable workspace `AGENTS.md`. Never assume a
particular repository, user account, cloud-storage provider, specialty, source
article, or previously generated presentation.

- Read only an article the user is authorized to provide.
- Save final `.pptx` and optional `.pdf` files directly in the requested output
  directory; avoid overwriting an unrelated presentation.
- Store extracted images, source manifests, deck specifications, crop review,
  provenance sidecars, and QA reports in `.skill-work/<run-id>/`.
- Never publish source articles, clinical information, generated decks,
  credentials, personal paths, or intermediate working files.
- For demonstrations and regression tests, generate entirely synthetic content.

Start with:

```bash
python3 <skill-root>/scripts/run.py doctor
python3 <skill-root>/scripts/run.py prepare <authorized-paper.pdf> \
  --workspace <workspace> --output-dir <output-directory> \
  --mode full --style <standard-or-nice> --json
```

On Windows, invoke the same script with `py -3`. The portable entry point
resolves its own installed runtime or a compatible Python environment.

## Analyze the article and plan the complete presentation

Read the entire article, its figures, captions, tables, references, and
supplementary information supplied by the user. Identify study design,
population, methods, endpoints, results, uncertainty, limitations, clinical
implications, and the article's actual heading hierarchy. Do not fabricate
measurements, diagnoses, citations, or outcomes.

Plan 40–55 slides including a title, an outline with useful slide ranges,
section dividers, structured teaching content, source figures and tables,
references, and a closing slide. Adapt the balance to the article type and
evidence rather than applying a specialty-specific template. Place figures and
tables near their first meaningful discussion. Record and explain any omitted
source figure or table in the run manifest.

Use the article's own heading and subheading wording where practical. Keep
English slide bodies concise and organized into labeled blocks, supporting
details, interpretation, and actionable takeaways. Speaker notes explain the
reasoning, evidence, limitations, and interpretation in Traditional Chinese;
introduce important English medical terms as `**Term**（中文翻譯）`.

Read [slide structure](slide_structure.md), [deck schema](deck_spec_schema.md),
or [speaker-note style](notes_style.md) only when that specific guidance is
needed.

## Extract and inspect every source asset

Preparation produces extracted text, page renders, embedded image streams,
PDF-rendered figure candidates, table crops, a source manifest, a contact
sheet, crop-review notes, and an image-polarity audit. Review the contact sheet,
captions, source metadata, page geometry, and crop warnings before selecting
assets. Table renders use a high-resolution setting suitable for dense text.

Embedded grayscale streams can disagree with their visual PDF appearance when
the document applies a `Decode` array or color-space transform. Use a verified
PDF-rendered figure, a decoded page crop, or another audited source; never put
an inverted raw embedded stream into the presentation.

For every final raster asset, preserve its neighboring
`<asset>.postprocess.json` sidecar:

- A direct transformation records its trusted `source`.
- A composite records every `source_inputs` entry.
- Intermediate crops keep their own sidecars so provenance can be followed
  recursively to an audited, PDF-rendered source in the extraction manifest.
- Vector diagrams cropped directly from the document identify the audited PDF
  as their source.
- A missing manifest, missing sidecar, unknown terminal source, malformed
  source chain, or inverted ancestor is a blocking QA failure.

Consult [quality gates and image provenance](quality_gates.md) when resolving
extraction, provenance, or grayscale-polarity failures.

## Crop conservatively and protect meaningful content

Classify each asset as a raster figure, multipanel figure, vector diagram,
flowchart, or table. Derive crop boundaries from the current article rather
than assuming fixed page coordinates, dimensions, figure numbers, or layouts.
Retain anatomy, annotations, scale bars, legends, axes, labels, connectors,
arrows, diagram boundaries, table headers, complete rows and columns,
footnotes, abbreviations, and source lines.

Use the bundled postprocessing helpers to remove unnecessary page margins,
detect the actual page or image background, and preserve semantic edges. The
background-aware trimmer handles white, gray, dark, and mixed backgrounds
without treating meaningful text or a diagram border as disposable whitespace.

```bash
python3 <skill-root>/scripts/postprocess_assets.py trim \
  <verified-source> <final-figure> --asset-type figure
python3 <skill-root>/scripts/postprocess_assets.py trim \
  <verified-table> <final-table> --asset-type table --margin 12
```

For raster panels on a dark slide, inspect each outer edge independently for a
thin white, gray, or anti-aliased seam. The banded recomposer removes only a
verified achromatic seam and defaults to a hard four-pixel maximum per side;
dark image background, colored perfusion scales, bright anatomy touching an
edge, and light regions extending beyond the inspection budget are preserved.
Never substitute a broad background-aware crop for this bounded panel cleanup.
Do not apply panel rim cleanup to a table, flowchart, algorithm, or vector
diagram. Record manually chosen crop boundaries in `crop_overrides.json`.

For difficult layouts, read
[article-level crop design](article_level_crop_design.md).

## Preserve one figure per slide and rebuild multipanel figures

Each source figure maps to exactly one figure slide and one final recomposed
image. Panel crops are intermediate assets; never point a slide at an
individual panel fragment or distribute one article figure across multiple
slides.

When a labeled raster figure contains multiple panels:

1. Separate each panel without overwriting or losing meaningful image content.
2. Preserve provenance for every panel and intermediate transformation.
3. Compare every reading-order-preserving row/column arrangement against the
   selected slide-box dimensions, each panel's aspect ratio, gutter width, and
   fixed-size label bands. Select the arrangement that maximizes the displayed
   area of the smallest panel; use panel short-edge readability, total image
   area, empty cells, and fewer rows as tie-breakers. Align row heights and row
   widths, and fill controlled gutters with the selected slide background.
4. Inspect the actual location of each source A/B/C/D letter. If any letter is
   embedded in image content, preserve the original letters for the entire
   figure and do not draw a second set. Never cover a label with a black/white
   rectangle, fill, content-aware inpainting, or fabricated image pixels.
5. Remove source letters only when each is demonstrably confined to a separate,
   uniform exterior margin. Record its placement and bounding box in the panel
   sidecar; if the surrounding margin contains anatomy, color scales, or
   annotations, preserve all source labels instead.
6. Provide native-label geometry only for source-label-free panels, and explain
   every visible A/B/C/D panel individually in Traditional Chinese notes.

Prefer editable, native fixed-size PowerPoint panel labels when uniform size
and precise row spacing matter:

```bash
python3 <skill-root>/scripts/recompose_panels_banded.py <final-figure> \
  --inputs <panel-a> <panel-b> <panel-c> <panel-d> \
  --labels A,B,C,D --geometry <panel-geometry.json> \
  --source-label-policy auto --max-edge-px 4 \
  --gap-above-in 0.06 --gap-below-in 0.12 --label-pt 18 \
  --bg '#061428' --slide-box-w-in 12.10 --slide-box-h-in 4.85

python3 <skill-root>/scripts/add_panel_labels.py <built.pptx> <labeled.pptx> \
  --spec <deck-spec.json> --geometry <panel-geometry.json> --label-pt 18
```

Use `--source-label-policy preserve` when the source visibly contains embedded
panel letters but an older extractor has no placement metadata. Modern panel
sidecars can provide `source_label_placement: embedded` and `embedded_label`,
or `source_panel_label: {placement: external-margin, box_px: [x0,y0,x1,y1]}`;
`auto` preserves embedded labels and crops an exterior margin only after
confirming that its pixels outside the label are uniformly blank. An unsafe
margin falls back to preservation. Preserved figures receive no native-label
band and no geometry entries, so their images can occupy more slide area.
Do not add slide-spec `panel_labels` to preserved figures. Their sidecars keep
`embedded_labels` for speaker-note validation instead.

Omit `--cols` for automatic layout selection. Four portrait or approximately
square panels frequently fit better in a single left-to-right 1 × 4 row than
in a 2 × 2 grid on a widescreen slide; wide panels may remain more legible in
multiple rows. Do not force either arrangement universally. Add `--cols N`
only when article semantics or an explicit user request requires that manual
override. The sidecar records the selected arrangement and every candidate's
measured on-screen panel sizes for reproducible review.

The standard figure box is 12.10 × 4.85 inches; the nice figure box is
12.13 × 4.95 inches. Pass the selected dimensions to the panel recomposer and
use the same `--label-pt` value when stamping native labels. Final QA checks
that every expected native label is visible, that preserved source labels are
not duplicated, that source pixels were not overwritten, and that bounded edge
cleanup remains within its declared limit.

## Preserve complete tables and vector assets

Keep a visible safety margin on all four sides of raster tables: the default is
12 pixels and the accepted range is 8–24 pixels. Do not deliver a table whose
text, gridlines, heading, footnote, or outer row touches the image edge.

Split a tall table only at a meaningful row boundary. Repeat its title and
column headers on every part, preserve footnotes where relevant, normalize the
source-canvas widths, and assign the same `image_width_in` to each part. For
parts with a shared pixel width, calculate an on-screen width that fits the
tallest part:

```text
image_width_in = selected_slide_box_height_in × common_pixel_width
                 ÷ tallest_table_part_pixel_height
```

Tables are the only source item allowed to span multiple slides. Preserve EMF
vector tables as editable, aspect-correct vector pictures on a suitable white
presentation card. Do not rasterize an available, valid EMF merely to satisfy
raster-sidecar rules.

Detect vector figures, flowcharts, decision trees, and other diagrams from
page drawing objects and rendered page regions, not just embedded image
streams. Protect every meaningful frame, connector, arrow, label, and legend.

## Author, validate, build, and verify

Create one fresh JSON deck specification from the current article. Use
the bundled logo or an authorized user-provided replacement, keep slide-visible
text entirely English, and provide complete Traditional Chinese notes for every
slide, including section dividers. Render note emphasis as real formatted
PowerPoint runs rather than leaving literal Markdown markers.

Audit the finished assets before building:

```bash
python3 <skill-root>/scripts/postprocess_assets.py audit-final \
  <final-assets> --spec <deck-spec.json>
python3 <skill-root>/scripts/run.py qa-spec <deck-spec.json> \
  --mode full --style <standard-or-nice>
python3 <skill-root>/scripts/run.py build <deck-spec.json> \
  --out <output.pptx> --mode full --style <standard-or-nice>
```

If a figure uses native-label geometry, stamp its panel labels after building
and run final QA on the stamped file:

```bash
python3 <skill-root>/scripts/run.py qa <final-output.pptx> \
  --spec <deck-spec.json> --mode full --style <standard-or-nice>
```

Both independent validators must pass before delivery. They cover slide count,
article metadata, outline and references, source heading order, English visible
content, Traditional Chinese notes, authentic note formatting, figure uniqueness,
recursive source provenance, grayscale polarity, multipanel geometry, native
labels, logo placement, table margins, split-table display widths, EMF assets,
and the final editable PowerPoint.

LibreOffice and Poppler are optional. When available, export a PDF or inspect
rendered slides; when unavailable, retain the verified `.pptx` and clearly
identify the optional rendering step that could not run.

For precise script contracts, see
[script-level quality expectations](script_quality_expectations.md).
