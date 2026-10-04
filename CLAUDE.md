# Naukri Job Automation

A local Windows tool: FastAPI + SQLite + server-rendered Jinja pages. State of the build,
architecture and open decisions are in PLAN.md. Read it before starting work.

## Owner's priorities, in order

Reliability, security, simple onboarding, good UX, modular architecture, error recovery,
testability, GitHub readiness.

## Commands

- Tests: `.venv\Scripts\python -m pytest`
- Run for a person: `start.bat` (or `python -m backend`, `--no-browser` to skip opening one)
- Preview while developing: the `dashboard` entry in `.claude/launch.json`

## Rules for this project

- Never build anything that gets past a CAPTCHA, OTP or other Naukri check. On any check the
  tool stops and asks the user.
- Never store or type the user's Naukri password. Login is done by the user in a browser window.
- The tool's browser is always visible. Never run it headless: Naukri answers "Access Denied" and
  then keeps serving that profile fake "No result found" pages (seen 2026-10-04).
- Never disguise the automated browser: no stealth plugins, no hiding `navigator.webdriver`, no
  user-agent changes, no resetting the profile to shed a flag. If Naukri refuses the tool, the
  tool says so and stops.
- The same goes for Google: its sign-in refuses a tool-controlled browser. Do not work around it;
  users log in to Naukri with a password or OTP instead.
- A real application cannot be taken back. Never send one while developing or testing unless the
  owner has named that exact job in the conversation. Test applying with the fake page in
  `tests/test_apply.py`.
- Live tests against Naukri cost the owner's IP its standing. Keep them to a handful of page
  loads, with a throwaway `NJA_DATA_DIR`, and prefer the fake page in `tests/test_discover.py`.
- To try the app without touching the user's real data, put `NJA_DATA_DIR` and `NJA_RESUMES_DIR`
  in `.env` pointing at a throwaway folder, and delete `.env` afterwards.
- UI text is for students, many not native English speakers: short plain sentences, no jargon.
- A feature that is not built yet is labelled "not available in this version yet" in the UI
  and README. Remove the label when the feature ships.
- Sample jobs (`jobs.is_demo`) must never be applied to or written to a Sheet.
- UI changes follow the design tokens at the top of `dashboard/static/style.css`. For new UI
  work, use the `ui-ux-pro-max` skill in `.claude/skills/` (git-ignored, MIT).
- The UI is a glass theme with a light (default) and a dark set of tokens. A rule never names a
  colour directly; add a token to both sets instead, and check new UI in both themes.
- Motion goes in `dashboard/static/ui.js` and must do nothing under `prefers-reduced-motion`.
  Pages must stay fully usable with that file missing.
- Schema changes: tables are created with `create_all`, which does not alter existing tables.
  Once real applications are being recorded, add a migration instead of editing a model in place.
