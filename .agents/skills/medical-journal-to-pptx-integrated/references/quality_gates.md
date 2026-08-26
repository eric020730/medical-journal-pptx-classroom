# Integrated quality gates and image provenance

Run `scripts/qa_gate.py spec <spec> --mode full --style standard|nice`
before building and `scripts/qa_gate.py all <spec> --pptx <deck> --mode
full --style standard|nice` afterwards. Both commands combine independent
teaching-deck, specification, PowerPoint, logo, and PDF-polarity checks.
Any `[FAIL]` blocks delivery.

## Full-deck requirements and visual-style normalization

Every deck requires 40–55 slides, plus outline, references, and section
structure. Keep one canonical deck specification for both visual
styles. The `nice` builder maps canonical `outline` and `references` slides to
styled content and canonical `part` slides to full-bleed section dividers only
during rendering. Neither conversion changes the user's saved source spec.

The standard figure image box is 12.10 × 4.85 inches. The nice figure image box
is 12.13 × 4.95 inches. Use the selected dimensions when composing label bands
or matching split-table on-screen widths.

## Grayscale polarity and complete source chains

The extractor records each raw embedded image and its PDF-rendered counterpart.
`image_polarity.py` compares normalized grayscale pixels against a clipped PDF
render; a negative correlation identifies a PDF image stream whose visual
appearance requires color-space or `Decode` corrections.

Use the rendered `extracted/figures/` image or a verified page render as an
asset source. Every final raster Figure/Table requires a neighboring
`<image>.postprocess.json` sidecar. Preserve `source` for single-image
transformations and `source_inputs` for every panel in a recomposed Figure.
Intermediate crops must also preserve their own sidecars so provenance can be
walked recursively back to a trusted PDF-rendered asset listed in the extraction
manifest. A missing manifest, absent intermediate sidecar, malformed source
chain, or unknown terminal source is a blocking failure; never downgrade these
conditions to warnings. Direct vector-figure crops record the audited PDF as
their trusted source.

The gate rejects raw inverted images, inverted intermediate crops, inverted
inputs hidden in multi-panel composites, raw panel fragments used as slides,
duplicated paper Figure numbers, missing geometry, unsafe table margins,
mismatched split-table widths, untranslated speaker notes, unrendered note bold
markup, missing bundled logos, and expected native panel labels that are absent
from the finished PowerPoint. Figures with native-label provenance must be
stamped with `add_panel_labels.py` before final QA. Figures whose source labels
overlap image content preserve the original letters and record
`source_label_policy: preserve`, `native_labels: false`, and `embedded_labels`.
The gate rejects duplicate native labels, overwritten clinical image pixels,
panel-edge cleanup exceeding its recorded per-side limit, and source-row seam
adjustments lacking a verified embedded-label frame or exceeding their declared
pixel budget. Speaker notes
must reference only labels present in either safe native or preserved source
metadata. EMF vector tables bypass
raster-sidecar requirements while retaining their aspect ratio and white
presentation card.

## Optional rendering

LibreOffice and Poppler improve visual QA but are not required to produce an
editable `.pptx`. If either tool is unavailable, preserve the completed QA-safe
PowerPoint and clearly state which optional PDF or preview step was skipped.
