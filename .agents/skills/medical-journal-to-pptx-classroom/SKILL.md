---
name: "medical-journal-to-pptx-classroom"
description: "Turn a medical journal PDF into a complete 40-55-slide editable teaching PowerPoint with English slides, Traditional Chinese speaker notes, extracted figures and tables, PDF image-inversion protection, advanced two-stage QA, and cross-platform local tooling."
---

# Medical Journal to PPTX: Portable Classroom Edition

This repository packages the complete `medical-journal-to-pptx`
`v0.2.38-bg-aware-trim` image and PowerPoint pipeline without a machine-specific
username, Python installation, or output directory.

## Resolve the project and its tools

The project root is the ancestor containing `.classroom-project.json`.
The installed Python environment is `.venv/bin/python` on macOS/Linux and
`.venv/Scripts/python.exe` on Windows. Do not use another project's environment.

Use the repository launcher; it also discovers LibreOffice and Poppler when
Windows or macOS did not add them to `PATH`:

```text
macOS/Linux: ./journal doctor
Windows:     journal.cmd doctor
```

Other useful commands:

```text
journal paths --json
journal init-run "path/to/paper.pdf" --mode full --json
journal prepare "path/to/paper.pdf" --mode full --json
journal run extract_from_pdf "paper.pdf" --out ".skill-work/run/extracted"
journal run postprocess_assets trim input.png output.png --asset-type figure
journal run postprocess_assets audit-final final_assets --spec deck_spec.json
journal image-qa extracted/manifest.json --spec deck_spec.json
journal qa-spec deck_spec.json --mode full
journal run build_deck deck_spec.json --out outputs/presentation.pptx
journal qa outputs/presentation.pptx --spec deck_spec.json --mode full
journal render outputs/presentation.pptx --preview
```

Write finished PowerPoint and optional PDF files directly into `outputs/`.
Keep extraction assets, intermediate images, manifests, specs, and previews in
`.skill-work/<run-id>/`. Never overwrite an unrelated existing output.

If required Python packages are missing, ask the user to run
`setup-macos.command` or `setup-windows.cmd`. Missing LibreOffice or Poppler
must not prevent generating the editable `.pptx`; explain which optional PDF
export or preview step could not run.

## Produce a complete teaching deck

`full` is the only supported presentation mode and always produces 40-55
slides. Before planning the deck, read
[the preserved full v0.2.38 workflow](references/full_workflow_v0.2.38.md).
Preserve language correctness, image safety, speaker notes, figure attribution,
and the requirement to verify the generated PowerPoint.

## Workflow

1. Identify the current PDF. Resolve relative paths from the repository root;
   do not modify the source PDF. Initialize a collision-safe run with
   `journal prepare "paper.pdf" --mode full --json`.
2. Read the extracted paper, page renders, manifest, contact sheet, and crop
   review. `prepare` also compares every embedded image with its PDF-rendered
   appearance and records unsafe inverted streams in `polarity-report.json`.
   Record the article title, authors, citation, heading structure,
   research question, methods, important numeric findings, limitations, every
   figure/table, and conclusion. Never invent unavailable publication details.
3. Prepare final figure/table assets using the bundled upstream scripts.
   Use color-decoded `extracted/figures/` images or safe reviewed page renders;
   never substitute raw `extracted/image_pXX_YY.*` streams. Preserve original
   source paths in asset sidecars, including every recomposed panel.
   Preserve all clinically meaningful anatomy, arrows, legends, labels, axes,
   table columns, and footnotes. Flowcharts are not photographic panels; tables
   keep an 8-24 px white safety margin. Every final raster asset needs its
   `.postprocess.json` sidecar.
4. Map each paper Figure to exactly one presentation figure slide. Recompose
   labeled multi-panel figures before placing them in the deck. A tall table may
   be split into clearly labeled table parts when the content would otherwise
   become unreadable. Explain any unavoidable omissions in the run manifest.
5. Write a fresh `deck_spec.json`. Use
   [the bundled deck schema](references/deck_spec_schema.md) when needed. Keep
   every visible slide field in English. Write scan-friendly Traditional Chinese
   speaker notes on every slide, with accurate English medical terms and
   article-specific explanations. Use the original bundled logo and visual
   style unless the user supplies an authorized replacement.
6. Run the upstream asset audit and then
   `journal qa-spec <deck_spec.json> --mode full` BEFORE building. This
   checks source metadata, required sections, English-only visible text, Chinese
   notes, figure uniqueness, panel geometry, table safety, and image polarity.
7. Build the `.pptx`, then run
   `journal qa <pptx> --spec <deck_spec.json> --mode full`. Fix each
   failure and rerun both gates until they pass. Export PDF and previews with
   `journal render <pptx> --preview` when the required tools are available.
8. Report the actual saved files, slide count, QA result, and any omitted
   figures, tables, or optional render steps. Do not claim an output exists or
   passed checks until the corresponding command completed successfully.

For speaker-note conventions, read
[the notes style](references/notes_style.md) only when writing notes. For
complex figure crops, read
[article-level crop design](references/article_level_crop_design.md) only when
the extracted assets require it. The complete original image pipeline remains
available under `scripts/`.

## Safety and classroom constraints

- Use only user-authorized papers. Do not upload identifiable patient data or
  commit source PDFs and generated presentations to Git.
- The bundled demonstration article is synthetic; label its data fictional.
- Free-plan Codex availability and exact skill access depend on the current
  account and product surface. Never promise enough usage for a complete deck.
- Do not call AI image generation. Figures are extracted from the supplied PDF;
  no image-generation entitlement or OpenAI API key is required.
- Do not require Microsoft PowerPoint to create a `.pptx`. LibreOffice is used
  for optional PDF export and stronger visual QA, not for core PPTX generation.
