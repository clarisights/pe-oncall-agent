from __future__ import annotations

import os
from configparser import ConfigParser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Settings:
    zulip_site: str
    zulip_email: str
    zulip_api_key: str
    default_stream: Optional[str] = None
    default_topic: Optional[str] = None
    llm_model: Optional[str] = None
    codex_cli: str = "codex"
    node_cli: str = "node"
    codex_api_key: Optional[str] = None
    sourcegraph_url: Optional[str] = None
    sourcegraph_token: Optional[str] = None

    @classmethod
    def load(cls, zuliprc_path: str = ".zuliprc") -> "Settings":
        """
        Load settings from environment variables with fallback to the
        classic Zulip .zuliprc file so local development works out of the box.
        """
        env_site = os.getenv("ZULIP_SITE")
        env_email = os.getenv("ZULIP_EMAIL")
        env_key = os.getenv("ZULIP_API_KEY")

        if env_site and env_email and env_key:
            return cls(
                zulip_site=env_site,
                zulip_email=env_email,
                zulip_api_key=env_key,
                default_stream=os.getenv("TRIAGE_DEFAULT_STREAM"),
                default_topic=os.getenv("TRIAGE_DEFAULT_TOPIC"),
                llm_model=os.getenv("LLM_MODEL"),
                codex_cli=os.getenv("CODEX_CLI_PATH", "codex"),
                node_cli=os.getenv("NODE_CLI_PATH", "node"),
                codex_api_key=os.getenv("CODEX_API_KEY"),
                sourcegraph_url=os.getenv("SOURCEGRAPH_URL"),
                sourcegraph_token=os.getenv("SOURCEGRAPH_TOKEN"),
            )

        config = ConfigParser()
        rc_file = Path(zuliprc_path)
        if not rc_file.exists():
            raise RuntimeError(
                "Zulip credentials not found. Set ZULIP_* env vars or add a .zuliprc file."
            )

        config.read(rc_file)
        if "api" not in config:
            raise RuntimeError(".zuliprc missing [api] section")

        section = config["api"]
        return cls(
            zulip_site=section.get("site", ""),
            zulip_email=section.get("email", ""),
            zulip_api_key=section.get("key", ""),
            default_stream=os.getenv("TRIAGE_DEFAULT_STREAM"),
            default_topic=os.getenv("TRIAGE_DEFAULT_TOPIC"),
            llm_model=os.getenv("LLM_MODEL"),
            codex_cli=os.getenv("CODEX_CLI_PATH", "codex"),
            node_cli=os.getenv("NODE_CLI_PATH", "node"),
            codex_api_key=os.getenv("CODEX_API_KEY"),
            sourcegraph_url=os.getenv("SOURCEGRAPH_URL"),
            sourcegraph_token=os.getenv("SOURCEGRAPH_TOKEN"),
        )


settings = Settings.load()
