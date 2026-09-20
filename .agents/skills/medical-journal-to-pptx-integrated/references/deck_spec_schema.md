# Deck Spec Schema

The builder script (`scripts/build_deck.py`) consumes a single JSON file
that describes the whole deck. This document is the reference for its shape.

## Top-level structure

```json
{
  "meta": { ... },
  "slides": [ ... ]
}
```

### `meta` object

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `footer_label` | string | yes | Running footer text on content/figure slides. Format: `"<first author> et al — <journal> <year>  |  <short English topic>"` — English only. |
| `logo_path` | string | no | Absolute or relative path to a logo image. If omitted, the skill uses `assets/dr_leether_logo.png` by default. Shown at the upper-right on non-title/non-closing slides only. |
| `extraction_manifest` | string | yes when slides use source images | Path to the fresh machine-owned extraction manifest authenticated against the source PDF. |
| `article_asset_map` | string | yes when the paper has Figure/Table slides | Path to `medical-journal-article-asset-map/v1`. It binds semantic caption numbers to manifest assets; the build manifest fingerprints its bytes. |
| `bg_page` | string (hex) | no | Default `#061428` — near-black-navy full-slide background |
| `header_navy` | string (hex) | no | Default `#0F2847` — mid-navy header band, Part-divider subtitle card |
| `accent_bright` | string (hex) | no | Default `#A8C5E8` — light-blue accent: title text, Part N numeral, progress-bar fill, stripes on title/thanks |
| `accent_dim` | string (hex) | no | Default `#2A4566` — muted mid-blue: progress-bar background, hairline dividers |
| `text_primary` | string (hex) | no | Default `#FFFFFF` — body copy on dark |
| `text_secondary` | string (hex) | no | Default `#8FA8C8` — footer, citation, caption |
| `accent_dark` / `accent_blue` / `accent_teal` / `accent_light` / `accent_pale` | string (hex) | no | Compatible color aliases. Prefer the descriptive palette keys above. |

### `slides` array

Every element is a slide object with a `type` discriminator. Supported types:

- `title`
- `outline`
- `part`
- `content`
- `figure`
- `references`
- `thanks`

All slide objects accept an optional `notes` string that becomes the speaker
notes. Use `\n` for line breaks inside notes.

**Language rule (applies to every slide type below):** `title`, `items`,
`body`, `caption`, `subtitle`, `authors`, `citation`, `footer_label` are
English only. `notes` are Traditional Chinese with bolded English medical
terms. Never mix Chinese into slide-visible fields.

**Title source rule:** For content, figure, and table slides, `title` should
come from the paper's native heading/subheading hierarchy whenever possible.
Use exact paper headings for section-level slides and exact subheadings for
subsection-level slides. If several slides share one source heading, keep the
heading language stable and add only a short qualifier after a colon. Put
Figure/Table numbers, captions, and teaching summaries in `caption`, `body`,
or `notes` rather than inventing a new slide title style.

## Slide types

### `title`

```json
{
  "type": "title",
  "title": "Clinical Evaluation of a Synthetic Research Intervention",
  "authors": "Firstauthor A, Coauthor B, Coauthor C, et al.",
  "citation": "Journal Name 2026; 12(3):123-134",
  "notes": "各位好，今天我要為大家介紹的是..."
}
```

The `title` string may contain `\n` for an explicit line break.

### `outline`

```json
{
  "type": "outline",
  "title": "Outline",
  "items": [
    "1️⃣  Background — Clinical Problem (Slides 3-7)",
    "2️⃣  Methods — Study Design & Cohort (Slides 8-13)",
    "3️⃣  Results — Primary Findings (Slides 14-23)"
  ],
  "notes": "📋 本次簡報共分為九大部分..."
}
```

Items are displayed as-is (no re-numbering). Put the numbered emoji in the
string yourself.

### `part`

```json
{
  "type": "part",
  "number": 1,
  "title": "Background — Clinical Problem"
}
```

`number` is displayed as `"Part <N>"`. `title` is the section subtitle.
Part dividers use the same 1.00" top header band and bright-blue divider as
normal content slides, while keeping the large centered `PART N` and middle
section-title band unchanged. Part dividers should include short transition
notes.

### `content`

The workhorse slide. Body is a list of lines (string per line). Use bullet
glyphs (`•`, `→`, `✅`) inside the strings — the builder doesn't add them.
Write the body as visually segmented teaching text, not as a flat list. Use
short English labels, blank lines, arrows, bullets, and a final landing line
to make the structure obvious. Avoid 4-5 identical `•` bullets in a row.

Recommended body grammar:
- section labels: `Study:`, `Definition:`, `Criteria:`, `Results:`,
  `Clinical meaning:`, `Key principle:`
- `→` lines: logic, implication, causal flow, or next step
- `•` lines: parallel facts, criteria, or feature lists
- `✅` lines: take-home message or confirmed conclusion
- `⚠️` lines: cautions, exceptions, red flags
- blank strings: section breaks between visual blocks

```json
{
  "type": "content",
  "title": "Clinical Problem: Why It Matters",
  "body": [
    "Clinical burden:",
    "• The target condition affects diagnosis, treatment, or prognosis",
    "• Current practice has measurable uncertainty or variability",
    "",
    "Why this study is needed:",
    "→ Existing evidence leaves an actionable knowledge gap",
    "→ Imaging, pathology, clinical outcomes, or AI tools may improve decisions",
    "",
    "✅ The article tests whether the proposed approach improves clinical decision-making"
  ],
  "image": "figures/synthetic-overview.png",
  "notes": "📊 這張投影片說明本研究的臨床問題..."
}
```

Optional `image` attaches a right-side figure thumbnail next to the body
text. If omitted, the body uses the full width.

Empty strings in `body` insert a blank line.

Validation rule for generated specs: most content slides should contain at
least one blank-line break and should not have more than 3 consecutive lines
starting with the same marker. Evidence, definition, recommendation, and
takeaway slides should end with `✅`, `⚠️`, or a strong `→` implication line.

### `figure`

Dedicated figure or table slide. The image dominates, body text is empty or
minimal.

```json
{
  "type": "figure",
  "title": "Results: Representative Research Findings",
  "image": "figures/synthetic-multipanel-example.png",
  "source_asset_id": "figure:1",
  "panel_labels": ["A", "B", "C", "D", "E", "F"],
  "caption": "Figure 1. Fully synthetic examples of the article's key findings.",
  "notes": "【圖片說明 — Figure 1：完全合成的研究圖表示例】\n\n【A 圖】..."
}
```

`caption` is shown below the image in italic small text.
`source_asset_id` must match the semantic identifier in
`meta.article_asset_map` (`figure:N` or `table:N`). The caption/title number,
mapped manifest source, and recursive final-image provenance must agree; an
extraction filename such as `Figure_05.png` is not itself a semantic number.
`panel_labels` is optional for figures with no panel letters. For source labels
that are absent or safely removed from a separate, uniform exterior margin,
provide `panel_labels` and valid geometry, or omit them from the spec and use
the recomposer's native-label geometry plus `add_panel_labels.py`.

When original A/B/C/D letters overlap anatomy, a color scale, annotations, or
other image content, preserve those embedded letters; never erase, cover,
inpaint, or crop clinical pixels to obtain editable labels. In that case omit
`panel_labels` from the slide, and keep `source_label_policy: preserve`,
`native_labels: false`, and `embedded_labels: ["A", "B", ...]` in the image
sidecar. When a figure mixes embedded and exterior labels, use
`source_label_policy: mixed`, keep only the overlapping subset in
`embedded_labels`, and put only safely cropped/absent letters in
`native_label_values` and native-label geometry. Geometric source label/image
boxes override stale placement flags. Never duplicate the same letter in both
sets; native labels use the standard `#8FA8C8` blue-gray.
Speaker notes must reference the same visible labels with `【A 圖】`,
`【B 圖】`, etc.; QA reads either native or embedded label metadata.

### `references`

Renders a bullet list of reference strings. Keep to 5-10.

```json
{
  "type": "references",
  "title": "Key References",
  "items": [
    "1. Firstauthor A, et al. Journal Name 2026; 12(3):123-134.",
    "2. Priorstudy B, et al. Journal Name 2024; 10(2):45-56.",
    "3. Guidelines Group C. Journal Name 2023; 9(1):1-12.",
    "4. Validationgroup D, et al. Journal Name 2022; 8(4):200-210.",
    "5. Methodsconsortium E. Journal Name 2021; 7(2):80-92."
  ],
  "notes": "📖 本篇主要參考文獻..."
}
```

### `thanks`

```json
{
  "type": "thanks",
  "title": "Thank You",
  "citation": "Firstauthor et al — Journal Name 2026",
  "notes": "🙏 謝謝大家的聆聽！\n\n📧 通訊作者：**Corresponding Author Name**..."
}
```

`subtitle` is optional. By default, omit it. Do not use `Questions?`, `Q&A`,
or similar visible closing text unless the user explicitly requests it.

## Validation checklist

Before running the builder, check:

- [ ] Exactly one `title` slide and one `thanks` slide.
- [ ] At least one `part` slide.
- [ ] Content, figure, and table slide titles follow the paper's heading and
      subheading map unless a deliberate exception is documented.
- [ ] Labeled multi-panel figures use exactly one safe label system: editable
      native letters after safe exterior-margin removal, or preserved embedded
      source letters when removal would damage image content.
- [ ] Embedded-label figures omit slide `panel_labels` and record their labels
      in the image sidecar; no source image pixels are masked or inpainted.
- [ ] Figure crops retain a conservatively trimmed core without semantic loss,
      followed by the standard exact 16 px safety canvas in the verified image
      background; there is no additional uncontrolled page whitespace.
- [ ] No paper Figure number appears on more than one `figure` slide, and no
      slide `image` points at a raw per-panel crop (`*_panel_*` / `panel_a.png`);
      multi-panel figures are recomposed into a single image first.
- [ ] Every slide that declares `image` has a valid, decodable path. Every final
      raster (`.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.webp`, or `.bmp`) has
      a complete neighboring `.postprocess.json` sidecar and a recursive source
      chain to a trusted PDF-rendered/page/vector source. This applies equally
      to `content.image` and `figure.image`.
- [ ] Every `.emf` is a vector table created by the bundled `vector-table`
      helper and has a typed neighboring sidecar bound to the audited PDF hash,
      authenticated page/bbox, padding, canonical SVG, and exact EMF replay.
      Other non-raster slide-image formats are unsupported.
- [ ] Final figure and flowchart rasters record an exact 16 px safety canvas;
      final raster tables record an integer 8–24 px margin. Padded dimensions,
      unpadded dimensions, background, and actual file dimensions agree.
- [ ] Every `content` slide has a non-empty English `title` and a substantive
      structured `body`; every `figure` has a non-empty `title`, `image`, and
      `caption`.
- [ ] Every slide has substantive Traditional Chinese notes, starts with a scan
      marker/emoji, and content slides end with a takeaway marker. Figure notes
      describe every visible panel exactly once.
- [ ] The first slide is the only `title`, the last slide is the only `thanks`,
      and at least one `outline`, `part`, and `references` slide exists.
- [ ] `meta.footer_label` is non-empty English text in the documented format;
      the references slide contains 5–10 non-empty entries; the closing slide
      carries the article citation.
- [ ] Panel geometry entries are finite, ordered values in `[0, 1]`, match the
      number of native labels, and place each label inside the slide near the
      corresponding figure.
- [ ] Run prebuild QA, build, stamp native labels when required, and run final QA
      with the same canonical spec and selected style. Final QA verifies the
      embedded build manifest, spec hash, style, per-slide content, notes, logo,
      and image hashes; a deck built from another spec is never reusable merely
      because it has the same slide count.
