# Working in MDT Observatory

- Read `vision.txt` and `docs/architecture.md` before changing the workflow.
- Python is managed with uv and `.python-version`; commit `uv.lock` with
  dependency changes. Frontend uses npm and `package-lock.json`.
- Use Tailwind utilities and the existing light/dark theme tokens. Preserve
  before-paint theme selection, accessible controls and specialty-specific layouts.
- Keep activity readable to clinicians. Technical provider metadata belongs in
  audit exports and telemetry, not clinical panels; never hide review failures.
- Keep role runtime/tool execution separate from the chair state machine.
- Never add real patient data, secret values, fabricated medical citations,
  hidden model reasoning or automatic clinical decisions.
- Preserve explicit rehearsal/live labeling, evidence access metadata,
  role-scoped tools and version-bound human review.
- Do not resolve friction merely because time passed or a model claimed consensus.
- Every workflow change needs invariant tests in `tests/test_workflow.py`;
  runtime changes need role/evidence/tool-loop tests.
- Run `uv run --frozen ruff check .`, `uv run --frozen mypy`,
  `uv run --frozen pytest`, and the frontend
  production build. Exercise the browser for UI changes.
- Azure remains one active revision/replica. Blob persistence uses managed
  identity, private networking and conditional ETag writes; keep these gates.
  SQLite is the local backend. Never weaken inherited policy to enable storage.
- Keep generated decisions, screenshots, databases, credentials and environment
  files out of Git. Document any demo or operational behavior changes.
