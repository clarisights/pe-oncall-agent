from __future__ import annotations

import logging
import shutil
import subprocess
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Tuple

logger = logging.getLogger(__name__)
RG_AVAILABLE = shutil.which("rg") is not None


@dataclass
class RepoMatch:
    path: str
    line: int
    preview: str


@dataclass
class RepoCommit:
    sha: str
    author: str
    date: str
    message: str


@dataclass
class LocalRepo:
    name: str
    path: Path

    def exists(self) -> bool:
        return self.path.exists()

    def search(self, keyword: str, limit: int = 3) -> List[RepoMatch]:
        if not keyword or not self.exists():
            return []
        if not RG_AVAILABLE:
            logger.warning("ripgrep not available; skipping code search for %s", self.name)
            return []

        cmd = [
            "rg",
            "--no-heading",
            "--line-number",
            "--ignore-case",
            "-m",
            str(limit),
            keyword,
            str(self.path),
        ]
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            logger.exception("ripgrep not installed")
            return []

        if result.returncode not in (0, 1):  # 1 == no matches
            logger.warning("rg exited with %s for %s: %s", result.returncode, self.name, result.stderr)
            return []

        matches: List[RepoMatch] = []
        for line in result.stdout.splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            full_path = Path(parts[0])
            try:
                rel_path = str(full_path.resolve().relative_to(self.path))
            except ValueError:
                rel_path = str(full_path)
            try:
                line_no = int(parts[1])
            except ValueError:
                line_no = 0
            preview = parts[2].strip()
            matches.append(RepoMatch(path=rel_path, line=line_no, preview=preview))
        return matches

    def recent_commits(self, limit: int = 3) -> List[RepoCommit]:
        if not self.exists():
            return []

        cmd = [
            "git",
            "-C",
            str(self.path),
            "log",
            f"-n{limit}",
            "--pretty=format:%h%x09%an%x09%ad%x09%s",
            "--date=short",
        ]
        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            logger.warning("Failed to read commits for %s: %s", self.name, exc)
            return []

        commits: List[RepoCommit] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            commits.append(
                RepoCommit(
                    sha=parts[0],
                    author=parts[1],
                    date=parts[2],
                    message=parts[3],
                )
            )
        return commits

    def read_file(self, relative_path: str, start_line: int = 1, end_line: int = 200) -> Optional[str]:
        if not self.exists():
            return None
        file_path = self.path / relative_path
        if not file_path.exists():
            return None
        start = max(1, start_line)
        end = max(start, end_line)
        try:
            with file_path.open("r") as handle:
                lines = handle.readlines()
        except OSError:
            logger.warning("Failed to read file %s in repo %s", relative_path, self.name)
            return None
        snippet = "".join(
            lines[start - 1 : end]
        )
        return snippet


def load_default_repos(base_dir: Optional[Path] = None) -> List[LocalRepo]:
    if base_dir is not None:
        base = base_dir
    else:
        env_base = os.getenv("TRIAGE_REPO_BASE")
        if env_base:
            base = Path(env_base)
        else:
            base = Path(__file__).resolve().parents[1]
    repo_roots = {
        "adwyze": base / "adwyze",
        "adwyze-frontend": base / "adwyze-frontend",
    }
    repos: List[LocalRepo] = []
    for name, path in repo_roots.items():
        repo = LocalRepo(name=name, path=path)
        if repo.exists():
            repos.append(repo)
        else:
            logger.warning("Repo %s not found at %s", name, path)
    return repos


class RepoCache:
    def __init__(self) -> None:
        self._search_cache: Dict[Tuple[str, str], List[RepoMatch]] = {}

    def cache_search(self, repo: str, keyword: str, matches: List[RepoMatch]) -> None:
        self._search_cache[(repo, keyword)] = matches

    def get_search(self, repo: str, keyword: str) -> Optional[List[RepoMatch]]:
        return self._search_cache.get((repo, keyword))
