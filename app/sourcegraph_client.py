from __future__ import annotations

import logging
import re
from typing import List, Optional

import requests

from .config import settings

logger = logging.getLogger(__name__)

SEARCH_QUERY = """
query Search($query: String!) {
  search(query: $query, version: V3) {
    results {
      matchCount
      results {
        __typename
        ... on FileMatch {
          repository { name }
          file { path }
          lineMatches {
            lineNumber
            offsetAndLengths
            line
          }
        }
      }
    }
  }
}
"""


class SourcegraphMatch:
    def __init__(self, repo: str, path: str, line: int, preview: str) -> None:
        self.repo = repo
        self.path = path
        self.line = line
        self.preview = preview


class SourcegraphClient:
    def __init__(self, url: Optional[str], token: Optional[str]) -> None:
        self.url = url.rstrip("/") if url else None
        self.token = token

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.token)

    def search(
        self,
        repo: str,
        keyword: str,
        directories: Optional[List[str]] = None,
        limit: int = 3,
    ) -> List[SourcegraphMatch]:
        if not self.enabled or not keyword:
            return []

        dir_filter = ""
        if directories:
            escaped = [re.escape(d.rstrip("/")) for d in directories]
            dir_filter = " (" + " OR ".join(f'file:^{"%s" % d}/' for d in escaped) + ")"

        query_string = f'repo:^{"%s" % repo}$ "{keyword}" count:{limit}{dir_filter}'
        try:
            response = requests.post(
                f"{self.url}/.api/graphql",
                json={"query": SEARCH_QUERY, "variables": {"query": query_string}},
                headers={"Authorization": f"token {self.token}"},
                timeout=15,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Sourcegraph search failed: %s", exc)
            return []

        data = response.json()
        results = data.get("data", {}).get("search", {}).get("results", {}).get("results", [])
        matches: List[SourcegraphMatch] = []
        for result in results:
            if result.get("__typename") != "FileMatch":
                continue
            repo_name = result["repository"]["name"]
            file_path = result["file"]["path"]
            for line_match in result.get("lineMatches", []):
                matches.append(
                    SourcegraphMatch(
                        repo=repo_name,
                        path=file_path,
                        line=line_match["lineNumber"],
                        preview=line_match["line"].strip(),
                    )
                )
                if len(matches) >= limit:
                    return matches
        return matches
