# Script-Level Quality Requirements

The bundled scripts enforce these requirements mechanically. Preserve every
invariant when modifying extraction, asset processing, deck building, or QA.

## Deck building

- [x] Resolves the default logo from the skill directory:
      `assets/dr_leether_logo.png`.
- [x] If `meta.logo_path` is supplied but does not exist, the builder WARNS and
      falls back to the bundled default logo instead of setting
      `logo_path = None`.
- [x] Prints a QA-friendly log line showing the logo path actually used (or a
      warning when no logo is available).
- [x] Rejects multi-label figure slides (>1 `panel_labels`) when panel geometry
      is missing. Requires `panel_label_x_fracs` (one per label) or
      `panel_boxes`; otherwise raises a build error. Labels are no longer
      silently distributed across one composite image. Override with
      `panel_geometry_exception: true`.
- [x] Keeps title and thank-you slides logo-free by default; shows the logo on
      outline, part, content, figure/table, and references slides.

## Asset processing

- [x] `trim` and `labels` accept `--asset-type {figure,table,flowchart,unknown}`
      and `--intermediate`.
- [x] `--asset-type table` defaults to `--margin 12` and rejects a final table
      output with `margin < 8` unless `--intermediate` is supplied (signalling
      a later padding/white-canvas step will restore the safety margin).
- [x] Sidecars for table assets record `asset_type: table`, the resolved
      `margin`, and `table_safety_margin_px`.
- [x] `audit-final` reads the deck spec and fails if a final table sidecar has
      `command in {trim, labels}` and `margin < 8` without a documented
      exception (`--allow-table-margin <names>` or a RUN_MANIFEST mention).
- [x] `audit-final` validates multi-panel figure slides: labels present and
      panel geometry present (or a documented exception). Split-table width
      equality check retained.
- [x] `recompose_panels_banded.py` automatically compares every valid column
      count against the actual slide box, panel proportions, gutters, and
      native-label bands. It maximizes the smallest displayed panel and keeps
      source reading order; explicit `--cols` remains a manual override.
- [x] Embedded source labels remain untouched and suppress both native-label
      geometry and label bands. Exterior labels are cropped only after their
      surrounding margin is proven uniform; unsafe margins preserve the source.
- [x] Exact-source panel crops containing a solid corner overwrite are rejected
      instead of silently covering anatomy, annotations, or clinical overlays.
- [x] White, gray, and anti-aliased achromatic edge seams are trimmed by at most
      four pixels per side by default for both standalone raster figures and
      recomposed panels. A uniform dark clinical canvas stops the trim sequence,
      so a preceding one-pixel PDF object-boundary hairline is removed instead
      of being retained by the safety cap; dark borders facing brighter content,
      colored scales, bright edge-touching content, tables, flowcharts, and
      thicker ambiguous light regions are preserved.
- [x] Exact crops sharing an audited source automatically reconcile a rough row
      boundary only when it cuts a verified boxed embedded label; independent
      overlap groups remain separate, linked panels share one corrected seam,
      clinical color scales block unsafe shifts, and source/effective crop boxes
      plus bounded shift depths remain auditable.
- [x] Recomposed-figure sidecars preserve every recursive `source_inputs` path
      and record the selected grid, reproducible candidate measurements, source
      label policy, overwritten-pixel count, bounded row-seam adjustments,
      and per-side edge-trim depths.

## Speaker-note validation

- [x] `postprocess_assets.py notes-audit --spec <spec>` counts notes-bearing
      slides and note emoji.
- [x] Fails if slides have notes but the total note emoji count is zero.
- [x] Fails if figure/table notes reference panel letters not present in either
      the slide's native `panel_labels` or the image sidecar's embedded labels.
- [x] Warns on literal `**` markup left in notes (the builder converts
      `**...**` to real bold, but stray markers usually signal a copy error).

## Release and regression expectations

- Run all checks using fully synthetic, specialty-neutral figures and data.
- Verify both visual styles with complete 40–55-slide bilingual presentations.
- Exercise image inversion, recursive source provenance, native panel labels,
  preserved embedded labels, non-destructive crop integrity, bounded edge
  cleanup, figure uniqueness, table safety margins, split-table sizing, and
  vector tables.
- Keep authorized papers, patient data, generated decks, intermediate artifacts,
  credentials, and personal filesystem paths outside public release archives.
