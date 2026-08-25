---
name: medical-journal-to-pptx-integrated
description: Create comprehensive 40-55-slide teaching PowerPoints from an authorized medical-journal PDF, with English slides, Traditional Chinese speaker notes, verified figures and tables, and standard or nice styling.
---

# Medical Journal to PowerPoint: Integrated Edition

This globally installable skill is self-contained. Resolve its root from this
`SKILL.md`; never assume a particular repository, username,
cloud-storage directory, or an existing project's virtual environment.

Use `scripts/run.py` as the portable entry point. On macOS/Linux invoke
`python3 <skill-root>/scripts/run.py`; on Windows use
`py -3 <skill-root>\scripts\run.py`. The entry point finds the installed shared
runtime or a compatible current Python environment.
For a copyright-safe example without patient data, run
`scripts/run.py demo --out <workspace>/synthetic-demo.pdf`.

## Create a full teaching deck and choose its visual style

- `--mode full`: always produce 40–55 slides for comprehensive journal-club
  teaching. Before authoring the deck, read
  [the complete image and teaching workflow](references/full_workflow.md).
- `--style standard`: dark-academic progress bars, outline cards, and
  numbered Part dividers; see [standard styling](references/visual_style.md).
- `--style nice`: kicker headers, full-bleed numbered section dividers, and
  optional white-card figures; see [nice styling](references/visual_style_nice.md).

`full` is the only supported content mode. Default to `standard` unless the
user chooses `nice`. Both styles preserve image safety, source attribution,
language rules, and final QA.

## Run the workflow

1. Resolve the user's authorized source PDF, active workspace, and requested
   output location. Follow workspace `AGENTS.md` output rules when present;
   otherwise place final `.pptx` and optional `.pdf` directly in the workspace
   or user-selected output directory. Keep all run files in
   `<workspace>/.skill-work/<run-id>/`; never overwrite an unrelated deck.
2. Run `scripts/run.py doctor`, then
   `scripts/run.py prepare <paper.pdf> --workspace <workspace> --output-dir
   <output-dir> --mode full --style <standard|nice> --json`.
   Preparation freshly extracts the paper, compares every embedded grayscale
   image with its PDF-rendered appearance, and writes a polarity report.
3. Inspect extracted text, the contact sheet, crop review, captions, and source
   metadata. Read [crop design](references/article_level_crop_design.md) only
   when complex assets require it. Use PDF-rendered or decoded figure images,
   never raw inverted image streams. Retain provenance sidecars through
   intermediate crops and multi-panel recomposition.
4. Process assets with the bundled image-processing helpers. Each paper Figure becomes
   exactly one recomposed figure slide. Preserve source A/B/C/D labels when
   they overlap image content; never mask or inpaint clinical pixels. Use native
   labels only when source letters are absent or isolated in a verified exterior
   margin. Reconcile source-row seams that split verified boxed embedded labels;
   never move a seam through a colored clinical scale. Remove only confirmed
   thin white/gray rims from single or multipanel raster figures, at most four
   pixels per side by default. Automatically compare horizontal and multi-row
   arrangements against the selected slide box, panel aspect ratios, gutters,
   and label bands; choose the arrangement that maximizes readability of the
   smallest displayed panel. Protect anatomy, annotations, flowcharts, table
   headers, and footnotes. Raster tables retain an 8–24 px safety margin;
   preserve split-table display widths and optional EMF vector tables.
5. Write a fresh specification with English-visible content and substantive,
   scan-friendly Traditional Chinese notes on every slide. Use
   [the deck schema](references/deck_spec_schema.md) and
   [speaker-note conventions](references/notes_style.md) when needed. Preserve
   paper-native headings, source metadata, and an explicit record of omissions.
6. Run `scripts/run.py qa-spec <spec.json> --mode full --style <style>` and
   fix every reported failure. Build with
   `scripts/run.py build <spec.json> --out <output.pptx> --mode full --style
   <style>`. Add native panel labels only when the run includes native-label
   geometry; preserved embedded labels must never be duplicated.
7. Run `scripts/run.py qa <output.pptx> --spec <spec.json> --mode full
   --style <style>` and fix failures until the independent deck, presentation,
   and PDF-image gates all pass. Use `scripts/run.py render <output.pptx>` when optional
   LibreOffice is available. Report only verified final artifacts.

For QA failure meanings and source-chain requirements, read
[quality gates and image provenance](references/quality_gates.md). For detailed
script contracts, read [script-level quality expectations](references/script_quality_expectations.md).
Never upload
or publish source papers, patient data, generated decks, credentials, or run
artifacts without explicit user authorization.
