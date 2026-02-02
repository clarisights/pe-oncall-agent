from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, List

import zulip

from .config import settings

logger = logging.getLogger(__name__)


class ZulipBotClient:
    """Thin wrapper around zulip.Client with safer defaults for the triage bot."""

    def __init__(self) -> None:
        self.client = zulip.Client(
            email=settings.zulip_email,
            api_key=settings.zulip_api_key,
            site=settings.zulip_site,
        )

    def send_stream_message(self, content: str, stream: Optional[str] = None, topic: Optional[str] = None) -> Dict[str, Any]:
        stream_name = stream or settings.default_stream
        topic_name = topic or settings.default_topic
        if not stream_name or not topic_name:
            raise ValueError("Stream and topic are required when defaults are not set.")

        request: Dict[str, Any] = {
            "type": "stream",
            "to": stream_name,
            "topic": topic_name,
            "content": content,
        }
        logger.info("Sending stream message: stream=%s topic=%s", stream_name, topic_name)
        response = self.client.send_message(request)
        if response.get("result") != "success":
            logger.error("Failed to send stream message: %s", response)
        return response

    def send_reply(self, message: Dict[str, Any], content: str) -> Dict[str, Any]:
        """Reply in the same thread/PM as the incoming message."""
        msg_type = message["type"]
        request: Dict[str, Any] = {
            "type": msg_type,
            "content": content,
        }
        if msg_type == "stream":
            request["to"] = message["display_recipient"]
            request["topic"] = message["subject"]
        else:
            # Zulip expects email/user ids for PMs.
            recipients = message.get("display_recipient", [])
            if isinstance(recipients, list):
                emails = [
                    r["email"]
                    for r in recipients
                    if isinstance(r, dict) and r.get("email") != settings.zulip_email
                ]
            else:
                emails = [message.get("sender_email")]
            request["to"] = emails or [message.get("sender_email")]
        response = self.client.send_message(request)
        if response.get("result") != "success":
            logger.error("Failed to send reply: %s", response)
        return response

    def register_event_queue(
        self,
        event_types: Optional[Iterable[str]] = None,
        narrow: Optional[Iterable[Any]] = None,
    ) -> Dict[str, Any]:
        logger.info(
            "Registering Zulip event queue (event_types=%s narrow=%s)",
            event_types or "default",
            bool(narrow),
        )
        kwargs: Dict[str, Any] = {}
        if event_types:
            kwargs["event_types"] = list(event_types)
        if narrow:
            kwargs["narrow"] = list(narrow)
        return self.client.register(**kwargs)

    def poll_events(self, queue_id: str, last_event_id: Optional[int]) -> Dict[str, Any]:
        return self.client.get_events(
            queue_id=queue_id,
            last_event_id=last_event_id if last_event_id is not None else -1,
            dont_block=False,
        )

    def fetch_thread_messages(
        self, stream_name: str, topic: str, num_before: int = 30
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "anchor": "newest",
            "num_before": max(1, num_before),
            "num_after": 0,
            "narrow": [
                ["stream", stream_name],
                ["topic", topic],
            ],
        }
        result = self.client.get_messages(params)
        if result.get("result") != "success":
            logger.error(
                "Failed to fetch thread messages stream=%s topic=%s error=%s",
                stream_name,
                topic,
                result.get("msg"),
            )
            return []
        return result.get("messages", [])
