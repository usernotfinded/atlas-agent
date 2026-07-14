# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    providers/provider_audit_pack.py
# PURPOSE: Assembles the shareable audit pack — the bundle a user hands to a
#          reviewer or attaches to a report. It is the export boundary, so it runs
#          the evidence index's secret and absolute-path scans before sealing.
# DEPS:    providers.provider_evidence_index (the scans), providers.provider_preflight
#          (the artifacts). Note `stat`: file permissions on the pack are set
#          deliberately, not left to the umask.
# ==============================================================================

"""Local-only provider audit pack orchestration.

This module creates a self-contained audit/export pack from the existing
provider preflight evidence pipeline. It does not call providers, load
credentials, use the network, touch brokers, or authorize execution.
"""

# --- IMPORTS ---
from __future__ import annotations

import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atlas_agent.providers.provider_evidence_index import (
    EvidenceIndexError,
    build_provider_evidence_index,
    export_provider_evidence_summary,
    generate_provider_evidence_report,
    inspect_provider_evidence_index,
)
from atlas_agent.providers.provider_preflight import (
    PreflightBundleVerificationError,
    PreflightSmokeChainError,
    PreflightValidationError,
    run_preflight_smoke_chain,
    verify_preflight_evidence_bundle,
    validate_call_plan_artifact,
)

AUDIT_PACK_FILES = [
    "call-plan.json",
    "validation-report.json",
    "manifest.json",
    "sha256sums.txt",
    "smoke-report.json",
    "evidence-index.json",
    "evidence-report.md",
    "evidence-summary.json",
    "audit-pack-manifest.json",
]

_CLOSED_SAFETY_SUMMARY = {
    "provider_call_made": False,
    "network_used": False,
    "credentials_loaded": False,
    "broker_touched": False,
    "live_trading_enabled": False,
    "pending_order_created": False,
    "order_approved": False,
}


class ProviderAuditPackError(ValueError):
    """Base error for provider audit pack creation."""


class ProviderAuditPackInputError(ProviderAuditPackError):
    """Raised when audit pack input validation fails."""


class ProviderAuditPackStageError(ProviderAuditPackError):
    """Raised when a validation, index, report, or summary stage fails."""


class ProviderAuditPackIOError(ProviderAuditPackError):
    """Raised when local input/output operations fail."""


class AuditPackVerificationError(ProviderAuditPackError):
    """Raised when audit pack verification fails."""


def _utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assert_expected_file(path: Path) -> None:
    if not path.is_file():
        raise ProviderAuditPackStageError(f"expected file was not written: {path.name}")


def _assert_relative_file_names(files: list[str]) -> None:
    for rel_path in files:
        path = Path(rel_path)
        if path.is_absolute() or path.as_posix() != path.name:
            raise ProviderAuditPackStageError("audit pack metadata must use relative file names only")


def _write_audit_pack_manifest(
    *,
    manifest_path: Path,
    provider_id: str,
    model_id: str,
    purpose: str,
    stages: dict[str, bool],
) -> dict[str, Any]:
    manifest_stages = dict(stages)
    manifest_stages["audit_pack_manifest_written"] = True
    _assert_relative_file_names(list(AUDIT_PACK_FILES))
    manifest = {
        "artifact_type": "provider_audit_pack_manifest",
        "schema_version": 1,
        "created_at": _utc_timestamp(),
        "valid": all(manifest_stages.values()),
        "provider_id": provider_id,
        "model_id": model_id,
        "purpose": purpose,
        "files": list(AUDIT_PACK_FILES),
        "stages": manifest_stages,
        "safety_summary": dict(_CLOSED_SAFETY_SUMMARY),
        "manual_review_required": True,
        "non_authorizing": True,
    }
    _write_json(manifest_path, manifest)
    return manifest


def create_provider_audit_pack(
    provider_id: str,
    model_id: str,
    purpose: str,
    max_context_chars: int,
    output_dir: Path,
) -> dict[str, Any]:
    """Create a local provider audit pack in *output_dir*.

    The pack runs the dry-run preflight chain, indexes the resulting evidence,
    renders a Markdown report, exports a compact summary, and writes a final
    audit manifest. All metadata uses relative file names inside the pack.
    """
    output_dir = Path(output_dir)
    stages = {
        "call_plan_generated": False,
        "call_plan_validated": False,
        "evidence_bundle_created": False,
        "evidence_bundle_verified": False,
        "smoke_report_written": False,
        "evidence_index_built": False,
        "evidence_report_written": False,
        "evidence_summary_written": False,
        "audit_pack_manifest_written": False,
    }

    evidence_index_path = output_dir / "evidence-index.json"
    evidence_report_path = output_dir / "evidence-report.md"
    evidence_summary_path = output_dir / "evidence-summary.json"
    audit_manifest_path = output_dir / "audit-pack-manifest.json"

    try:
        smoke_result = run_preflight_smoke_chain(
            provider_id=provider_id,
            model_id=model_id,
            purpose=purpose,
            max_context_chars=max_context_chars,
            output_dir=output_dir,
        )
    except PreflightValidationError as exc:
        raise ProviderAuditPackInputError(str(exc)) from exc
    except PreflightSmokeChainError as exc:
        raise ProviderAuditPackStageError(str(exc)) from exc
    except OSError as exc:
        raise ProviderAuditPackIOError(str(exc)) from exc

    for stage_name in (
        "call_plan_generated",
        "call_plan_validated",
        "evidence_bundle_created",
        "evidence_bundle_verified",
    ):
        stages[stage_name] = smoke_result.get("stages", {}).get(stage_name) is True

    try:
        _assert_expected_file(output_dir / "call-plan.json")
        _assert_expected_file(output_dir / "validation-report.json")
        _assert_expected_file(output_dir / "manifest.json")
        _assert_expected_file(output_dir / "sha256sums.txt")
        _assert_expected_file(output_dir / "smoke-report.json")

        verification = verify_preflight_evidence_bundle(output_dir)
        if verification.get("valid") is not True:
            raise ProviderAuditPackStageError("evidence bundle verification returned invalid")
        stages["evidence_bundle_verified"] = True

        smoke_report = json.loads((output_dir / "smoke-report.json").read_text(encoding="utf-8"))
        if smoke_report.get("valid") is not True or smoke_report.get("smoke_chain_success") is not True:
            raise ProviderAuditPackStageError("smoke report is invalid")
        stages["smoke_report_written"] = True

        index = build_provider_evidence_index(
            output_dir,
            exclude_paths=[
                evidence_index_path,
                evidence_report_path,
                evidence_summary_path,
                audit_manifest_path,
            ],
        )
        index["root"] = "."
        if index.get("findings"):
            raise ProviderAuditPackStageError("evidence index contains invalid artifacts")
        _write_json(evidence_index_path, index)
        inspect_provider_evidence_index(evidence_index_path)
        stages["evidence_index_built"] = True

        report_result = generate_provider_evidence_report(evidence_index_path, output=evidence_report_path)
        if report_result.get("is_valid") is not True:
            raise ProviderAuditPackStageError("evidence report was generated from an invalid index")
        _assert_expected_file(evidence_report_path)
        stages["evidence_report_written"] = True

        summary = export_provider_evidence_summary(evidence_index_path)
        if summary.get("valid") is not True:
            raise ProviderAuditPackStageError("evidence summary was generated from an invalid index")
        summary["source_index_path"] = "evidence-index.json"
        _write_json(evidence_summary_path, summary)
        stages["evidence_summary_written"] = True

        manifest = _write_audit_pack_manifest(
            manifest_path=audit_manifest_path,
            provider_id=provider_id,
            model_id=model_id,
            purpose=purpose,
            stages=stages,
        )
        stages["audit_pack_manifest_written"] = True
        _assert_expected_file(audit_manifest_path)
    except ProviderAuditPackError:
        raise
    except PreflightBundleVerificationError as exc:
        raise ProviderAuditPackStageError(str(exc)) from exc
    except EvidenceIndexError as exc:
        raise ProviderAuditPackStageError(str(exc)) from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProviderAuditPackStageError(f"generated evidence was not parseable: {exc}") from exc
    except OSError as exc:
        raise ProviderAuditPackIOError(str(exc)) from exc

    return {
        "valid": True,
        "output_dir": str(output_dir),
        "files": list(AUDIT_PACK_FILES),
        "stages": dict(stages),
        "manifest": manifest,
        "safety_summary": dict(_CLOSED_SAFETY_SUMMARY),
        "manual_review_required": True,
        "non_authorizing": True,
    }


def verify_provider_audit_pack(pack_dir: Path) -> dict[str, Any]:
    """Verify an existing provider audit pack.

    Checks that the pack is complete, safe, and ready for external review.
    Does not use network, credentials, or touch executing paths.
    """
    pack_dir = Path(pack_dir)
    findings = []
    checks = {
        "required_files_present": False,
        "no_symlinked_required_files": True,
        "no_extra_executable_files": True,
        "relative_paths_only": True,
        "no_absolute_paths": True,
        "no_secret_like_values": True,
        "no_raw_payload_bodies": True,
        "call_plan_valid": False,
        "bundle_valid": False,
        "smoke_report_valid": False,
        "evidence_index_valid": False,
        "evidence_summary_valid": False,
        "evidence_report_present": False,
        "audit_pack_manifest_valid": False,
        "safety_summary_closed": False,
    }

    if not pack_dir.is_dir():
        raise ProviderAuditPackIOError("pack directory does not exist or is not a directory")

    missing_files = []
    for f in AUDIT_PACK_FILES:
        p = pack_dir / f
        if not p.exists():
            missing_files.append(f)
            checks["no_symlinked_required_files"] = False
        elif p.is_symlink():
            checks["no_symlinked_required_files"] = False
            findings.append(f"required file is a symlink: {f}")

    if not missing_files:
        checks["required_files_present"] = True
    else:
        findings.append(f"missing required files: {', '.join(missing_files)}")

    exec_extensions = {
        ".sh", ".bash", ".zsh", ".fish", ".py", ".pyc", ".js", ".ts",
        ".mjs", ".cjs", ".exe", ".dll", ".dylib", ".so", ".bat", ".cmd", ".ps1"
    }

    for root, _, files in os.walk(pack_dir):
        for f in files:
            p = Path(root) / f
            rel = p.relative_to(pack_dir)
            if p.is_symlink() and rel.name not in AUDIT_PACK_FILES:
                continue
            if p.suffix in exec_extensions:
                checks["no_extra_executable_files"] = False
                findings.append(f"script/executable extension found: {rel.name}")
            else:
                try:
                    mode = p.stat().st_mode
                    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
                        checks["no_extra_executable_files"] = False
                        findings.append(f"executable permission bit set: {rel.name}")
                except OSError:
                    pass

            try:
                content = p.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                continue

            import re
            if re.search(r'\b(raw_prompt|raw_request|raw_response|prompt_body|request_body|response_body)\b', content):
                checks["no_raw_payload_bodies"] = False
                findings.append(f"raw payload body found in {rel.name}")

            if "/users/" in content or "/home/" in content or "c:\\" in content:
                checks["no_absolute_paths"] = False
                findings.append(f"absolute path found in {rel.name}")

            for sec in ("sk-ant-", "sk-proj-", "ghp_", "xoxb-", "bearer "):
                if sec in content:
                    checks["no_secret_like_values"] = False
                    findings.append(f"secret-like value found in {rel.name}")
                    break

    try:
        call_plan = json.loads((pack_dir / "call-plan.json").read_text(encoding="utf-8"))
        validate_call_plan_artifact(call_plan)
        checks["call_plan_valid"] = True
    except Exception:
        findings.append("call-plan.json is invalid")

    try:
        verification = verify_preflight_evidence_bundle(pack_dir)
        if verification.get("valid") is True:
            checks["bundle_valid"] = True
        else:
            findings.append("evidence bundle is invalid")
    except Exception:
        findings.append("evidence bundle is invalid")

    try:
        smoke = json.loads((pack_dir / "smoke-report.json").read_text(encoding="utf-8"))
        if smoke.get("valid") is True and all(smoke.get("stages", {}).values()):
            checks["smoke_report_valid"] = True
        else:
            findings.append("smoke-report.json is invalid or not all stages are true")
    except Exception:
        findings.append("smoke-report.json is malformed")

    try:
        inspect_provider_evidence_index(pack_dir / "evidence-index.json")
        checks["evidence_index_valid"] = True
    except Exception:
        findings.append("evidence-index.json is invalid")

    try:
        summary = json.loads((pack_dir / "evidence-summary.json").read_text(encoding="utf-8"))
        if summary.get("artifact_type") == "provider_evidence_index_summary":
            safety = summary.get("safety_summary", {})
            if any(safety.values()):
                findings.append("evidence-summary safety_summary is not closed")
            else:
                checks["evidence_summary_valid"] = True
        else:
            findings.append("evidence-summary artifact_type is invalid")
    except Exception:
        findings.append("evidence-summary.json is malformed")

    try:
        report_text = (pack_dir / "evidence-report.md").read_text(encoding="utf-8").lower()
        if "reviewer" in report_text or "non-authorizing" in report_text:
            checks["evidence_report_present"] = True
        else:
            findings.append("evidence-report.md missing reviewer/non-authorizing notes")
    except Exception:
        findings.append("evidence-report.md is unreadable")

    try:
        manifest = json.loads((pack_dir / "audit-pack-manifest.json").read_text(encoding="utf-8"))
        if manifest.get("artifact_type") == "provider_audit_pack_manifest" and manifest.get("valid") is True:
            if all(manifest.get("stages", {}).values()):
                safety = manifest.get("safety_summary", {})
                if not any(safety.values()):
                    checks["audit_pack_manifest_valid"] = True
                    checks["safety_summary_closed"] = True
                else:
                    findings.append("audit-pack-manifest safety_summary is not closed")
            else:
                findings.append("audit-pack-manifest has false stages")
        else:
            findings.append("audit-pack-manifest is not valid")
    except Exception:
        findings.append("audit-pack-manifest.json is malformed")

    valid = not findings and all(checks.values())

    return {
        "artifact_type": "provider_audit_pack_verification_report",
        "schema_version": 1,
        "valid": valid,
        "accepted_for_external_review": valid,
        "verified_at": _utc_timestamp(),
        "pack_dir": str(pack_dir),
        "required_files_present": checks["required_files_present"],
        "checks": checks,
        "safety_summary": dict(_CLOSED_SAFETY_SUMMARY),
        "findings": findings,
        "manual_review_required": True,
        "non_authorizing": True,
    }
