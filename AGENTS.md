# Single-workflow medical-journal project

For a repository URL or beginner onboarding request, read `CODEX-START.md` first and perform the authorized Local setup. Do not return a manual installation assignment.

- The sole skill is `.agents/skills/medical-journal-to-pptx-classroom/SKILL.md`.
- Use only `setup-codex.sh` or `setup-codex.ps1`; there is no global installer.
- Resolve paths from the root containing `.classroom-project.json`.
- Use this project's `.venv` through `journal` / `journal.cmd`.
- Proceed only after the current receipt is `FULL_QA_READY_SKILL_PENDING`.
- The readiness gate must include LibreOffice, Poppler and a successful synthetic `PPTX → PDF → preview` render; there is no PPTX-only success mode.
- Actually read the complete skill, then request the user's PDF.
- With a readable PDF, report title and page count, execute the full 40–55-slide workflow, run spec/final QA, render to PDF and inspect previews.
- Save final PPTX/PDF in `outputs/`; keep specs, assets and QA in `.skill-work/<run-id>/`.
- Never weaken QA, invent clinical findings, or publish papers, decks, patient information or credentials.
