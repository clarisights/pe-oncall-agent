from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import TriageRequest


@dataclass
class IncidentRecord:
    stream: Optional[str]
    topic: Optional[str]
    last_summary: Optional[str] = None
    last_request: Optional[TriageRequest] = None
    history: List[str] = field(default_factory=list)

    def update(self, summary: str, request: TriageRequest) -> None:
        self.last_summary = summary
        self.last_request = request
        self.history.append(summary)


class IncidentStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._incidents: Dict[str, IncidentRecord] = {}

    def _key(self, stream: Optional[str], topic: Optional[str]) -> str:
        return f"{stream or 'dm'}::{topic or 'general'}"

    def get_or_create(self, request: TriageRequest) -> IncidentRecord:
        key = self._key(request.stream, request.topic)
        with self._lock:
            if key not in self._incidents:
                self._incidents[key] = IncidentRecord(stream=request.stream, topic=request.topic)
            return self._incidents[key]

    def find(self, stream: Optional[str], topic: Optional[str]) -> Optional[IncidentRecord]:
        key = self._key(stream, topic)
        with self._lock:
            return self._incidents.get(key)

    def list_incidents(self) -> List[IncidentRecord]:
        with self._lock:
            return list(self._incidents.values())
