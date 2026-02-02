from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from .repo import LocalRepo, RepoMatch, RepoCommit, load_default_repos, RepoCache
from .sourcegraph_client import SourcegraphClient, SourcegraphMatch

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Thin facade over local repositories. Later this can wrap GitHub search,
    Metabase queries, etc.
    """

    def __init__(self, repos: Optional[List[LocalRepo]] = None, sourcegraph: Optional[SourcegraphClient] = None) -> None:
        self.repos = repos or load_default_repos()
        self.repo_map: Dict[str, LocalRepo] = {repo.name: repo for repo in self.repos}
        self.cache = RepoCache()
        self.sourcegraph = sourcegraph
        logger.info("Tool registry ready for repos: %s", ", ".join(self.repo_map.keys()))

    def _repo(self, name: str) -> Optional[LocalRepo]:
        repo = self.repo_map.get(name)
        if not repo:
            logger.warning("Requested repo %s not found in registry", name)
        return repo

    def list_repos(self) -> List[str]:
        return list(self.repo_map.keys())

    def search_code(
        self,
        repo_name: str,
        query: str,
        limit: int = 3,
        directories: Optional[List[str]] = None,
    ) -> List[RepoMatch]:
        repo = self._repo(repo_name)
        if not repo:
            return []
        cached = self.cache.get_search(repo_name, query)
        if cached is not None:
            return cached[:limit]
        matches: List[RepoMatch] = []
        if self.sourcegraph and self.sourcegraph.enabled:
            logger.debug(
                "Sourcegraph search repo=%s query=%s dirs=%s",
                repo_name,
                query,
                directories,
            )
            sg_matches = self.sourcegraph.search(repo_name, query, directories=directories, limit=limit)
            for match in sg_matches:
                matches.append(
                    RepoMatch(path=match.path, line=match.line, preview=match.preview)
                )
            if sg_matches:
                logger.debug("Sourcegraph returned %s matches for %s", len(sg_matches), query)
        if not matches:
            matches = repo.search(query, limit=limit)
            logger.debug("ripgrep returned %s matches for %s", len(matches), query)
        self.cache.cache_search(repo_name, query, matches)
        return matches

    def read_file(self, repo_name: str, path: str, start: int = 1, end: int = 200) -> Optional[str]:
        repo = self._repo(repo_name)
        if not repo:
            return None
        return repo.read_file(path, start_line=start, end_line=end)

    def recent_commits(self, repo_name: str, limit: int = 3) -> List[RepoCommit]:
        repo = self._repo(repo_name)
        if not repo:
            return []
        return repo.recent_commits(limit=limit)


@dataclass
class ToolResult:
    description: str
    content: str
