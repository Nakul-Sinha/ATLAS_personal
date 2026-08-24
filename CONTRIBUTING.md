# Contributing to ATLAS

Thanks for your interest in ATLAS. This guide covers local setup and the conventions
used across the monorepo.

## Repository layout

| Path | What it is | Toolchain |
|------|------------|-----------|
| `ml/` | Vision-driven desktop agent | Python 3.12, Ollama |
| `ml/mcp/` | Browser automation agent | Python 3.12, Node.js, Chrome |
| `backend/` | FastAPI WebSocket relay | Python 3.12 |
| `frontend/` | Tauri v2 + Next.js launcher | Node.js, Rust |
| `companion-app/` | Flutter mobile client | Flutter/Dart |
| `landing-page/` | Static marketing page | HTML/CSS |

## Prerequisites

- Python 3.12+
- Node.js 20+
- Rust 1.77+ (for the Tauri frontend)
- Flutter 3.x (for the companion app)
- Ollama (for the ML agent) with `llama3.2` and `llava` pulled
- Google Chrome (for the browser agent)

## Development conventions

- Keep changes scoped to one component per pull request where possible.
- Python: format and lint with `ruff`. Prefer type hints.
- Run the relevant tests before opening a PR:
  - `pytest backend/`
  - `pytest ml/tests/`
- Frontend: `npm run lint` and `npm run build` from `frontend/`.
- Write commit messages in the imperative mood, one concern per commit.

## Environment variables

Each component that needs configuration ships an `.env.example`. Copy it to `.env` and
fill in values. Never commit real secrets; `.env` files are gitignored.

## Pull requests

- Describe what changed and why.
- Link the relevant IDs from `issues.md`.
- Ensure CI is green.
