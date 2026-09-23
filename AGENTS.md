# Medical journal: one URL, one integrated workflow

For a repository URL or onboarding request, read `CODEX-START.md` and perform the authorized local setup. Preserve established user authorization; do not ask again when installation was requested.

- The only active skill is `.agents/skills/medical-journal-to-pptx-integrated/SKILL.md`. Read its current `VERSION` and full instructions before each presentation run.
- Use this project's `.venv` through `journal` / `journal.cmd`; never another project's or the global skill's runtime.
- Setup must actually pass managed-tool checks and the integrated synthetic full-deck QA and PDF/preview pipeline. Only then read the skill and prompt for the paper.
- After receiving a readable authorized PDF, proceed with the full 40–55-slide standard workflow unless the user requests nice; preserve English slides and Traditional Chinese notes.
- Preserve source maps, replayable panel/seam evidence, note quality, canonical rebuild comparison, native labels and QA receipts. Never bypass a failed gate.
- Final delivery requires current automatic QA, PDF/previews bound to the current PPTX, and recorded actual visual review of every page and source Figure/Table. Rendering alone is not visual approval.
- Save final PPTX/PDF in `outputs/` unless the user's workspace output rules specify another location. Keep intermediate data in `.skill-work/<run-id>/`.
- `tests/fixtures/classroom_v46` is historical regression data, never an alternative production workflow or skill.
- Standalone global installation is retained for existing users, not a student onboarding choice; never modify a global installation during project setup.
- Never overwrite unrelated files or publish papers, generated decks, patient data or credentials without explicit authorization. Synthetic demo data must remain labelled fictional.
