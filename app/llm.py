from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from .config import settings
from typing import List, Optional

from .models import TriageRequest
from .tools import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


class LLMAgent:
    """
    Wrapper around the Codex CLI (`codex exec`). Falls back to keyword analyzer when
    login/CLI is unavailable.
    """

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.model = settings.llm_model
        self.node_cmd = settings.node_cli
        resolved_node = shutil.which(self.node_cmd)
        if not resolved_node:
            logger.warning(
                "Node CLI '%s' not found on PATH; Codex CLI cannot run.", self.node_cmd
            )
        self.node_path = resolved_node
        requested = settings.codex_cli
        resolved = shutil.which(requested)
        if not resolved:
            logger.warning("Codex CLI '%s' not found on PATH; LLM triage disabled.", requested)
        self.cli_path = resolved
        self.api_key = settings.codex_api_key
        self.logged_in = (
            self._ensure_login() if self.cli_path and self.node_path else False
        )

    @property
    def enabled(self) -> bool:
        return bool(self.cli_path and self.node_path and self.logged_in)

    def _run_command(self, cmd: List[str], label: str) -> bool:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            logger.error("%s command missing (%s)", label, cmd[0])
            return False
        except Exception:
            logger.exception("Failed to execute %s", label)
            return False
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            logger.error("%s failed (%s): %s", label, result.returncode, detail)
            return False
        detail = result.stdout.strip() or result.stderr.strip()
        if detail:
            logger.info("%s ok: %s", label, detail.splitlines()[0])
        else:
            logger.info("%s ok", label)
        return True

    def _ensure_login(self) -> bool:
        if not self._run_command([self.node_path, "--version"], "node --version"):
            return False
        if not self._run_command([self.cli_path, "--version"], "codex --version"):
            return False
        if self._check_login():
            return True
        if not self.api_key:
            logger.warning("CODEX_API_KEY not set; cannot auto-login Codex CLI.")
            return False
        try:
            result = subprocess.run(
                [self.cli_path, "login", "--with-api-key"],
                input=self.api_key + os.linesep,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            logger.exception("Failed to execute 'codex login --with-api-key'")
            return False
        if result.returncode != 0:
            logger.error("Codex login failed: %s", result.stderr.strip())
            return False
        return self._check_login()

    def _check_login(self) -> bool:
        if not self.cli_path:
            return False
        try:
            result = subprocess.run(
                [self.cli_path, "login", "status"],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            logger.exception("Failed to check Codex login status")
            return False
        if result.returncode == 0:
            logger.info("Codex CLI login verified.")
            return True
        logger.warning("Codex CLI login status non-zero: %s", result.stderr.strip())
        return False

    def run(self, request: TriageRequest, tool_results: Optional[List[ToolResult]] = None) -> Optional[str]:
        if not self.enabled:
            return None

        prompt_lines = [
            "You are an engineering on-call assistant responding over Zulip. Use the evidence below to propose the most likely root cause, explicitly call out unknowns, and ask for clarification if critical data is missing.",
            "",
            "Incident:",
            request.incident_text,
            "",
        ]
        if request.thread_context:
            prompt_lines.append("Thread context:")
            prompt_lines.extend(request.thread_context[-8:])
            prompt_lines.append("")
        if tool_results:
            prompt_lines.append("Evidence from tools:")
            for result in tool_results[:5]:
                prompt_lines.append(f"{result.description}\n{result.content}\n")
        prompt_lines.append(
            "Respond in Markdown with sections: **Finding** (state HIGH/MED/LOW confidence and justify it), **Evidence** (cite repo paths or runbooks), **Next steps**, and **Open questions** when you need more info. If confidence would be LOW, prefer to explain what additional data is needed before making a definitive claim."
        )
        prompt = "\n".join(prompt_lines)

        with tempfile.NamedTemporaryFile(mode="r+", delete=True) as outfile:
            cmd = [
                self.cli_path,
                "exec",
                "--skip-git-repo-check",
                "--output-last-message",
                outfile.name,
                "--color",
                "never",
            ]
            if self.model:
                cmd.extend(["--model", self.model])
            cmd.append(prompt)

            try:
                logger.info("Invoking Codex CLI with prompt length %s characters", len(prompt))
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                logger.exception("Failed to invoke Codex CLI")
                return None

            if result.returncode != 0:
                logger.error("Codex exec failed (%s): %s", result.returncode, result.stderr.strip())
                return None

            outfile.seek(0)
            content = outfile.read().strip()
            logger.debug("Codex response length %s characters", len(content))
            return content or None
