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

- [x] `trim` and `labels` accept `--asset-type {clinical-image,figure,table,flowchart,unknown}`
      and `--intermediate`.
- [x] Final `clinical-image` assets require a 0 px outer raster canvas. Final
      nonclinical `figure` and `flowchart` assets require exactly 16 px;
      `--intermediate` defaults to 0.
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
- [x] Banded composites default by asset type: `clinical-image` requires 0 px
      and `figure` requires 16 px. Candidate fit, fixed-size label bands, and
      native-label anchors use those exact final dimensions; mismatched explicit
      margins fail. Every regular grid row absorbs integer resize rounding in
      its final panel so a 0 px clinical canvas exposes no right-edge background strip.
- [x] A reviewed `left-span-2x2` template arranges exactly five preserved-label
      panels with panel 1 spanning both rows and panels 2–5 in a 2×2 block.
      Native label bands and `--cols` are rejected for this irregular template.
- [x] A reviewed `right-span-2x2` template preserves semantic A/B/C/D/E order,
      keeps panel 3 as the full-height right span, and leaves panels 1–2/4–5 in
      their upper/lower 2×2 source topology. Every resize preserves aspect ratio.
- [x] Embedded source labels remain untouched and suppress both native-label
      geometry and label bands. Exterior labels are cropped only after their
      surrounding margin is proven uniform; unsafe margins preserve the source.
- [x] Missing placement metadata in `auto` is preserved conservatively. Label
      count must equal panel count; a run without replacement labels never crops
      a source label. Native label geometry must be finite and in `[0,1]`, and
      repeat stamping is idempotent.
- [x] `panel-crop --label-placement absent` is the only supported way to claim
      a reviewed missing source label. It forbids label/image boxes and records
      the full decoded panel bbox plus RGB SHA-256; recomposition rejects stale
      or tampered evidence. Final sidecars keep disjoint embedded,
      cropped-exterior, and verified-absent label groups, with native labels
      equal to the latter two groups.
- [x] Raster helpers reject input/output path identity. The legacy `labels`
      command requires a positive, visually verified `--cut-bottom-px` and never
      guesses the label boundary.
- [x] Exact-source panel crops containing a solid corner overwrite are rejected
      instead of silently covering anatomy, annotations, or clinical overlays.
- [x] `panel-crop` creates only exact, unpadded intermediate rectangles from an
      authenticated raster, records typed source/output sizes and label/image
      geometry, and is replayed pixel-for-pixel by final QA. Hand-authored or
      unknown panel-crop commands remain fail-closed.
- [x] `panel-crop` accepts repeatable paired seam reports and edges, stores an
      edge-keyed multi-seam evidence map, and can require every declared
      interior left/right/top/bottom boundary. QA independently replays each
      report, native-resolution overlay hash, band, axis, and crop coordinate;
      duplicate, missing, cross-row, or cross-column evidence fails.
- [x] Clinical banded recomposition groups exact panel crops by authenticated
      source and infers nearest overlapping right/below adjacencies in source
      coordinates. Both sides of every inferred adjacency must occur in
      `required_seam_edges` and `seam_reviews`; legacy sidecars that omit the
      declarations fail. The composite records a deterministic
      `medical-journal-source-seam-topology/v1` graph, and final QA regenerates
      and compares it so missing or stale topology metadata cannot pass.
- [x] Every authenticated required seam is locked before embedded-label frame
      reconciliation, so a false label-frame detection cannot expand an upper
      clinical panel into its lower neighbor or move either reviewed edge.
- [x] White, gray, and anti-aliased achromatic edge seams are trimmed by at most
      four pixels per side by default for both standalone raster figures and
      recomposed panels. A uniform dark clinical canvas stops the trim sequence,
      so a preceding one-pixel PDF object-boundary hairline is removed instead
      of being retained by the safety cap; dark borders facing brighter content,
      colored scales, bright edge-touching content, tables, flowcharts, and
      thicker ambiguous light regions are preserved.
- [x] `panel-crop` can record a reviewed 0–12 px `TOP BOTTOM LEFT RIGHT`
      edge-trim declaration plus a typed audit reason without changing the
      exact intermediate crop. The banded recomposer applies it only after
      verified image-box/exterior-label removal, rejects it for preserved
      embedded labels, and records verified, heuristic, and total depths
      separately. The four-pixel automatic default is unchanged.
- [x] Banded composites report a QA warning when a 5–12 px full-edge near-white
      band survives the heuristic cap and terminates in distinctly darker
      content. Broad white-background panels do not trigger this warning.
- [x] When `--no-trim` disables bounded cleanup, the same review includes
      1–4 px full-edge near-white bands and QA blocks the asset until its crop
      box or audited trim removes the residual PDF frame.
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
- [x] `trim`, `labels`, `panel-crop`, `same-width`, `split-table`, `crop-vector-figure`,
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
- [x] `article_asset_map.py` binds semantic `figure:N`/`table:N` identifiers to
      authenticated manifest files using PDF/manifest hashes, replayed caption
      bbox/text hashes, and deterministic caption-neighbor geometry. Deck slides
      carry `source_asset_id`; QA requires recursive final provenance to end at
      the mapped raster, and the build manifest fingerprints the map file.
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
  preserved embedded labels, verified-absent evidence, non-destructive crop
  integrity, multi-edge/non-shared seam evidence, source gutters, row-specific
  boundaries, spanning source topology, bounded edge cleanup, clinical 0 px/nonclinical 16 px canvases,
  caption-to-source mapping, figure uniqueness, table safety margins,
  split-table sizing, and vector tables.
- Keep authorized papers, patient data, generated decks, intermediate artifacts,
  credentials, and personal filesystem paths outside public release archives.
