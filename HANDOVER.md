# On-call Triage Bot – Handover Notes

## Purpose
Prototype Zulip agent that triages on-call incidents for Adwyze/Adwyze-frontend by:
- listening to PMs/mentions, fetching thread context, and replying with Codex-generated RCAs or doc snippets (`/product` command).
- searching local repo checkouts (and optionally Sourcegraph) for evidence.
- exposing `/status` and `rerun` commands for follow-ups.

## What’s in this repo
- `app/` FastAPI service (poller, analyzer, Codex wrapper, product command).
- `docker-compose.yml` full stack (git-daemon, Sourcegraph, bot) + `docker-compose.sourcegraph.yml`.
- `scripts/sync_mirrors.sh` to build Sourcegraph mirrors.
- `README.md` with setup/status snapshot, `.env.example` for required env vars.
- GitHub repo published at `https://github.com/clarisights/pe-oncall-agent`.

## Recent changes (this session)
1. Documented current capabilities, gaps, and TODO about replacing local bind mounts with hosted mirrors + Sourcegraph tokens.
2. Added `.env.example`, improved `.gitignore`, and published the repo to GitHub (`docs:` + `feat:` commits).
3. Disabled noisy service hints and optional commit evidence; `/product` command now works even when embedded in mentions.
4. Added `HANDOVER.md` (this file) and `agents/claude.md` for future AI/engineer orientation.

## Current limitations / TODOs
- **Repo access**: bot still bind-mounts `../adwyze` and `../adwyze-frontend`. TODO: mirror repos to a remote git host (or use Sourcegraph gitserver) and provide deploy tokens so containers aren’t tied to dev machines.
- **Sourcegraph**: requires manual git-daemon + mirrors. Add automated mirroring + credentials, or disable entirely until remote hosting exists.
- **Service hints**: disabled because they returned irrelevant evidence. Needs a new classifier/heuristic before re-enabling targeted searches.
- **Codex CLI**: ensure `CODEX_API_KEY` is available in non-local deployments (currently via `.env`/Secret Manager only).
- **Product answers**: `/product` command only searches repo docs; no Notion/Metabase integration yet.
- **Security**: secrets live in `.env`; migrate to secret manager for prod and audit Codex prompts for PII.

## How to run locally (summary)
1. `cp .env.example .env` and fill out Zulip + Codex (Sourcegraph optional).
2. Keep `../adwyze` and `../adwyze-frontend` checked out and up to date.
3. `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
4. `uvicorn app.main:app --reload` (or `docker compose -f docker-compose.yml up -d --build` for the full stack).

## Useful commands
- `docker compose -f docker-compose.yml up -d --build` – spin up git-daemon + Sourcegraph + bot (uses `.env`).
- `/product <question>` in Zulip – returns doc snippets instead of RCA.
- `/status`, `/rerun` – read cached summary or re-trigger analysis.

## Next recommended steps
1. Host read-only mirrors (S3, GCS, GitHub) and update Sourcegraph/Git daemon configs to pull from them.
2. Reintroduce service hints with a classifier driven by actual incidents (maybe via Codex-assisted hint generation).
3. Expand evidence sources (Notion runbooks, metrics/logs) and add confidence gating before responding.
4. Harden secrets and add automated mirror sync cron in `docker-compose`.

Feel free to reach out in #pe-oncall or open issues in the GitHub repo for future enhancements.
