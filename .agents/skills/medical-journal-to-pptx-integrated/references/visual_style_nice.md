# Visual Style Reference — nice builder

Widescreen 16:9 (13.333 × 7.5 in). Dark-academic palette (fixed in
`scripts/build_deck.py`):

| Role | Hex |
|------|-----|
| Page background | `#061428` (near-black navy) |
| Header band / section-divider page | `#102444` (mid navy) |
| Divider rule + accent (kicker, number) | `#5BA9E6` (light blue) |
| Title text | `#EAF2FC` |
| Body text | `#D8E4F2` |
| Footer / caption / subtitle (muted) | `#8FA8C8` |
| Figure/table card | `#FFFFFF` |

Layout:

- **Header** (content/figure slides): 1.00" `#102444` band; optional small
  uppercase KICKER in accent above a bold title; 3 pt `#5BA9E6` divider under
  the band. Logo (0.62") upper-right.
- **Title slide**: two full-width divider rules (≈2.05" and 5.0"); centered
  kicker, large centered title, authors, citation. No logo/footer.
- **Section divider**: full `#102444` page, large accent number (e.g. `01`),
  bold section title, optional subtitle, divider rule at ≈3.05". Logo + footer.
- **Content**: structured teaching body from 1.35" downward (12.0" wide); 18 pt
  default; `• Label:` bold prefix, `→` logic, single `✅` take-home; `**…**` bold.
- **Figure/Table**: image fit (aspect-preserved) into box (0.60", 1.25",
  12.13", 4.95"); optional white card (`card: true`); italic-style caption at
  ≈6.35"; footer.
- **Footer**: `footer_label` left at 7.05"; zero-padded page number right.
- **Thanks**: full `#102444` page, big centered title + subtitle, divider rule.

Native panel labels (added post-build) use the figure box 12.13 × 4.95 in for
their on-screen-size/gap calibration — pass these as `--slide-box-w-in` /
`--slide-box-h-in` to `recompose_panels_banded.py`.
