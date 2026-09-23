# Rendered delivery verification

Full delivery requires **current automatic QA, a current complete render, and
explicit approved visual review of every preview page**. Successful rendering is
not visual review. Structural QA and rendering cannot establish clinical fidelity.
Inspect the actual full-size previews and source material before approving.

## CLI

Repository workflows explicitly select the project Python before global runtime
selection. `journal` delegates to the integrated workflow. Direct invocation:

```sh
python .agents/skills/medical-journal-to-pptx-integrated/scripts/run.py \
  --runtime-python .venv/bin/python qa deck.pptx --spec deck_spec.json --style standard --json
```

On Windows use `.venv/Scripts/python.exe`. Installed standalone `run.py` retains
its explicit environment override, managed global runtime, and ready current
Python fallback. Repository managed LibreOffice/Poppler under `.bootstrap` take
priority over PATH. Windows uses `soffice.com` when available. Explicit project
root and binary overrides are available through
`MEDICAL_JOURNAL_PPTX_PROJECT_ROOT`, `MEDICAL_JOURNAL_PPTX_SOFFICE`, and
`MEDICAL_JOURNAL_PPTX_PDFTOPPM`; project managed binaries still take priority.

Commands below are arguments to the selected integrated runner:

```sh
qa deck.pptx --spec deck_spec.json --mode full --style standard --json
render deck.pptx --preview --json
# Existing sibling PDFs require explicit --overwrite.
visual-review deck.pptx --evidence review-evidence.json --json
qa-status deck.pptx --spec deck_spec.json --style standard --require-delivery --json
```

Use the actual `standard` or `nice` style consistently. `render --preview` returns
`pptx`, `pdf`, `pdf_pages`, `preview_dir`, `contact_sheet`, `preview_pages`,
`render_receipt`, and `render_receipt_sha256`. It explicitly returns
`render_success: true`, `visual_review: false`, and `delivery_ready: false`.
Without `--preview`, PDF rendering remains available but cannot satisfy delivery.

## Explicit visual review evidence

Create evidence only after inspecting the exact rendered snapshot. Copy its
`render_receipt_sha256` from the render result (or the current `qa-status.render`
object). The exact required JSON fields are:

```json
{
  "render_receipt_sha256": "<64-character SHA-256 of the inspected .render.json receipt>",
  "reviewer": "Reviewer identifier",
  "reviewed_pages": [1, 2, 3],
  "findings": "Describe the actual visual checks, findings, and resolved issues.",
  "approved": true
}
```

The example page list is illustrative: supply every page of the actual 40–55-slide
deck exactly once, using one-based integers. Both reviewer and findings must be
nonempty strings; approved must be a JSON boolean. `false` records rejection and
returns a nonzero exit status. Do not generate automatic approval or recycle old
findings. The command binds the evidence to the exact render-receipt digest, which
in turn binds the PPTX, PDF, all previews, contact sheet, counts, and validator
code. Rerendering invalidates old review even when the images look unchanged.

## Receipts and status

- `deck.pptx.qa.json`: existing v4.4 automatic QA receipt, binding deck/spec,
  validator code, version, mode, and style. All existing gates remain required.
- `deck.pptx.render.json`: unsigned render receipt with SHA-256 bindings, PDF
  page count, exact preview inventory/count, and contact sheet binding. PDF
  page count must match the PPTX slide count; previews must cover all pages.
- `deck.pptx.visual-review.json`: separate unsigned explicit review record with
  the submitted evidence and its source-file digest. Evidence is embedded;
  the input evidence file need not remain beside the deliverables.

Plain `qa-status` keeps the structural `ok`/exit behavior when no render receipt
exists, and exposes `automatic_qa`, `render`, `visual_review`, `delivery_ready`,
and `requires_full_delivery` separately. **Whenever a render receipt is present,
changed, missing, malformed, or failed rendered artifacts make plain status fail.**
A current render without approved review can still have structural `ok: true`,
but always has `delivery_ready: false`. `requires_full_qa` retains its original
automatic-QA meaning; it does not imply that full delivery is ready.

`qa-status --require-delivery` exits zero only when all three stages are current.
Use that command as the mandatory final delivery gate. Re-run automatic QA after
spec/deck/validator changes, rerender when needed, and inspect the new rendered
pages before submitting new evidence. A failed or interrupted render/review retry
invalidates its previous pass. Declining to overwrite an existing PDF does not
invalidate it. The receipts detect accidental changes; they are local unsigned
records, not cryptographic signatures or independent proof of human inspection.

`smoke-test --render --keep --style standard|nice --json` creates a full synthetic
deck, automatic QA receipt, PDF, every preview, and render receipt. Its `render`
object has the same render contract. It never approves visual review; readiness
smokes must not claim full delivery approval. Without `--keep`, the temporary
artifacts are removed after the test, including any paths in its render report.
