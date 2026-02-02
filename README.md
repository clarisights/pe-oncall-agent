## On-call Triage Bot (v1)

This repo sketches a lightweight triage bot that listens to Zulip, pulls code context from `adwyze` and `adwyze-frontend`, runs a quick RCA using Codex (or a local analyzer fallback), and replies with findings. It is intentionally scoped to read-only actions so that we can validate the workflow before expanding into deploys or ticket updates.

### Status Snapshot

- **Works today**
  - Polls Zulip (PMs or mentions) and replies with RCA-style summaries using Codex.
  - Keyword-based code search across `adwyze` + `adwyze-frontend` via ripgrep; `/product …` queries surface documentation snippets from the same repos.
  - Optional `/status` and `/rerun` commands reuse cached incident state.
  - Full-stack compose file runs git-daemon, Sourcegraph, and the bot together when repos are bind-mounted locally.
- **Known gaps**
  - Service hinting is disabled (needs a better classifier), so every request scans both repos.
  - Sourcegraph integration requires manual setup of git mirrors and API tokens; without it, searches rely solely on local clones.
  - Bot still depends on mounting local working copies; no remote git hosting yet.
- **To make this production-ready**
  - Host read-only mirrors in object storage or GitHub instead of bind-mounting local repos, and point Sourcegraph at that host with deploy keys/tokens.
  - Harden Codex login (CI-safe secrets distribution) and add retries/backoff for CLI failures.
  - Add policy-backed data sources (metrics/logs, Notion runbooks) and confidence-aware prompting before declaring RCAs.

> **TODO**: Replace the local bind-mount approach with mirrored repos fetched by the containers themselves (or Sourcegraph’s own gitserver) using GitHub tokens. Until then, developers must keep `../adwyze` and `../adwyze-frontend` up to date.

### Architecture

1. **Zulip Listener**
   - Use a Zulip outgoing webhook or long-lived bot.
   - Normalize each new incident message into a `TriageRequest` (incident id, stream/topic links, free-form text).
2. **Context Builder**
   - GitHub App with read access to `adwyze` and `adwyze-frontend`.
   - Preload service maps (owners, runbooks) and expose helpers for repo search, file reads, and recent commits.
   - Optional Sourcegraph OSS instance for high-precision code search (used when `SOURCEGRAPH_URL`/`SOURCEGRAPH_TOKEN` are set).
   - Optional adapters for Grafana/Graphite queries or GCP Logs (start with canned queries run via REST APIs).
3. **LLM RCA Worker**
   - Stateless service (FastAPI/Express) that calls Codex (or another LLM) with function-calling tools for:
     - `search_repo(repo, query)`
     - `read_file(repo, path, ref)`
     - `run_metric_query(source, params)` — initially mocked.
   - Prompt pattern:
     1. Summarize the Zulip incident.
     2. Ask for hypotheses + evidence using available tools.
     3. Produce `finding`, `confidence`, `next_steps`.
4. **Responder**
   - Formats RCA into a Zulip reply (bullets for cause, evidence, next steps).
   - Stores conversation + artifacts in a lightweight DB (SQLite/Postgres) for auditing.

### Data Flow

```
Zulip -> Webhook (FastAPI) -> enqueue job (Redis/Cloud Tasks)
        -> Context Builder pulls code/log snippets
        -> LLM RCA Worker composes analysis
        -> Responder posts summary back to Zulip + persists state
```

### Implementation Checklist

- [ ] Provision Zulip bot + webhook endpoint.
- [ ] Create GitHub App (read-only) and helper SDKs for repo search + file fetch.
- [ ] Stand up FastAPI service (`/zulip-webhook`, `/healthz`).
- [ ] Define `TriageRequest`, `ContextPacket`, `RCAResponse` dataclasses.
- [ ] Implement tool functions for repo search and file read (call GitHub Search + Contents APIs).
- [ ] Wire Codex/LLM function-calling prompt with tool router + response formatter.
- [ ] Implement Zulip responder (REST API call to reply in the same topic/thread).
- [ ] Add minimal persistence (incident id, LLM response, tool logs).
- [ ] Add unit tests for tool adapters + formatter.
- [ ] Deploy behind HTTPS (Cloud Run/App Engine) with secrets in Secret Manager.

### Local development quick start

1. Copy `.env.example` to `.env`, fill in Zulip + Codex credentials, and (optionally) Sourcegraph details. These vars are loaded automatically when you use `docker compose`.
1. Drop the Zulip bot credentials into `.zuliprc` (already ignored from git) or export `ZULIP_EMAIL`, `ZULIP_API_KEY`, `ZULIP_SITE`.
2. (Optional) set `TRIAGE_DEFAULT_STREAM` and `TRIAGE_DEFAULT_TOPIC` so `/api/v1/zulip/reply` does not need explicit values.
3. (Optional) export `TRIAGE_REPO_BASE` if the `adwyze` repos live somewhere other than the parent directory of this project. You can also extend `SERVICE_HINTS` in `app/triage.py` to add runbook/metadata for other services (e.g., mapping stream/topic keywords like “reports” to `adwyze-frontend`).
   - Use `TRIAGE_BOT_ALIASES` (comma-separated) if your Zulip bot is usually mentioned via a nickname (e.g., `probably` instead of `probably-bot`).
     - LLM options:
       - `CODEX_API_KEY` – used to auto-login the Codex CLI at startup (if already logged in, this can be omitted).
       - `CODEX_CLI_PATH` – override if the CLI binary is not simply `codex`.
       - `NODE_CLI_PATH` – override if the Node.js binary required by the Codex CLI is not `node`.
       - `LLM_MODEL` – passed to `codex exec --model` (optional; leave unset to use your Codex account default).
   - Sourcegraph (optional but recommended for high-accuracy code retrieval):
     - `SOURCEGRAPH_URL` – e.g., `http://localhost:8080` if you run Sourcegraph OSS locally.
     - `SOURCEGRAPH_TOKEN` – API token for that instance.
   - `THREAD_CACHE_TTL` – seconds to cache Zulip thread context (default 120).
   - `TRIAGE_WORKERS` controls how many background triage jobs may run in parallel (default 2).
4. Install dependencies: `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
5. Run the service: `uvicorn app.main:app --reload`.
6. Mention the bot in Zulip or send it a PM. Saying “ping” elicits `triage bot is online`. Any other message containing “triage” (or a PM) triggers the local repo analyzer which searches `../adwyze` and `../adwyze-frontend` for keywords using `rg` and replies with file snippets or the latest commit summary. If you include a Zulip topic link (e.g., `#narrow/channel/.../topic/...`), the bot also fetches the last few messages from that thread for additional context (stream subscription required).
7. After the bot replies, you can type `status` to see the latest summary, `rerun` / `next steps` to trigger another automated analysis, or `/product <question>` (anywhere in the message) to fetch product documentation snippets instead of a full RCA.
8. Use `POST /api/v1/zulip/reply` to broadcast updates back into a stream/topic once RCA logic is ready.

> Note: the analyzer uses [`rg`](https://github.com/BurntSushi/ripgrep); install it via Homebrew (`brew install ripgrep`) or ensure it is on `PATH`.

### Sourcegraph + git daemon helper stack

For high-accuracy code retrieval you can run Sourcegraph OSS locally and serve mirrored repos via `git daemon`:

1. Sync the mirrors under `./sourcegraph-data`:
   ```bash
   chmod +x scripts/sync_mirrors.sh
   ./scripts/sync_mirrors.sh
   ```
   The script clones (or fetches) bare mirrors for `clarisights/adwyze` and `clarisights/adwyze-frontend`. Override `SOURCEGRAPH_REPO_OWNER`, `SOURCEGRAPH_UPSTREAM_BASE`, or edit the `REPOS` array to add more repos.

2. Launch Sourcegraph + git daemon:
   ```bash
   docker compose -f docker-compose.sourcegraph.yml up -d
   ```
   This exposes Sourcegraph on `http://localhost:7080` and a git daemon on `git://localhost:9418` reading from the mirrored repos.

3. In Sourcegraph, add a “Generic Git host” pointed at `git://host.docker.internal` (or `git://localhost` if running outside Docker Desktop) with repos `clarisights/adwyze.git` and `clarisights/adwyze-frontend.git`. After syncing, create an access token and set `SOURCEGRAPH_URL` / `SOURCEGRAPH_TOKEN` before starting the triage service.

> **Note**: The bot container (via `docker-compose.full-stack.yml`) bind-mounts your local working copies `../adwyze` and `../adwyze-frontend` into `/app/repos`. Keep those sibling repositories present and up-to-date (e.g., via `git pull`) so the bot always analyzes the latest code. If your repo layout differs, adjust the volume paths accordingly.

### Operational Considerations

- **Auth**: every external call uses service accounts or GitHub App tokens rotated via Secret Manager.
- **Rate limits**: cache repo search results for a request; throttle LLM calls per incident.
- **Privacy**: redact secrets/log tokens before sending to Codex/LLM providers.
- **Fallbacks**: if LLM fails, reply with “analysis failed” and link to logs for manual follow-up.

### Next (v2) Ideas

## Full-stack local setup

To run the entire stack (git mirrors + Sourcegraph + triage bot) with one command:

1. Sync or update mirrors: `./scripts/sync_mirrors.sh`
2. Provide the necessary env vars (ZULIP creds, Sourcegraph token, Codex settings) in a `.env` file.
3. Start everything:
   ```bash
   docker compose -f docker-compose.full-stack.yml up -d --build
   ```
   This spins up the git daemon, Sourcegraph OSS, and the triage bot (pointing at `sourcegraph:7080`). The bot logs are visible via `docker compose logs -f bot`.

When you’re done, `docker compose -f docker-compose.full-stack.yml down` stops the services.

Once v1 reliably summarizes incidents, we can expand into:
1. Metabase/Grafana shortcuts for metrics.
2. Shortcut/Jira ticket updates.
3. Jenkins pipeline triggers for test/staging deploys.
4. PR drafting + release orchestration.
5. Lightweight code indexing (Sourcegraph or local embeddings) so the LLM can retrieve the most relevant files without scanning entire repos on every incident.

## Ultimate Objective

- Build an autonomous on-call assistant that watches Zulip, triages incidents end-to-end (context gathering → RCA → next steps), and offers interactive commands for follow-ups.
- Provide deep tooling for evidence (Sourcegraph-indexed code, runbooks/Notion, metrics/logging, git history) so Codex responses have concrete backing.
- Maintain per-incident state (history, commands, clarifications) and integrate with downstream systems (Shortcut, Jenkins, deployment pipelines).

### Current Capabilities
- FastAPI bot with Zulip poller, incident store, and commands (`status`, `rerun`).
- Sourcegraph-backed code search and file reads (git daemon + mirrors + compose stack) when `SOURCEGRAPH_*` vars are provided.
- Codex CLI integration with structured prompts + logging of prompt length, evidence sample, confidence.
- Dynamic keyword extraction; legacy service hints proved noisy/broken and are currently disabled pending a redesign.
- `/product` command for doc lookups alongside RCA replies.
- README instructions + scripts for syncing repo mirrors and running Sourcegraph/git-daemon/bot services.

### Next Steps
1. Improve service inference (topic classifier, better keyword weighting, automatic hint generation via Codex).
2. Expand evidence sources (runbooks via Notion MCP, git diff history, metrics/log stubs).
3. Add clarifying question flows and action recommendations (confidence thresholds, open questions).
4. Integrate follow-up actions (Jenkins triggers, Shortcut ticket updates, deployment commands).
5. Harden deployment (containerize bot alongside Sourcegraph/git-daemon, schedule mirror syncs, secrets management, remote repo hosting without local mounts).
