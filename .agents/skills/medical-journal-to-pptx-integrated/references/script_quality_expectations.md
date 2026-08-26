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
- [x] Embeds a deterministic build manifest (skill version, style, exact
      presentation canvas dimensions, canonical spec hash, slide content/notes
      hashes, image hashes, shape bounds/z-order,
      fills, lines, picture crops, run typography, stable shape OOXML, and slide
      visibility flags) and final QA rejects a missing or mismatched manifest.
      QA also performs a fresh spec/style rebuild, so rewriting the local
      manifest cannot authorize an arbitrary overlay. Managed
      `MJ_PANEL_LABEL_` shapes remain under a strict exact-label allow-list.
- [x] Both styles render every supported field, including `content.image` and
      the closing citation; QA resolves custom logos exactly as the builder does.

## Asset processing

- [x] `trim` and `labels` accept `--asset-type {figure,table,flowchart,unknown}`
      and `--intermediate`.
- [x] Final `figure`, `flowchart`, and `table` assets default to an exact 16 px safety canvas
      added after the unpadded core is trimmed; `--intermediate` defaults to 0.
- [x] `--asset-type table` defaults to `--margin 16` and rejects a final table
      output outside 8–24 px unless `--intermediate` is supplied (signalling
      a later padding/white-canvas step will restore the safety margin).
- [x] Sidecars for final raster assets record the resolved `margin`,
      `safety_margin_px`, `padding_background`, and padded/unpadded dimensions;
      table assets additionally record `asset_type: table` and
      `table_safety_margin_px`.
- [x] Decoded final rasters must be opaque, contain non-background core content,
      and physically contain all four declared padding bands. Case-insensitive
      RGB metadata and bounded JPEG/WebP edge compression are handled without
      trusting metadata alone.
- [x] `audit-final` reads every supported raster suffix in the deck spec and
      validates provenance fields, final/intermediate state, asset type, safety
      margin, padding background, size arithmetic, actual decoded size, and the
      physical pixels in all four declared safety bands. EMF tables do not use
      raster safety fields, but require a typed vector sidecar and exact
      authenticated PDF→SVG→EMF replay.
- [x] `audit-final` validates multi-panel figure slides: labels present and
      panel geometry present (or a documented exception). Split-table width
      equality check retained.
- [x] `recompose_panels_banded.py` automatically compares every valid column
      count against the actual slide box, panel proportions, gutters, and
      native-label bands. It maximizes the smallest displayed panel and keeps
      source reading order; explicit `--cols` remains a manual override.
- [x] Banded composites default to an exact 16 px outer safety canvas. Candidate
      fit, fixed-size label bands, and native-label anchors all use the padded
      dimensions; `--safety-margin-px 0` remains an explicit compatibility
      override for intermediates but cannot pass final-asset QA.
- [x] Embedded source labels remain untouched and suppress both native-label
      geometry and label bands. Exterior labels are cropped only after their
      surrounding margin is proven uniform; unsafe margins preserve the source.
- [x] Missing placement metadata in `auto` is preserved conservatively. Label
      count must equal panel count; a run without replacement labels never crops
      a source label. Native label geometry must be finite and in `[0,1]`, and
      repeat stamping is idempotent.
- [x] Raster helpers reject input/output path identity. The legacy `labels`
      command requires a positive, visually verified `--cut-bottom-px` and never
      guesses the label boundary.
- [x] Exact-source panel crops containing a solid corner overwrite are rejected
      instead of silently covering anatomy, annotations, or clinical overlays.
- [x] White, gray, and anti-aliased achromatic edge seams are trimmed by at most
      four pixels per side by default for both standalone raster figures and
      recomposed panels. A uniform dark clinical canvas stops the trim sequence,
      so a preceding one-pixel PDF object-boundary hairline is removed instead
      of being retained by the safety cap; dark borders facing brighter content,
      colored scales, bright edge-touching content, tables, flowcharts, and
      thicker ambiguous light regions are preserved.
- [x] A verified image-content box is applied before heuristic rim cleanup, so
      a PDF crop frame does not combine with the raster's own antialiased edge
      and exceed the four-pixel safety budget.
- [x] Non-white gray seams require one-way luminance contrast against the next
      inward line, preventing uniform gray MRI background from exhausting the
      rim budget and indirectly preserving a preceding white seam.
- [x] Clinical-figure `bg-aware auto` preserves the complete dark/gray source
      canvas. Explicit broad refinement is rejected when it would exceed the
      bounded edge budget on a dark or coloured acquisition background.
- [x] Exact crops sharing an audited source automatically reconcile a rough row
      boundary only when it cuts a verified boxed embedded label; independent
      overlap groups remain separate, linked panels share one corrected seam,
      clinical color scales block unsafe shifts, and source/effective crop boxes
      plus bounded shift depths remain auditable.
- [x] Recomposed-figure sidecars preserve every recursive `source_inputs` path
      and record the selected grid, reproducible candidate measurements, source
      label policy, overwritten-pixel count, bounded row-seam adjustments,
      per-side edge-trim depths, safety margin, background, and padded/unpadded
      dimensions.
- [x] `trim`, `labels`, `same-width`, `split-table`, `crop-vector-figure`,
      auto-split composites, aligned composites, and banded composites record complete replay
      parameters. Final QA regenerates their output and requires exact decoded
      pixels; unknown or non-replayable final commands fail closed.

## Speaker-note validation

- [x] `postprocess_assets.py notes-audit --spec <spec>` counts notes-bearing
      slides and note emoji.
- [x] Fails per slide when notes are non-string, empty, non-substantive,
      non-Traditional Chinese, repetitive glyph/short-phrase padding, missing
      scan markers, or missing a latter-half content takeaway.
- [x] Fails when the same normalized speaker note is reused on more than two
      slides; punctuation, case, and page/slide/teaching-ordinal variations do
      not make otherwise repeated boilerplate unique, while clinical numeric
      values remain significant.
- [x] Fails when more than two notes form a ≥97%-similar normalized template
      group, so inserting one meaningless character per slide cannot evade the
      reuse gate. Differing HR, CI, p-value, percentage, and sample-size values
      remain substantive numeric distinctions.
- [x] Fails if figure/table notes reference panel letters not present in either
      the slide's native `panel_labels` or the image sidecar's embedded labels.
- [x] Warns on literal `**` markup left in notes (the builder converts
      `**...**` to real bold, but stray markers usually signal a copy error).

## Release and regression expectations

- [x] Extraction manifests bind the source PDF and every page/image/figure/table
      raster by SHA-256. QA validates strict field types, extraction-root paths,
      complete page numbering, fresh PDF page renders, in-page crop geometry,
      and byte-identical unique aliases before creating a trusted-terminal set.
- [x] Extraction writes only to a new or empty directory and never deletes or
      overwrites files claimed by mutable prior manifests.
- [x] Malformed manifests return structured failures. Direct-PDF flowcharts
      require exact deterministic `crop-vector-figure` page/bbox/DPI pixel
      replay (including stripped-frame margins); table and
      flowchart provenance does not bypass intermediate-polarity comparison.
- [x] Vector-table EMFs require the audited PDF hash, authenticated page,
      requested/effective bbox and padding, canonical SVG hash, valid EMF
      header, and byte-exact regeneration with a runtime-discovered LibreOffice
      binary. Sidecar-provided executable paths are never run.
- [x] The canonical package fingerprint covers slide transitions/timing,
      masters, layouts, themes, relationships, media, and embedded objects;
      the standard custom-properties manifest remains LibreOffice-renderable,
      with one exact relationship target and content-type override.

- Run all checks using fully synthetic, specialty-neutral figures and data.
- Verify both visual styles with complete 40–55-slide bilingual presentations.
- Exercise image inversion, recursive source provenance, native panel labels,
  preserved embedded labels, non-destructive crop integrity, bounded edge
  cleanup, figure uniqueness, table safety margins, split-table sizing, and
  vector tables.
- Keep authorized papers, patient data, generated decks, intermediate artifacts,
  credentials, and personal filesystem paths outside public release archives.
