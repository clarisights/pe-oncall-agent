# Codex Agent Quick Reference

Designed to give the Codex CLI (or any LLM agent) enough context to reason about this repo without re-indexing everything.

## Core entry points

- `app/main.py` – FastAPI app wiring Zulip poller, command routing (`/product`, `/status`, `rerun`), and background triage execution.
- `app/triage.py` – Tool orchestrator + `TriageService`; currently runs keyword-based searches across both repos (service hints disabled).
- `app/tools.py` – `ToolRegistry` abstraction over local repos + optional Sourcegraph client.
- `app/repo.py` – Local repo helpers (ripgrep search, commit listing, file reads).
- `app/llm.py` – Codex CLI wrapper with auto-login and prompt construction.
- `app/poller.py` + `app/zulip_client.py` – Long-polling Zulip event loop and REST helpers.
- `app/sourcegraph_client.py` – GraphQL search client (only used if `SOURCEGRAPH_URL/TOKEN` are set).
- `app/state.py` – In-memory incident store (latest request/summary per stream/topic).
- `app/analyzer.py` – Fallback keyword analyzer when Codex is unavailable.

## Commands & features

- Mention or DM triggers RCA (`triage_service.run`).
- `/product <query>` anywhere in the message → `_answer_product_query` surfaces doc snippets (filters paths containing `docs/`, `readme`, etc.).
- `/status`, `rerun`, `next steps` – leverage `IncidentStore`.
- Thread context: `_extract_thread_reference` parses Zulip topic links or `#**stream>topic**` mentions.
- Evidence: currently ripgrep-only unless Sourcegraph env vars are present; recent commits disabled by default (`TRIAGE_INCLUDE_COMMITS=false`).

## Environment knobs (see `.env.example`)

- `TRIAGE_REPO_BASE` defaults to `/app/repos` (bind-mount locations for `adwyze`, `adwyze-frontend`).
- `CODEX_API_KEY`, `LLM_MODEL`, `CODEX_CLI_PATH`, `NODE_CLI_PATH` configure the Codex CLI stage.
- `SOURCEGRAPH_URL/TOKEN` optional for high-precision search.
- `TRIAGE_WORKERS`, `THREAD_CACHE_TTL`, `TRIAGE_BOT_ALIASES`.

## Compose/Docker

- `docker-compose.yml` – runs git-daemon (serving `./sourcegraph-data/repos`), Sourcegraph OSS, and the bot container (bind-mounts `../adwyze*`).
- `docker-compose.sourcegraph.yml` – helper stack when only Sourcegraph + git-daemon are needed.
- `Dockerfile` – multi-stage build bundling Codex CLI (Node 20 base) and Python app; installs `git` + `ripgrep`.

## Scripts

- `scripts/sync_mirrors.sh` – clones/fetches bare mirrors into `./sourcegraph-data/repos/github.com/clarisights/{adwyze,adwyze-frontend}.git`.

## Known gaps

- Service hints were disabled because they produced irrelevant matches; expect both repos to be scanned for every incident.
- Repos must be bind-mounted locally until remote mirroring is implemented.
- Sourcegraph credentials are optional; when absent, only ripgrep snippets are available.
- `/product` command still relies on repo-resident docs (no Notion/Metabase adapters yet).

Use this map to reason about code without reloading every file into Codex. When making structural changes, update this doc so future agents stay in sync.
