---
name: "medical-journal-to-pptx-classroom"
description: "Turn a medical journal PDF into a complete 40-55-slide editable teaching PowerPoint with English slides, Traditional Chinese speaker notes, source figures/tables, two-stage QA, mandatory PDF rendering and slide-preview inspection."
---

# Medical Journal to PPTX: Portable Classroom Edition

This repository packages the `medical-journal-to-pptx v0.2.38-bg-aware-trim` workflow with a project-local Python and rendering toolchain.

## Resolve the project and tools

The project root is the ancestor containing `.classroom-project.json`. Use `.venv/bin/python` on macOS/Linux or `.venv/Scripts/python.exe` on Windows. Never use another project's environment.

Use the repository launcher:

```text
macOS/Linux: ./journal doctor --strict
Windows:     journal.cmd doctor --strict
```

Useful commands:

```text
journal paths --json
journal prepare "paper.pdf" --mode full --json
journal run extract_from_pdf "paper.pdf" --out ".skill-work/run/extracted"
journal run postprocess_assets audit-final final_assets --spec deck_spec.json
journal image-qa extracted/manifest.json --spec deck_spec.json
journal qa-spec deck_spec.json --mode full
journal run build_deck deck_spec.json --out outputs/presentation.pptx
journal qa outputs/presentation.pptx --spec deck_spec.json --mode full
journal render outputs/presentation.pptx --preview
```

Write final PPTX and PDF files into `outputs/`. Keep extraction assets, manifests, specs and previews in `.skill-work/<run-id>/`. Never overwrite an unrelated output.

If any required package, LibreOffice or Poppler is missing, follow root `CODEX-START.md` and run the authorized `setup-codex.sh` / `setup-codex.ps1`. Do not hand manual installation commands back to the student and do not continue in a PPTX-only mode.

## Produce a complete teaching deck

`full` is the only supported mode and always produces 40–55 slides. Before planning, read `references/full_workflow_v0.2.38.md`. Preserve language correctness, source attribution, image polarity, speaker notes and all quality gates.

## Workflow

1. Resolve the authorized PDF without modifying it. Initialize a collision-safe run with `journal prepare "paper.pdf" --mode full --json`.
2. Read the extracted article, page renders, manifest, contact sheet and crop review. Record title, authors, citation, structure, research question, methods, important numeric findings, limitations, every figure/table and conclusion. Never invent missing publication details.
3. Prepare final assets using the bundled scripts. Use decoded `extracted/figures/` images or reviewed PDF page renders; never use unsafe raw image streams. Preserve anatomy, labels, legends, axes, table columns and footnotes. Each final raster asset needs its `.postprocess.json` provenance sidecar.
   For table or multi-panel crops, read `references/article_level_crop_design.md`. Table extraction candidates are not final assets: use reviewed PDF-point bounds and `journal run source_crops plan.json --out NEW_DIRECTORY`, with title/header/last-row/footnote anchors. Do not reuse another paper's coordinates or assume object extraction order equals A–D. Do not use fixed-pixel cuts to remove labels from medical images.
4. Map each article Figure to one presentation figure slide. Recompose labeled multi-panel figures before placement. A tall table may be split into clearly labeled parts only when needed for readability. Record unavoidable omissions.
   Keep crop validation separate from slide composition. Preserve an existing Figure design when fixing Tables. For the classroom photographic-figure style, export safe image-only panels and use the existing banded compositor (equal-height, proportional scaling, dark background) plus native 18pt labels. White source-review grids are not replacements for this design. See the crop-design reference for commands.
5. Write a fresh `deck_spec.json`. Visible slide content is English. Every slide receives substantive, scan-friendly Traditional Chinese notes with accurate English medical terminology and article-specific explanations. Use the bundled logo and visual style unless the user provides an authorized replacement.
6. Run asset audit and `journal qa-spec <deck_spec.json> --mode full` before build. Fix every failure; never weaken a QA rule.
7. Build the PPTX, then run `journal qa <pptx> --spec <deck_spec.json> --mode full`. Fix failures and rerun both gates until they pass.
8. Run `journal render <pptx> --preview`. The final deck is not quality-complete until LibreOffice creates the PDF, Poppler creates slide previews/contact sheet, and the rendered pages are visually inspected for clipping, overlap, unreadable text, bad crops or layout drift. Repair the spec/assets, rebuild and repeat QA/render when defects are visible.
   Verify preview page count equals PDF page count. Compare every Figure/Table against its original page and final slide, recording source page, panel/row coverage, header, last row and footnotes in the run review. Structural QA alone never establishes visual completeness.
9. Report actual saved files, slide count, spec/final QA, PDF render result, preview location and any omissions. Do not claim a file or pass until the corresponding command completed.

For note conventions, read `references/notes_style.md` when writing notes. For complex crops, read `references/article_level_crop_design.md`. The complete original image pipeline remains under `scripts/`.

## Safety and classroom constraints

- Use only user-authorized papers. Do not commit source PDFs, generated decks or identifiable patient data.
- The bundled demonstration article is synthetic; label its data fictional.
- Codex access and quota depend on account/product surface; setup cannot guarantee sufficient usage.
- Do not call AI image generation. Figures come from the supplied PDF.
- Microsoft PowerPoint is not required to create the PPTX; LibreOffice and Poppler are required for this repository's final rendered quality gate.
- A rendered pass does not prove clinical accuracy. The final presentation still requires human comparison with the source article.
