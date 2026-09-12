# Single-workflow medical-journal project

For a repository URL or beginner onboarding request, read `CODEX-START.md` first
and guide the user through the actual authorized local setup. Do not return a
manual installation assignment. A bare URL is not execution consent: ask one
short intent question when necessary; do not repeat it after installation is
already requested. Follow workspace rules, approvals, and organizational policy.

- The sole skill is `.agents/skills/medical-journal-to-pptx-classroom/SKILL.md`.
- Use `setup-codex.sh` or `setup-codex.ps1`; no alternative/global installer.
- Resolve paths from the root containing `.classroom-project.json`.
- Use this project's `.venv` through `journal` / `journal.cmd`.
- Only a successful current setup receipt allows proceeding to skill reading.
- Actually read the complete skill, then request the user's PDF. Do not claim
  that an installer can attest model loading, login, or quota.
- With a readable PDF, report its title and page count, then execute the full
  workflow without unnecessary outline-approval or repeated prompt stages.
- Save final PPTX and optional PDF in `outputs/`; keep specs, assets and QA in
  `.skill-work/<run-id>/`. Never overwrite an unrelated existing presentation.
- Preserve 40–55 English slides, Traditional Chinese notes, figure provenance,
  grayscale protection, prebuild QA, final QA and honest optional-render status.
- Never change QA rules to obtain a pass or invent clinical findings.
- Do not publish papers, decks, patient information or credentials. The bundled
  synthetic paper is for automated testing, not the student's default article.
