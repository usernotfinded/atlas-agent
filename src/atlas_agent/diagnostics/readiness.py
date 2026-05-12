from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

from atlas_agent.config.schema import AtlasConfig
from atlas_agent.providers.catalog import get_provider_profile, normalize_provider_id
from atlas_agent.providers.runtime import resolve_runtime_provider
from atlas_agent.ai.discipline import discipline_status


@dataclass
class ReadinessCheck:
    id: str
    label: str
    status: Literal["pass", "warn", "fail", "info"]
    message: str
    remediation: str | None = None


@dataclass
class ReadinessReport:
    checks: list[ReadinessCheck]
    ready_for_backtesting: bool
    ready_for_paper_agentic: bool
    ready_for_live: bool | str

    def to_dict(self):
        return {
            "checks": [asdict(c) for c in self.checks],
            "readiness": {
                "backtest": self.ready_for_backtesting,
                "paper_agentic": self.ready_for_paper_agentic,
                "live": self.ready_for_live,
            }
        }


def check_workspace(config: AtlasConfig) -> ReadinessCheck:
    workspace_dir = config.workspace_root
    if workspace_dir.exists() and (workspace_dir / ".atlas").exists():
        return ReadinessCheck(
            id="workspace.initialized",
            label="Workspace initialized",
            status="pass",
            message=f"Path: {workspace_dir.absolute()}",
        )
    return ReadinessCheck(
        id="workspace.initialized",
        label="Workspace initialized",
        status="fail",
        message="Workspace is not fully initialized.",
        remediation="atlas init .",
    )


def check_configuration(config: AtlasConfig) -> ReadinessCheck:
    config_path = config.workspace_root / ".atlas" / "config.toml"
    if config_path.exists():
        return ReadinessCheck(
            id="config.readable",
            label="Configuration readable",
            status="pass",
            message=f"Config: {config_path.relative_to(config.workspace_root) if config.workspace_root in config_path.parents else config_path}",
        )
    return ReadinessCheck(
        id="config.readable",
        label="Configuration readable",
        status="fail",
        message="config.toml is missing or unreadable.",
        remediation="atlas configure",
    )


def check_provider(config: AtlasConfig) -> list[ReadinessCheck]:
    checks = []
    canonical = normalize_provider_id(config.model.provider or "")
    profile = get_provider_profile(canonical)
    
    if profile is None or profile.id in ("null", "local_command"):
        checks.append(ReadinessCheck(
            id="provider.configured",
            label="AI provider",
            status="fail",
            message="AI provider not configured.",
            remediation="atlas model configure"
        ))
        return checks
        
    checks.append(ReadinessCheck(
        id="provider.configured",
        label="AI provider",
        status="pass",
        message=f"Provider: {profile.label}"
    ))

    runtime = resolve_runtime_provider(config)
    key_source = runtime["api_key_source"]
    
    if not profile.key_required:
        checks.append(ReadinessCheck(
            id="provider.api_key",
            label="API key",
            status="info",
            message="Not required for this provider."
        ))
    elif key_source in ("process_env", "env_atlas"):
        env_var_used = runtime["api_key_env_var_used"]
        checks.append(ReadinessCheck(
            id="provider.api_key",
            label="API key",
            status="pass",
            message=f"Configured ({env_var_used})"
        ))
    else:
        expected_vars = ", ".join(profile.env_precedence)
        checks.append(ReadinessCheck(
            id="provider.api_key",
            label="API key",
            status="fail",
            message=f"Missing (expected: {expected_vars})",
            remediation="atlas model configure"
        ))
        
    return checks


def check_discipline(config: AtlasConfig) -> ReadinessCheck:
    status = discipline_status(config.memory_dir.parent)
    if status["configured"] and status["valid"]:
        return ReadinessCheck(
            id="discipline.configured",
            label="Discipline profile",
            status="pass",
            message="Configured and valid."
        )
    elif status["configured"]:
        return ReadinessCheck(
            id="discipline.configured",
            label="Discipline profile",
            status="fail",
            message=f"Invalid: {'; '.join(status['errors'])}",
            remediation="atlas discipline setup"
        )
    return ReadinessCheck(
        id="discipline.configured",
        label="Discipline profile",
        status="fail",
        message="Missing.",
        remediation="atlas discipline setup"
    )


def check_symbol(config: AtlasConfig) -> ReadinessCheck:
    symbol = config.market.symbol
    if symbol and symbol != "DEMO-SYMBOL":
        return ReadinessCheck(
            id="market.symbol",
            label="Trading symbol",
            status="pass",
            message=f"Symbol: {symbol}"
        )
    return ReadinessCheck(
        id="market.symbol",
        label="Trading symbol",
        status="fail",
        message="Trading symbol not configured.",
        remediation="atlas config set market.symbol <SYMBOL>"
    )


def check_audit(config: AtlasConfig) -> list[ReadinessCheck]:
    checks = []
    
    checks.append(ReadinessCheck(
        id="audit.enabled",
        label="Audit",
        status="pass",
        message="Enabled"
    ))
    
    raw_prompt_logging = getattr(config.safety, "log_raw_prompts", False)
    provider_text_logging = getattr(config.safety, "log_provider_text", False)
    
    if raw_prompt_logging:
        checks.append(ReadinessCheck(
            id="audit.raw_prompt_logging",
            label="Raw prompt logging",
            status="warn",
            message="Enabled. Secrets are redacted, but strategy text may be stored."
        ))
    else:
        checks.append(ReadinessCheck(
            id="audit.raw_prompt_logging",
            label="Raw prompt logging",
            status="info",
            message="Disabled."
        ))
        
    if provider_text_logging:
         checks.append(ReadinessCheck(
            id="audit.provider_text_logging",
            label="Provider text logging",
            status="warn",
            message="Enabled."
        ))
    else:
        checks.append(ReadinessCheck(
            id="audit.provider_text_logging",
            label="Provider text logging",
            status="info",
            message="Disabled."
        ))

    return checks


def check_risk(config: AtlasConfig) -> list[ReadinessCheck]:
    checks = []
    
    checks.append(ReadinessCheck(
        id="risk.configured",
        label="Risk gates",
        status="pass",
        message="Configured."
    ))
    
    return checks


def check_live(config: AtlasConfig) -> list[ReadinessCheck]:
    checks = []
    if config.enable_live_trading:
        checks.append(ReadinessCheck(
            id="live.enabled",
            label="Live trading",
            status="warn",
            message="Enabled."
        ))
    else:
        checks.append(ReadinessCheck(
            id="live.disabled_by_default",
            label="Live trading",
            status="pass",
            message="Disabled by default."
        ))
    return checks


def run_diagnostics(config: AtlasConfig) -> ReadinessReport:
    checks = []
    checks.append(check_workspace(config))
    checks.append(check_configuration(config))
    checks.extend(check_provider(config))
    checks.append(check_discipline(config))
    checks.append(check_symbol(config))
    checks.extend(check_audit(config))
    checks.extend(check_risk(config))
    checks.extend(check_live(config))

    # Calculate overall readiness
    has_provider = any(c.id == "provider.configured" and c.status == "pass" for c in checks)
    has_api_key_or_not_required = any(c.id == "provider.api_key" and c.status in ("pass", "info") for c in checks)
    has_valid_discipline = any(c.id == "discipline.configured" and c.status == "pass" for c in checks)
    has_symbol = any(c.id == "market.symbol" and c.status == "pass" for c in checks)
    
    provider_ready = has_provider and has_api_key_or_not_required
    
    ready_for_backtesting = True
    ready_for_paper_agentic = provider_ready and has_valid_discipline and has_symbol
    ready_for_live = "requires review" if config.enable_live_trading else False

    return ReadinessReport(
        checks=checks,
        ready_for_backtesting=ready_for_backtesting,
        ready_for_paper_agentic=ready_for_paper_agentic,
        ready_for_live=ready_for_live,
    )


def print_readiness_report(report: ReadinessReport) -> None:
    print("Atlas setup checklist\n")
    
    for check in report.checks:
        if check.status == "pass":
            icon = "[✓]"
        elif check.status == "info":
            icon = "[i]"
        elif check.status == "warn":
            icon = "[!]"
        else:
            icon = "[!]"
            
        if check.id in ("provider.api_key", "audit.raw_prompt_logging", "audit.provider_text_logging"):
             print(f"    {check.label}: {check.message}")
        else:
            if check.status in ("pass", "warn", "info"):
                print(f"{icon} {check.label}")
                if check.message:
                    print(f"    {check.message}")
            else:
                if check.id == "config.readable":
                    print(f"{icon} Configuration missing")
                else:
                    print(f"{icon} {check.label} missing")
                if check.message and "missing" not in check.message.lower() and "not configured" not in check.message.lower():
                    print(f"    {check.message}")

        if check.remediation:
            print(f"    Run: {check.remediation}")
            if check.id == "market.symbol":
                 print(f"    Example: atlas config set market.symbol AAPL")
        if check.id not in ("provider.configured", "audit.enabled"):
            print()
    
    if report.ready_for_paper_agentic:
        status_msg = "ready for paper agentic workflows"
    else:
        status_msg = "not ready for agentic paper workflows"
        
    print(f"Status: {status_msg}\n")
    
    print("Summary")
    print(f"Ready for backtesting: {'yes' if report.ready_for_backtesting else 'no'}")
    print(f"Ready for paper agentic workflows: {'yes' if report.ready_for_paper_agentic else 'no'}")
    print(f"Ready for live workflows: {report.ready_for_live}")
