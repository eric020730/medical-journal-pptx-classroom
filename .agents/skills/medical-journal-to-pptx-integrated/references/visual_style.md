# Visual Style Reference

Exact specifications for the bilingual medical-journal deck. The builder script
(`scripts/build_deck.py`) uses these constants; this document explains why they
are what they are so a future revision can stay consistent.

**Design direction:** dark academic / deep-navy — full-slide deep navy
background, mid-navy header band, light-blue accents. Feels like a formal
conference or medical-school grand-rounds deck shown in a dimmed lecture hall.
White medical figures pop off the dark page like clean cards.

## Canvas

- **Slide size**: 13.333" × 7.5" (16:9 widescreen; 12,192,000 × 6,858,000 EMUs).
- **Coordinate origin**: top-left.

## Color palette (dark academic — near-black-navy)

| Name | Hex | Where it's used |
|------|-----|-----------------|
| `bg_page` | `#061428` | Near-black-navy full-slide background on every slide type |
| `header_navy` | `#0F2847` | Mid-navy header band on content slides, Part-divider subtitle card, decorative bands on title/thanks |
| `accent_bright` | `#A8C5E8` | Light-blue accent — title-slide title, Part N numeral, full progress/divider bars, horizontal stripes on title/thanks |
| `accent_dim` | `#2A4566` | Muted mid-blue — hairline dividers and compatible accents; do not use as progress-bar background |
| `text_primary` | `#FFFFFF` | Primary body copy on dark bg |
| `text_secondary` | `#8FA8C8` | Footer citation, caption, page number (muted blue-gray) |
| `text_on_header` | `#FFFFFF` | Title text sitting on the mid-navy header band |
| `caption` | `#8FA8C8` | Figure caption (same muted blue-gray as secondary) |
| `hairline` | `#2A4566` | Thin divider line above footer |

Compatible alias keys accepted by `meta` (prefer the descriptive keys above):
- `accent_dark` / `bg_dark` → `bg_page`
- `accent_blue` / `accent_light` → `accent_bright`
- `accent_teal` / `accent_pale` → `accent_dim`
- `header_bg` → `header_navy`
- `body_text` → `text_primary`

## Slide types and their shape boxes

All positions in inches. Format: `(left, top, width, height)`.

### Title slide

```
Rectangle (full bg)         (0.00, 0.00, 13.33, 7.50)  fill bg_page
Rectangle (top header band) (0.00, 0.00, 13.33, 1.10)  fill header_navy
Rectangle (top accent line) (0.00, 1.10, 13.33, 0.06)  fill accent_bright
Rectangle (bot accent line) (0.00, 6.34, 13.33, 0.06)  fill accent_bright
Rectangle (bot header band) (0.00, 6.40, 13.33, 1.10)  fill header_navy
TextBox (title)             (0.80, 2.00, 11.70, 2.20)  40pt bold accent_bright, center
TextBox (authors)           (0.50, 4.40, 12.30, 0.60)  20pt text_primary, center
TextBox (citation)          (0.50, 5.05, 12.30, 0.60)  16pt text_secondary italic, center
```

The title is in bright light-blue, authors in white, citation in muted
blue-gray. The two navy bands top and bottom frame the slide like a formal
conference poster.

### Outline slide

Same header band as a normal content slide, same footer, same progress bar
(usually empty since the outline comes before any Part divider). Body has
numbered items with emoji markers (1️⃣2️⃣3️⃣…) in English only.

Outline body: 24pt `text_primary` (white). Outline title: 28pt white on the
mid-navy header band (same as content header).

### Part divider slide

```
Rectangle (full bg)               (0.00, 0.00, 13.33, 7.50)  fill bg_page
Rectangle (top header band)       (0.00, 0.00, 13.33, 1.00)  fill header_navy
Rectangle (top accent stripe)     (0.00, 1.00, 13.33, 0.10)  fill accent_bright
Picture (logo)                    (12.47, 0.225, 0.61, 0.55) symbol-only logo, top-right
TextBox ("PART N")                (0.50, 1.60, 12.30, 2.20)  88pt bold accent_bright, center
Rectangle (section subtitle band) (0.00, 4.40, 13.33, 1.10)  fill header_navy
TextBox (section title)           (0.50, 4.55, 12.30, 0.80)  30pt text_primary, center
Rectangle (bottom hairline)       (0.00, 7.48, 13.33, 0.02)  fill accent_bright
```

Part dividers are a pure visual beat. Their top header band intentionally
matches normal content slides (1.00" high) while the rest of the divider
layout remains unchanged. No "Section N of M" label is shown; the progress bar
in the top stripe doubles as the only section counter the audience needs.

### Content slide

```
Rectangle (full bg)            (0.00, 0.00, 13.33, 7.50)  fill bg_page
Rectangle (mid-navy header)    (0.00, 0.00, 13.33, 1.00)  fill header_navy  — taller: 1.00" for editorial weight
Rectangle (progress bar)       (0.00, 1.00, 13.33, 0.10)  fill accent_bright
Picture (logo)                 (12.47, 0.225, 0.61, 0.55) symbol-only logo, top-right
TextBox (title)                LEFT-aligned — see below
TextBox (body)                 (0.55, 1.30, 12.25, 5.70)  22pt text_primary
Rectangle (footer hairline)    (0.00, 7.05, 13.33, 0.01)  fill hairline
TextBox (footer citation)      (0.40, 7.12, 10.50, 0.32)  11pt text_secondary, left
TextBox (footer page number)   (11.40, 7.12, 1.53, 0.32)  11pt text_secondary, right — format `"{N:02d}"` only (zero-padded current page, no slash, no total)
```

Title placement depends on whether a logo is present:
- With logo:    TextBox at `(0.55, 0.12, 11.55, 0.78)`, 28pt bold white, **left-aligned**, middle-anchored.
- Without logo: TextBox at `(0.55, 0.12, 12.25, 0.78)`, 28pt bold white, **left-aligned**, middle-anchored.

If the slide has an image on the right (a content+figure hybrid), the body
text box shrinks to `(0.55, 1.30, 7.60, 5.70)` and the image takes
`(8.35, 1.45, 4.70, 5.30)` with aspect ratio preserved.

Progress bar rules:
- Always draw one full-width bright-blue (`accent_bright`) stripe.
- Do not draw a darker inactive background segment.
- The bar is now a clean section divider/accent line rather than a two-tone
  progress meter.

### Figure slide (dedicated)

Same frame as a content slide (navy header + progress bar + footer) but body
area hosts the image + caption:

```
Picture (figure image)         (0.60, 1.35, 12.10, 4.90)  preserve aspect ratio, center
TextBox (caption)              (0.60, 6.35, 12.10, 0.60)  13pt italic caption color, center
```

If the caption is long (>2 lines), shrink the image height to 4.5" and let
the caption occupy two lines. Most medical figures have white backgrounds,
which read as bright cards on the deep-navy page — a deliberate effect.

### References slide

Same frame as content slide. Body uses 15pt `text_primary` with space-after
on each paragraph for readability.

### Thank-you slide

Mirrors the title slide — two mid-navy bands top/bottom, two bright accent
lines, "Thank You" in bright light-blue, and citation in muted secondary.
No logo is shown on the final Thank-You slide by default. 60pt title. The
subtitle area is optional. The default final slide should not show
"Questions?", "Q&A", or similar visible closing text unless the user
explicitly requests it.

## Typography

- **Primary font**: Calibri (everywhere). The python-pptx default usually
  renders as Calibri on both Windows and Mac. Do not specify a custom font
  unless the user asks, to avoid missing-font substitution.
- **Sizes**:
  - Title-slide title: 40pt
  - Thank-You title: 60pt
  - Part N numeral: 88pt
  - Part section subtitle: 30pt
  - Content/outline/figure/references title (on header): 28pt
  - Outline items: 24pt
  - Body: 22pt
  - References body: 15pt
  - Figure caption: 13pt italic
  - Footer citation: 11pt
  - Footer page number: 11pt
- **Bold**: titles, Part N numeral, and the first token of numbered bullets
  only. Do not bold body text — emphasis inside notes is done with emojis,
  not bold on the slide.
- **Body rhythm**: slide-visible body text should have visible hierarchy.
  Prefer short English block labels plus marker lines over flat bullets.
  Good markers:
  - `→` for flow, implication, mechanism, or management direction
  - `•` for parallel criteria or facts
  - `✅` for a confirmed take-home conclusion
  - `⚠️` for caution, red flags, or exceptions
  - blank lines between 2-3 blocks
  Avoid content slides made only of plain `•` bullets; they read like an
  exported outline and match the weaker V3 pattern.

## Footer layout

The running footer on content/figure/outline/references slides has two
pieces, separated horizontally:

```
Left  (11pt, left-aligned):    <FirstAuthor> et al — <Journal> <Year>  |  <Short English topic>
Right (11pt, right-aligned):   <slide_num>  — zero-padded 2-digit, no slash, no total
```

Examples for the footer label:
- `Firstauthor et al — Journal Name 2026  |  Imaging Biomarkers in Clinical Practice`
- `Groupname et al — Journal Name 2025  |  Clinical Research Quality Monitoring`

Use an em dash (`—`) between author and journal, two spaces + pipe + two
spaces before the topic. The topic should be short — roughly 4-8 words.

Page number format: zero-padded 2-digit only (`04`, `17`, `42`). No slash,
no total. This is an understated editorial convention — the audience only
needs the page position, not the deck size. Title slide and Thank-you slide
do NOT show the footer or page number — they're the "cover" and "back
cover" of the deck.
