"""Local-only provider audit pack orchestration.

This module creates a self-contained audit/export pack from the existing
provider preflight evidence pipeline. It does not call providers, load
credentials, use the network, touch brokers, or authorize execution.
"""

from __future__ import annotations

import json
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
