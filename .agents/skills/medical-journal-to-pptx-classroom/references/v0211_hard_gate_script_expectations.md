# Script-Level Hard Gates (Implemented)

Status: **implemented in v0.2.11.1** (2026-06-12). The rules below are now
enforced in the canonical scripts, not merely documented. This file is kept as
the design record and as a regression checklist for future versions — every
item must remain true.

## build_deck.py — implemented

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

## postprocess_assets.py — implemented

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

## notes QA — implemented

- [x] `postprocess_assets.py notes-audit --spec <spec>` counts notes-bearing
      slides and note emoji.
- [x] Fails if slides have notes but the total note emoji count is zero.
- [x] Fails if figure/table notes reference panel letters not present in the
      slide's `panel_labels`.
- [x] Warns on literal `**` markup left in notes (the builder converts
      `**...**` to real bold, but stray markers usually signal a copy error).

## Rationale

The BMC v0.2.11 run exposed four gaps, now closed in code:
1. live plain skill could be overwritten by proposal prose rather than full
   v0.2.11 content;
2. speaker notes could be complete but lose the v0.2.5 lead-emoji/bullet
   scaffold — now catchable with `notes-audit`;
3. v0.2.8 tight figure trimming leaked into table final assets as
   `trim --margin 0` — now blocked at write time and at `audit-final`;
4. generated `meta.logo_path` missed the workspace root, and the builder
   silently disabled the logo instead of falling back — now warns and falls
   back to the bundled logo.
