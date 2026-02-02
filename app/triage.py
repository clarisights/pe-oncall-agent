from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import List, Optional, Dict, Any

from .analyzer import BasicAnalyzer
from .llm import LLMAgent
from .models import TriageRequest
from .tools import ToolRegistry, ToolResult

logger = logging.getLogger(__name__)


SERVICE_HINTS = {
    "google_ads_breakdowns": {
        "repos": ["adwyze"],
        "directories": [
            "app/models/base_adwords_segment_type.rb",
            "app/models/base_adwords_segment_report.rb",
            "app/annotators/adwords/base_adwords_segment_tag_annotator.rb",
            "app/adwords/adwords/api/client.rb",
        ],
        "runbook": "docs/adding_new_breakdown.md",
        "keywords": ["Google Ads", "AdWords", "breakdown", "segment"],
        "topic_matches": ["google-ads", "gaql-breakdowns"],
    },
    "custom_analytics_dereferencing": {
        "repos": ["adwyze"],
        "directories": [
            "config/channels",
            "app/models/taboola_ad_account.rb",
            "lib/ad_references_module",
        ],
        "runbook": "docs/ca_integration.md",
        "keywords": ["custom analytics", "CA", "deref", "channel schema"],
        "topic_matches": ["custom-analytics", "ca-deref"],
    },
    "vibetv_custom_channel": {
        "repos": ["adwyze"],
        "directories": [
            "app/vibe_tv/vibe_tv/client.rb",
            "lib/vibe_tv_input_source.rb",
            "private/schemas/custom_channel/v1/vibe_tv.json",
            "python/ingestion_pipeline/airflow/dags/dags/generated/custom_advertising/vibe_tv.py",
        ],
        "runbook": "docs/vibetv_integration.md",
        "keywords": ["VibeTV", "CTV channel", "async report", "Pi CADV"],
        "topic_matches": ["vibetv"],
    },
    "mediago_custom_channel": {
        "repos": ["adwyze"],
        "directories": [
            "app/mediago/mediago/client.rb",
            "lib/mediago_input_source.rb",
            "private/schemas/custom_channel/v1/mediago.json",
            "python/ingestion_pipeline/airflow/dags/dags/generated/custom_advertising/mediago.py",
        ],
        "runbook": "docs/mediago_integration.md",
        "keywords": ["MediaGo", "Baidu", "custom channel", "Pi CADV"],
        "topic_matches": ["mediago"],
    },
    "picadv_ad_previews": {
        "repos": ["adwyze"],
        "directories": [
            "app/annotators/custom_advertising/custom_advertising_ad_tag_annotator.rb",
            "app/custom_advertising/base_custom_advertising_object.rb",
            "lib/creative_preview/base_pi_preview.rb",
            "lib/creative_preview/facebook_preview.rb",
            "lib/creative_preview/tiktok_preview.rb",
        ],
        "runbook": "PI-CADV Ad Preview Framework.md",
        "keywords": ["ad preview", "creative preview", "PI CADV", "custom advertising"],
        "topic_matches": ["ad-preview", "pi-cadv-previews"],
    },
    # Frontend/service hints can be appended below once generated.
    "dashboard_reporting": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/dashboard/components/Report.tsx",
            "src/apps/dashboard/actions",
            "src/apps/dashboard/sagas",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["dashboard", "reports", "widgets", "report tabs", "shared report"],
        "topic_matches": ["/dashboard", "/r/:id", "scheduled-report"],
    },
    "integrations_control_center": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/Integrations/MainIntegrationsPage.tsx",
            "src/apps/Integrations/components",
            "src/apps/Integrations/sagas",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["integrations", "connections", "onboarding", "ad accounts", "connected channels"],
        "topic_matches": ["/integrations", "ad_accounts", "onboarding"],
    },
    "custom_metrics_workspace": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/CustomMetricsNew/MetricsPage.tsx",
            "src/apps/CustomMetricsNew/MetricsGroups",
            "src/apps/CustomMetricsNew/Metric",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["custom metrics", "metric builder", "metric groups", "kpi definitions"],
        "topic_matches": ["custom-metrics", "metric-groups"],
    },
    "custom_dimensions_workspace": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/CustomDimensionsV2/components",
            "src/apps/CustomDimensionsV2/sagas",
            "src/apps/CustomDimensionsV2/api.ts",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["custom dimensions", "dimension builder", "attributes", "data enrichment"],
        "topic_matches": ["custom-dimensions"],
    },
    "preferences_center": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/Preferences/components",
            "src/apps/Preferences/services",
            "src/apps/Preferences/index.jsx",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["preferences", "teams", "roles", "segments", "notifications"],
        "topic_matches": ["/dashboard/preferences", "manage-users", "teams"],
    },
    "agency_portal": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/agency/AgencyContainer.jsx",
            "src/apps/agency/actions",
            "src/apps/login/AgencyLogin.jsx",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["agency portal", "user agencies", "agency login", "partner onboarding"],
        "topic_matches": ["user_agencies", "agency-login", "agency-sign-up"],
    },
    "admin_console_and_tools": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/admins",
            "src/apps/adminTools/ReportDuplicator",
            "src/apps/adminTools/BrowseGCS",
            "src/apps/adminTools/ManageProjectionMetrics",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["admin", "company management", "report duplicator", "gcs browser", "projection metrics"],
        "topic_matches": ["/admins", "admin-tools", "company-preferences"],
    },
    "data_quality_sanity_checker": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/SanityChecker/SanityCheckCreator.jsx",
            "src/apps/SanityChecker/SanityCheckerDataModal.tsx",
            "src/apps/SanityChecker/AdvertisingBackfill.jsx",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["sanity checker", "data quality", "backfill", "sanity checks"],
        "topic_matches": ["sanity-checker", "backfill"],
    },
    "internal_query_consoles": {
        "repos": ["adwyze-frontend"],
        "directories": [
            "src/apps/Querier",
            "src/apps/adminTools/SnowflakeQuerier/SnowflakeQuerier.tsx",
            "src/apps/adminTools/DataExporterLogs",
        ],
        "runbook": "https://github.com/adwyze/adwyze-frontend/wiki",
        "keywords": ["bigquery", "snowflake", "admin query", "data exporter logs"],
        "topic_matches": ["query-bigquery", "query-snowflake", "data-exporter"],
    },
}

# Map common stream/topic names to services.
STREAM_TOPIC_HINTS = {
    "google-ads": "google_ads_breakdowns",
    "gaql-breakdowns": "google_ads_breakdowns",
    "custom-analytics": "custom_analytics_dereferencing",
    "ca-deref": "custom_analytics_dereferencing",
    "vibetv": "vibetv_custom_channel",
    "mediago": "mediago_custom_channel",
    "ad-preview": "picadv_ad_previews",
    "pi-cadv-previews": "picadv_ad_previews",
    "/dashboard": "dashboard_reporting",
    "/r/:id": "dashboard_reporting",
    "scheduled-report": "dashboard_reporting",
    "/integrations": "integrations_control_center",
    "ad_accounts": "integrations_control_center",
    "onboarding": "integrations_control_center",
    "custom-metrics": "custom_metrics_workspace",
    "metric-groups": "custom_metrics_workspace",
    "custom-dimensions": "custom_dimensions_workspace",
    "/dashboard/preferences": "preferences_center",
    "manage-users": "preferences_center",
    "teams": "preferences_center",
    "user_agencies": "agency_portal",
    "agency-login": "agency_portal",
    "agency-sign-up": "agency_portal",
    "/admins": "admin_console_and_tools",
    "admin-tools": "admin_console_and_tools",
    "company-preferences": "admin_console_and_tools",
    "sanity-checker": "data_quality_sanity_checker",
    "backfill": "data_quality_sanity_checker",
    "query-bigquery": "internal_query_consoles",
    "query-snowflake": "internal_query_consoles",
    "data-exporter": "internal_query_consoles",
}


class ToolOrchestrator:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry
        self.include_commits = os.getenv("TRIAGE_INCLUDE_COMMITS", "false").lower() == "true"

    def gather(self, request: TriageRequest) -> List[ToolResult]:
        findings: List[ToolResult] = []
        aggregate_text = " ".join(
            [request.incident_text]
            + request.thread_context
            + ([request.topic] if request.topic else [])
        )
        keywords = _extract_keywords(aggregate_text)
        hints = self._resolve_service_hints(keywords, request.topic)
        logger.info(
            "Resolved service hints repos=%s runbook=%s directories=%s keywords=%s",
            hints["repos"],
            hints["runbook"],
            hints["directories"],
            keywords,
        )

        for repo in hints["repos"]:
            allowed_dirs = hints["directories"].get(repo, [])
            if not allowed_dirs:
                allowed_dirs = self._dynamic_directories(repo, keywords)
            logger.debug("Using directories for %s: %s", repo, allowed_dirs)
            for keyword in keywords or ["incident"]:
                matches = self.registry.search_code(
                    repo,
                    keyword,
                    limit=2,
                    directories=allowed_dirs or None,
                )
                logger.debug(
                    "Search results repo=%s keyword=%s count=%s",
                    repo,
                    keyword,
                    len(matches),
                )
                for match in matches:
                    if allowed_dirs and not any(match.path.startswith(prefix) for prefix in allowed_dirs):
                        continue
                    snippet = self.registry.read_file(repo, match.path, match.line - 3, match.line + 3)
                    content = snippet or match.preview
                    findings.append(
                        ToolResult(
                            description=f"{repo}:{match.path}:{match.line}",
                            content=content.strip(),
                        )
                    )

            if self.include_commits:
                commits = self.registry.recent_commits(repo, limit=2)
                for commit in commits:
                    findings.append(
                        ToolResult(
                            description=f"{repo} recent commit {commit.sha}",
                            content=f"{commit.date} {commit.author}: {commit.message}",
                        )
                    )

        if hints["runbook"]:
            findings.append(
                ToolResult(
                    description="Runbook hint",
                    content=f"Consult runbook: {hints['runbook']}",
                )
            )
        if findings:
            logger.info(
                "Gathered %s tool results; sample=%s",
                len(findings),
                [f.description for f in findings[:5]],
            )
        else:
            logger.info("No tool results gathered")

        return findings

    def _resolve_service_hints(self, keywords: List[str], topic: Optional[str]) -> Dict[str, Any]:
        runbook: Optional[str] = None
        directories: Dict[str, List[str]] = {}
        repos = self.registry.list_repos()
        for repo in repos:
            directories.setdefault(repo, [])
        return {"repos": repos, "runbook": runbook, "directories": directories}

    def _dynamic_directories(self, repo: str, keywords: List[str], max_dirs: int = 5) -> List[str]:
        counter: Counter[str] = Counter()
        for keyword in keywords:
            matches = self.registry.search_code(repo, keyword, limit=3)
            for match in matches:
                parts = match.path.split("/")
                directory = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
                if directory:
                    counter[directory] += 1
        top_dirs = [directory for directory, _ in counter.most_common(max_dirs) if directory]
        return top_dirs


STOP_WORDS = {
    "probabl",
    "triage",
    "issue",
    "issues",
    "please",
    "thanks",
    "thank",
    "hello",
    "hey",
    "team",
    "update",
    "updated",
    "cc",
    "clarisights",
}
KEYWORD_LIMIT = int(os.getenv("TRIAGE_KEYWORD_LIMIT", "12"))
TOKEN_RE = re.compile(r"[a-z0-9_-]{2,}")


def _extract_keywords(text: str) -> List[str]:
    tokens = TOKEN_RE.findall(text.lower())
    counts: Counter[str] = Counter()
    for token in tokens:
        if token in STOP_WORDS:
            continue
        if token.isdigit():
            continue
        counts[token] += 1
    return [token for token, _ in counts.most_common(KEYWORD_LIMIT)]


class TriageService:
    def __init__(self, analyzer: BasicAnalyzer, llm_agent: LLMAgent, orchestrator: ToolOrchestrator) -> None:
        self.analyzer = analyzer
        self.llm_agent = llm_agent
        self.orchestrator = orchestrator

    def run(self, request: TriageRequest) -> str:
        tool_results = self.orchestrator.gather(request)
        llm_summary: Optional[str] = None
        if self.llm_agent.enabled:
            llm_summary = self.llm_agent.run(request, tool_results=tool_results)
            if llm_summary:
                return llm_summary

        logger.info("LLM unavailable or returned no result; falling back to keyword analyzer.")
        combined = request.combined_text()
        return self.analyzer.analyze(combined)
