from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TriageRequest:
    sender_email: str
    stream: Optional[str]
    topic: Optional[str]
    incident_text: str
    thread_context: List[str] = field(default_factory=list)

    def combined_text(self) -> str:
        lines = [self.incident_text.strip()]
        if self.thread_context:
            lines.append(
                f"Thread context (latest {len(self.thread_context)} messages):"
            )
            lines.extend(self.thread_context)
        return "\n".join(line for line in lines if line)
