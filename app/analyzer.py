from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .repo import LocalRepo, RepoMatch, load_default_repos

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "the",
    "this",
    "that",
    "have",
    "error",
    "issue",
    "with",
    "when",
    "from",
    "user",
    "users",
    "request",
    "requests",
    "failed",
    "failing",
    "frontend",
    "backend",
    "prod",
    "production",
}


@dataclass
class RepoFinding:
    repo: str
    matches: List[RepoMatch]
    note: str = ""


def _extract_keywords(text: str, limit: int = 4) -> List[str]:
    tokens = re.findall(r"[a-zA-Z]{4,}", text.lower())
    keywords: List[str] = []
    for token in tokens:
        if token in STOP_WORDS:
            continue
        if token in keywords:
            continue
        keywords.append(token)
        if len(keywords) >= limit:
            break
    return keywords


class BasicAnalyzer:
    def __init__(self) -> None:
        base_dir_env = os.getenv("TRIAGE_REPO_BASE")
        base_dir = Path(base_dir_env) if base_dir_env else None
        self.repos = load_default_repos(base_dir=base_dir)
        repo_names = ", ".join(repo.name for repo in self.repos)
        logger.info("Analyzer loaded repos: %s", repo_names)

    def analyze(self, incident_text: str) -> str:
        keywords = _extract_keywords(incident_text)
        if not self.repos:
            return "I could not locate the local repos; please ensure they exist next to this project."

        findings: List[RepoFinding] = []
        for repo in self.repos:
            matches: List[RepoMatch] = []
            for keyword in keywords:
                matches.extend(repo.search(keyword, limit=1))
                if len(matches) >= 3:
                    break

            note = ""
            if not matches:
                commits = repo.recent_commits(limit=1)
                if commits:
                    last = commits[0]
                    note = f"latest commit {last.sha} by {last.author} on {last.date}: {last.message}"
                else:
                    note = "no matches and unable to read recent commits"
            findings.append(RepoFinding(repo=repo.name, matches=matches, note=note))

        lines: List[str] = []
        lines.append("Automated triage check")
        if keywords:
            lines.append(f"Keywords noticed: {', '.join(keywords)}")
        else:
            lines.append("Keywords: (none detected)")

        for finding in findings:
            lines.append(f"* Repo `{finding.repo}`")
            if finding.matches:
                for match in finding.matches:
                    lines.append(
                        f"  - {match.path}:{match.line} — {match.preview[:160]}"
                    )
            if finding.note:
                lines.append(f"  - {finding.note}")

        lines.append("")
        lines.append("_reply with `next steps` for additional guidance_")
        return "\n".join(lines)
