# Portable medical-journal classroom project

This repository is a standalone teaching project. Resolve every path from the
repository root containing `.classroom-project.json`; never use a developer's
username, Desktop path, Google Drive path, or an environment from another copy.

- Prefer the repository skill `$medical-journal-to-pptx-classroom`.
- The separate `$medical-journal-to-pptx-integrated` skill is self-contained;
  install it globally with `install-global.py` when use outside this project is
  requested. Preserve the repository classroom workflow and existing skills.
- Use the repository `.venv` through `./journal` on macOS/Linux or
  `journal.cmd` on Windows. Run `journal doctor` before a presentation task.
- Save final `.pptx` and optional `.pdf` files directly in `outputs/`.
- Keep extraction assets, manifests, deck specs, QA reports, and previews in
  `.skill-work/<run-id>/`; never publish these files.
- `full` is the only presentation mode and means the complete 40-55 slide
  workflow. Preserve English slide text and Traditional Chinese notes.
- Do not silently overwrite an existing presentation.
- Treat student papers and clinical material as private. Never upload, commit,
  publish, or share a PDF, patient data, generated deck, or credentials unless
  the user explicitly asks for that particular action.
- The classroom demo is synthetic. Its results are fictional and must never be
  represented as clinical evidence.
