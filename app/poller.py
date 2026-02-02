from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Iterable, Optional

from zulip import ZulipError

from .zulip_client import ZulipBotClient

logger = logging.getLogger(__name__)


class ZulipEventPoller:
    """Background long-poll loop that streams Zulip events to a handler callback."""

    def __init__(
        self,
        client: ZulipBotClient,
        handler: Callable[[Dict[str, Any]], None],
        event_types: Optional[Iterable[str]] = None,
        narrow: Optional[Iterable[Any]] = None,
    ) -> None:
        self.client = client
        self.handler = handler
        self.event_types = event_types
        self.narrow = narrow
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._running = threading.Event()

    def start(self) -> None:
        if self._running.is_set():
            return
        logger.info("Starting Zulip event poller thread")
        self._running.set()
        self._thread.start()

    def stop(self) -> None:
        logger.info("Stopping Zulip event poller")
        self._running.clear()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while self._running.is_set():
            queue_id = None
            last_event_id: Optional[int] = None
            try:
                response = self.client.register_event_queue(
                    event_types=self.event_types,
                    narrow=self.narrow,
                )
            except ZulipError as exc:
                logger.exception("Failed to register Zulip event queue: %s", exc)
                time.sleep(5)
                continue

            if response.get("result") == "error":
                logger.error("Zulip queue registration failed: %s", response.get("msg"))
                time.sleep(5)
                continue

            queue_id = response.get("queue_id")
            last_event_id = response.get("last_event_id")
            if not queue_id:
                logger.error("Queue registration returned no queue_id. Response=%s", response)
                time.sleep(5)
                continue

            logger.info("Registered Zulip queue_id=%s", queue_id)

            while self._running.is_set() and queue_id:
                try:
                    events = self.client.poll_events(queue_id, last_event_id)
                    for event in events.get("events", []):
                        last_event_id = event["id"]
                        if event.get("type") == "message":
                            self.handler(event["message"])
                except ZulipError as exc:
                    logger.warning("Zulip polling error: %s; will re-register queue", exc)
                    time.sleep(2)
                    break
                except Exception:
                    logger.exception("Unexpected error while processing Zulip event")
        logger.info("Zulip poller exiting")
