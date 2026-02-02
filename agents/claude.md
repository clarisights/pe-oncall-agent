# Claude Agent Notes

## Mission
Assist with on-call automation experiments for Adwyze by:
- Monitoring Zulip requests (`@probably`, DMs) and responding with RCAs or `/product` doc answers.
- Iterating on tool orchestration (Sourcegraph, repo search, metrics/log hooks) to improve confidence/accuracy.
- Capturing learnings back in `README.md` / `HANDOVER.md`.

## Boot Checklist
1. Clone `clarisights/pe-oncall-agent`.
2. Copy `.env.example` to `.env` and populate:
   - `ZULIP_SITE`, `ZULIP_EMAIL`, `ZULIP_API_KEY`
   - `CODEX_API_KEY` (required for RCAs)
   - Optional `SOURCEGRAPH_URL/TOKEN` if mirrors are ready
3. Ensure local repos exist (temporary requirement):
   - `../adwyze`
   - `../adwyze-frontend`
4. Start stack:
   ```bash
   docker compose -f docker-compose.yml up -d --build
   docker compose logs -f bot
   ```
   or run `uvicorn app.main:app --reload` with a virtualenv for local dev.

## Current Constraints
- Service hints disabled → bot searches both repos by default.
- Sourcegraph optional; when disabled, ripgrep is sole evidence source.
- `/product` command only searches repo docs (no Notion yet).
- Local repo bind-mount still mandatory (remote mirrors TODO).

## Priorities / Ideas
1. Replace local bind mounts with hosted git mirrors (and wire Sourcegraph to them).
2. Rebuild service hinting (topic classifier, TF-IDF keywords, Sourcegraph symbol index).
3. Integrate Notion/Shortcut/Jenkins for richer next-step suggestions.
4. Add confidence gating + clarifying question flow before posting shaky RCAs.

Document major changes or discoveries in `HANDOVER.md` so future agents can pick up quickly.
