from __future__ import annotations

import logging
import os
import re
import threading
import time
from html import unescape
from typing import Optional, List, Tuple, Dict
from urllib.parse import unquote
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI
from pydantic import BaseModel

from .config import settings
from .poller import ZulipEventPoller
from .zulip_client import ZulipBotClient
from .analyzer import BasicAnalyzer
from .tools import ToolRegistry
from .llm import LLMAgent
from .triage import TriageService, ToolOrchestrator
from .models import TriageRequest
from .state import IncidentStore, IncidentRecord
from .sourcegraph_client import SourcegraphClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("triage_bot")

app = FastAPI(title="On-call Triage Bot", version="0.1.0")

zulip_client = ZulipBotClient()
sourcegraph_client = SourcegraphClient(settings.sourcegraph_url, settings.sourcegraph_token)
tool_registry = ToolRegistry(sourcegraph=sourcegraph_client)
orchestrator = ToolOrchestrator(tool_registry)
llm_agent = LLMAgent(tool_registry)
analyzer = BasicAnalyzer()
triage_service = TriageService(analyzer=analyzer, llm_agent=llm_agent, orchestrator=orchestrator)
triage_executor = ThreadPoolExecutor(
    max_workers=int(os.getenv("TRIAGE_WORKERS", "2"))
)
poller: Optional[ZulipEventPoller] = None
incident_store = IncidentStore()


class ReplyRequest(BaseModel):
    content: str
    stream: Optional[str] = None
    topic: Optional[str] = None


@app.get("/healthz")
async def healthcheck() -> dict:
    return {"status": "ok"}


@app.post("/api/v1/zulip/reply")
async def post_reply(payload: ReplyRequest) -> dict:
    result = zulip_client.send_stream_message(
        content=payload.content,
        stream=payload.stream,
        topic=payload.topic,
    )
    return {"status": "sent", "zulip": result}


THREAD_LINK_RE = re.compile(
    r"#narrow/channel/(?P<stream_id>\d+)-(?P<stream_slug>[^/]+)/topic/(?P<topic>[^\s)]+)",
    re.IGNORECASE,
)
THREAD_LABEL_RE = re.compile(r"\[#(?P<label>[^>\]]+)\s*>", re.IGNORECASE)
MANUAL_THREAD_RE = re.compile(
    r"#\*\*(?P<stream>[^>]+)>(?P<topic>[^\*]+)\*\*",
    re.IGNORECASE,
)


def _plain_text(content: str) -> str:
    text = unescape(content or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _decode_url_component(encoded: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return "%" + match.group(1)

    patched = re.sub(r"\.([0-9A-Fa-f]{2})", repl, encoded)
    return unquote(patched)


def _extract_thread_reference(raw_content: str, plain_content: str) -> Optional[Tuple[str, str]]:
    match = THREAD_LINK_RE.search(raw_content)
    if not match:
        manual = MANUAL_THREAD_RE.search(plain_content)
        if manual:
            stream_name = manual.group("stream").strip()
            topic_name = manual.group("topic").strip()
            return stream_name, topic_name
        return None
    stream_slug = match.group("stream_slug")
    topic_raw = match.group("topic")
    topic_part = topic_raw.split("/near/", 1)[0]
    topic = _decode_url_component(topic_part)

    # Try to recover human-readable stream name from the message text.
    label_match = THREAD_LABEL_RE.search(plain_content)
    if label_match:
        stream_name = label_match.group("label").strip()
    else:
        stream_name = _decode_url_component(stream_slug)
    if not stream_name:
        stream_name = stream_slug
    return stream_name, topic


def _bot_aliases() -> list[str]:
    aliases = []
    handle = settings.zulip_email.split("@")[0]
    handle = handle.split("+")[0]
    aliases.append(handle.lower())
    for sep in ("-", "_", "."):
        if sep in handle:
            aliases.append(handle.split(sep)[0].lower())
    extra = os.getenv("TRIAGE_BOT_ALIASES", "")
    for token in extra.split(","):
        token = token.strip().lower()
        if token:
            aliases.append(token)
    return list(dict.fromkeys(aliases))


def _should_respond(message: dict, plain_content: str) -> bool:
    if message.get("type") == "private":
        return True
    flags = message.get("flags") or []
    if "mentioned" in flags or "mentioned-inline" in flags:
        return True
    content = plain_content.lower()
    aliases = _bot_aliases()
    mention_tokens = set()
    for alias in aliases:
        mention_tokens.update(
            {
                alias,
                f"@{alias}",
                f"@**{alias}**",
                f"@_{alias}",
            }
        )
    mention_tokens.add("triage")
    return any(token in content for token in mention_tokens)


COMMAND_ALIASES = {
    "status": ["status", "triage status", "status?", "show status"],
    "rerun": ["rerun", "rerun analysis", "rerun triage", "next steps", "next-steps"],
    "product": ["/product", "product"],
}
DOC_PATH_KEYWORDS = (
    "docs/",
    "doc/",
    "handbook",
    "guide",
    "runbook",
    "spec",
    "adr",
    "readme",
    "wiki",
)


def _extract_command(plain_content: str) -> tuple[Optional[str], str]:
    text = plain_content.strip()
    lowered = text.lower()
    product_match = re.search(r"(^|\s)/product\b", lowered)
    if product_match:
        start = product_match.start(0)
        idx = lowered.find("/product", start)
        remainder = text[idx + len("/product"):].strip()
        return "product", remainder
    for command, aliases in COMMAND_ALIASES.items():
        for alias in aliases:
            alias_lower = alias.lower()
            if lowered == alias_lower:
                return command, ""
            if lowered.startswith(alias_lower + " "):
                remainder = text[len(alias):].strip()
                return command, remainder
    return None, ""


def handle_incoming_message(message: dict) -> None:
    sender = message.get("sender_email")
    if sender == settings.zulip_email:
        # Ignore our own messages to avoid loops.
        return

    stream = message.get("display_recipient")
    topic = message.get("subject")
    raw_content = message.get("content", "")
    plain_content = _plain_text(raw_content)
    logger.info(
        "Incoming message stream=%s topic=%s sender=%s flags=%s text=%s",
        stream,
        topic,
        sender,
        message.get("flags"),
        plain_content,
    )

    if not _should_respond(message, plain_content):
        return
    logger.info("Responding to message from %s", sender)

    stream_name = stream if isinstance(stream, str) else None
    command, remainder = _extract_command(plain_content)

    thread_lines: List[str] = []
    thread_ref = _extract_thread_reference(raw_content, plain_content)
    topic_hint = topic or ""
    fetch_stream: Optional[str] = None
    fetch_topic: Optional[str] = None
    if thread_ref:
        fetch_stream, fetch_topic = thread_ref
        topic_hint = fetch_topic
    elif isinstance(stream, list) and topic:
        stream_id = message.get("stream_id")
        if stream_id is not None:
            fetch_stream = str(stream_id)
            fetch_topic = topic
    elif isinstance(stream, str) and topic:
        fetch_stream, fetch_topic = stream, topic

    if fetch_stream and fetch_topic:
        logger.info("Fetching thread context stream=%s topic=%s", fetch_stream, fetch_topic)
        thread_messages = zulip_client.fetch_thread_messages(fetch_stream, fetch_topic, num_before=25)
        if not thread_messages:
            logger.warning(
                "No messages returned for stream=%s topic=%s; falling back to empty context",
                fetch_stream,
                fetch_topic,
            )
        else:
            logger.info(
                "Fetched %s messages for stream=%s topic=%s",
                len(thread_messages),
                fetch_stream,
                fetch_topic,
            )
        for msg in thread_messages[-10:]:
            text = _plain_text(msg.get("content", ""))
            if not text:
                continue
            author = msg.get("sender_full_name") or msg.get("sender_email")
            logger.debug("Thread snippet: %s: %s", author, text)
            thread_lines.append(f"{author}: {text}")
    logger.info("Thread context lines=%s sample=%s", len(thread_lines), thread_lines)

    normalized = plain_content.strip().lower()
    if normalized == "ping":
        zulip_client.send_reply(message, "triage bot is online :rocket:")
        return

    if command:
        if _handle_command(command, remainder, message, stream_name, topic, thread_lines):
            return

    triage_request = TriageRequest(
        sender_email=sender or "",
        stream=stream_name,
        topic=topic,
        incident_text=plain_content,
        thread_context=thread_lines,
    )
    incident = incident_store.get_or_create(triage_request)
    triage_executor.submit(_run_triage_and_reply, message, triage_request, incident)


def _handle_command(
    command: Optional[str],
    remainder: str,
    message: dict,
    stream: Optional[str],
    topic: Optional[str],
    thread_lines: List[str],
) -> bool:
    incident = incident_store.find(stream, topic)
    if command == "status":
        if incident and incident.last_summary:
            zulip_client.send_reply(message, f"Latest triage summary:\n\n{incident.last_summary}")
        else:
            zulip_client.send_reply(message, "No prior triage summary found for this thread.")
        return True
    if command == "rerun":
        request: Optional[TriageRequest] = None
        if remainder:
            request = TriageRequest(
                sender_email=message.get("sender_email") or "",
                stream=stream,
                topic=topic,
                incident_text=remainder,
                thread_context=thread_lines,
            )
        elif incident and incident.last_request:
            request = incident.last_request
        else:
            zulip_client.send_reply(
                message,
                "I couldn't find prior triage context to rerun. Please provide details about the issue first.",
            )
            return True

        target_incident = incident_store.get_or_create(request)
        zulip_client.send_reply(message, "Re-running automated triage; will reply with updates shortly.")
        triage_executor.submit(_run_triage_and_reply, message, request, target_incident)
        return True
    if command == "product":
        query = remainder.strip()
        if not query:
            zulip_client.send_reply(
                message,
                "Use `/product <question>` to search product docs. Example: `/product TrendyolGO pod adjust requirements`.",
            )
            return True
        reply = _answer_product_query(query)
        zulip_client.send_reply(message, reply)
        return True
    return False


def _answer_product_query(query: str, max_results: int = 4) -> str:
    snippets = _gather_product_snippets(query, max_results=max_results)
    if not snippets:
        return (
            f"I couldn't find any product docs mentioning “{query}”. "
            "Try refining the query or share more context so I can point you to the right runbook."
        )
    lines = [f"Product context for `{query}`:"]
    for repo, path, line_no, snippet in snippets:
        trimmed = snippet.strip()
        if len(trimmed) > 500:
            trimmed = trimmed[:500] + "…"
        lines.append(f"- `{repo}:{path}:{line_no}`\n```text\n{trimmed}\n```")
    lines.append("Need deeper details? Follow up with `/product <more context>`.")
    return "\n\n".join(lines)


def _gather_product_snippets(query: str, max_results: int = 4) -> List[tuple[str, str, int, str]]:
    hits: List[tuple[str, str, int, str]] = []
    for repo in tool_registry.list_repos():
        matches = tool_registry.search_code(repo, query, limit=6)
        for match in matches:
            lower_path = match.path.lower()
            if not any(keyword in lower_path for keyword in DOC_PATH_KEYWORDS):
                continue
            snippet = tool_registry.read_file(
                repo,
                match.path,
                max(match.line - 4, 1),
                match.line + 4,
            ) or match.preview
            snippet = snippet.strip()
            if not snippet:
                continue
            hits.append((repo, match.path, match.line, snippet))
            if len(hits) >= max_results:
                return hits
    return hits


def _run_triage_and_reply(message: dict, triage_request: TriageRequest, incident: IncidentRecord) -> None:
    try:
        summary = triage_service.run(triage_request)
    except Exception as exc:
        logger.exception("Failed to run triage pipeline")
        summary = f"Unable to run automated analysis: {exc}"

    incident.update(summary, triage_request)
    response = zulip_client.send_reply(message, summary)
    if response.get("result") == "success":
        logger.info("Reply sent to %s", triage_request.sender_email)
    else:
        logger.error("Failed to send triage response: %s", response)


@app.on_event("startup")
async def startup_event() -> None:
    global poller
    poller = ZulipEventPoller(
        client=zulip_client,
        handler=handle_incoming_message,
    )
    poller.start()
    logger.info("Startup complete; polling Zulip for messages.")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    if poller:
        poller.stop()
    triage_executor.shutdown(wait=False)
