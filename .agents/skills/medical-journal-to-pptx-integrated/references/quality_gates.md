# Integrated quality gates and image provenance

Run `scripts/qa_gate.py spec <spec> --mode full --style standard|nice`
before building and `scripts/qa_gate.py all <spec> --pptx <deck> --mode
full --style standard|nice` afterwards. Both commands combine independent
teaching-deck, specification, PowerPoint, logo, and PDF-polarity checks.
Any `[FAIL]` blocks delivery.

The builder embeds a deterministic manifest in the PowerPoint: skill version,
selected style, exact presentation canvas dimensions, canonical specification
hash, per-slide content/notes hashes,
source image hashes, and a visual fingerprint of every shape's stable OOXML,
embedded picture bytes, z-order, bounds, rotation, fill, line, picture crop,
typography, and slide visibility flags. Final QA requires this manifest,
compares it with the supplied spec and actual deck, and independently renders a
fresh canonical baseline. Managed native-label shapes are accepted only through
an exact name/text/size allow-list derived from the spec and sidecar. A locally
rewritten manifest cannot bless an arbitrary overlay. A deck built from another article,
another style, another image, or modified notes must fail even when its slide
count and topology happen to match.

The package fingerprint also covers presentation and slide XML (including
timing and transitions), masters, layouts, themes, relationships, media, fonts,
charts, and embedded objects. The manifest is stored in the standard OOXML
custom-properties part so both PowerPoint and LibreOffice can load and export
the deck. Its package relationship, target, and content-type override must each
exist exactly once and match the standard values.

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

The extraction manifest uses a strict schema and records the source-PDF
SHA-256, render DPI, complete 1-based page inventory, and SHA-256 for every
enumerated raster. QA freshly rerenders every PDF page, authenticates figure and
table crops against their declared page geometry, requires unique figures to be
byte-identical aliases, and accepts only the verified report inventory as a
trusted terminal. An absolute/out-of-root artifact path, duplicate or invalid
page number, out-of-page bounding box, malformed list, hash mismatch, or
mutable manifest injection is a blocking failure rather than a warning or
traceback. Extraction only writes into a new or empty directory and never
deletes files based on manifest contents.

Use the rendered `extracted/figures/` image or a verified page render as an
asset source. Every final raster image used by any slide—including
`content.image`—requires a neighboring
`<image>.postprocess.json` sidecar. Preserve `source` for single-image
transformations and `source_inputs` for every panel in a recomposed Figure.
Intermediate crops must also preserve their own sidecars so provenance can be
walked recursively back to a trusted PDF-rendered asset listed in the extraction
manifest. A missing manifest, absent intermediate sidecar, malformed source
chain, or unknown terminal source is a blocking failure; never downgrade these
conditions to warnings. Direct vector-figure crops record the audited PDF as
their trusted source and include `command: crop-vector-figure`, page, DPI,
detected/effective PDF bounding boxes, PDF crop margin, and outer-frame metadata
so QA can deterministically regenerate the padded raster and require exact
decoded pixels.

Raw embedded PDF streams are never trusted provenance terminals, even when a
quick polarity comparison is inconclusive. Provenance traversal distinguishes
cycles from a legitimate shared DAG and binds polarity comparison only to the
rendered ancestor named by that asset's own source chain.

The gate rejects raw inverted images, inverted intermediate crops, inverted
inputs hidden in multi-panel composites, raw panel fragments used as slides,
duplicated paper Figure numbers, missing geometry, unsafe table margins,
mismatched split-table widths, untranslated speaker notes, unrendered note bold
markup, missing bundled logos, and expected native panel labels that are absent
from the finished PowerPoint. Figures with native-label provenance must be
stamped with `add_panel_labels.py` before final QA. Figures whose source labels
overlap image content preserve the original letters and record
`source_label_policy: preserve`, `native_labels: false`, and `embedded_labels`.
Mixed figures record `source_label_policy: mixed`, disjoint `embedded_labels`
and `native_label_values`, and native geometry only for the latter. Source-space
label/image/crop geometry overrides stale placement flags; exterior labels must
pass the uniform-margin crop test before receiving `#8FA8C8` native labels.
The gate rejects duplicate native labels, overwritten clinical image pixels,
panel-edge cleanup exceeding its recorded per-side limit, and source-row seam
adjustments lacking a verified embedded-label frame or exceeding their declared
pixel budget. Speaker notes
must reference only labels present in either safe native or preserved source
metadata. Simplified-only forms, repeated glyph/short-phrase padding,
non-string notes, missing latter-half content takeaways, and normalized
boilerplate or ≥97%-similar templates reused on more than two slides fail. Note normalization ignores
punctuation, case, and page/slide/teaching ordinals while preserving clinical numeric
values. EMF vector tables bypass only raster padding/polarity fields. They still
require a typed vector sidecar, the audited extraction manifest and source-PDF
hash, an authenticated page/bbox, and exact deterministic PDF→SVG→EMF replay.

Final raster Figure/Table sidecars record `safety_margin_px`,
`padding_background`, `unpadded_size_px`, and `padded_size_px`. These fields are
required, strongly typed, dimensionally consistent, and equal to the decoded
image dimensions. QA also inspects the decoded outer bands and requires their
pixels to match the declared padding background; metadata alone cannot claim a
nonexistent canvas. Transparency and an all-background/blank unpadded core also
fail. Supported single-image helpers and all final raster compositors are
deterministically replayed from their declared source(s); decoded output pixels
must match exactly, so localized replacement content cannot hide behind a
global similarity score. The normal
default is an exact 16 px canvas applied after cleanup; intermediate crops use
0 px. Multi-panel candidate fits and native-label anchors must be derived from
the padded composite dimensions, never from coordinates calculated before an
after-the-fact border was added.

The expected logo is resolved from `meta.logo_path` with the same fallback used
by the builder; custom authorized logos are hashed and validated instead of
being mistaken for a missing bundled logo. Panel labels must occur exactly once
at finite in-slide coordinates near the associated figure.

## Optional rendering

LibreOffice and Poppler improve visual QA but are not required to produce an
editable `.pptx`. If either tool is unavailable, preserve the completed QA-safe
PowerPoint and clearly state which optional PDF or preview step was skipped.
