## Vision
- Autonomous on-call triage assistant that monitors Zulip, gathers context (code, metrics, runbooks), produces credible RCAs, and drives follow-up actions (status updates, reruns, next steps).
- Integrates deeply with code repos (auto-indexed via Sourcegraph), Notion runbooks, Jenkins/CI, metrics/logging systems.
- Provides interactive commands (status, rerun, ask clarifying questions) and maintains incident state/history per stream/topic.

## Current State
- FastAPI bot with Zulip poller, incident state store, and command handling.
- Local repo readers + Sourcegraph integration for code search and file read via new `SERVICE_HINTS` + dynamic directory inference.
- Codex CLI agent invoked with context (incident text + thread messages + code snippets). Automatic fallback to keyword analyzer if Codex fails.
- Scripts + docker-compose to run git daemon (mirrored repos) and Sourcegraph OSS; triage service uses `SOURCEGRAPH_URL/TOKEN` for high-accuracy snippets.
- Logging instrumentation (thread messages, service hints, tool results, Codex prompt size) for diagnosing RCA quality.

## Next Objectives
1. Improve service inference: topic → service classifier, learned keyword weights, dynamic hints (e.g., per-stream overrides).
2. Expand evidence sources: runbook fetch (Notion MCP), git log diffs (`sg search type:commit`), metrics/log stubs.
3. Clarifying question flow: bot asks for missing info instead of guessing when confidence low; use incident state to remember answers.
4. Richer responses: structured findings with confidence bars, open questions, action checklists.
5. Enable follow-up actions: run Jenkins jobs, create Shortcut tickets, update Zulip threads with status automatically.
6. Harden infra: containerize entire stack; keep Sourcegraph/git daemon and bot in docker-compose for easy spin-up; periodic mirror sync.
7. Security: secrets via dotenv or Secret Manager, scrub logs, enforce least privilege tokens.

