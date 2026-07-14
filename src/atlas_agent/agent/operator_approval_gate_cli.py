# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    agent/operator_approval_gate_cli.py
# PURPOSE: CONFIGLESS entry point for `atlas agent operator-approval-gate`. Routed
#          directly by cli_bootstrap.py, bypassing the main CLI entirely.
# DEPS:    stdlib only (argparse, json) + the approval-gate engine.
#
# WARNING: One of the four trust-contract commands — see the note in
#          bounded_live_autonomy_readiness_cli.py. No config, no heavy imports.
# ==============================================================================

# --- IMPORTS ---
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas_agent.agent.operator_approval_gate import (
    OperatorApprovalGateInputs,
    OperatorApprovalGateValidationError,
    build_operator_approval_gate_report,
    write_operator_approval_gate_artifacts,
)


CLI_DESCRIPTION = """\
Operator approval gate evaluation (CAND-008) — evidence-only, simulated-only.

This command consumes CAND-004 trading-quality evidence, CAND-005 shadow-live
comparison evidence, CAND-006 gated submit conformance evidence, CAND-007 runtime
readiness envelope evidence, and CAND-008-owned static local fixtures. It
evaluates them in strict fail-closed order and records an operator approval gate
artifact if every gate passes.

This command does not submit orders, does not call broker or provider APIs, does
not load credentials, does not create real or pending orders, does not import
Order/OrderRouter/RiskManager/ApprovalManager/runtime kill switch, and does not
claim live readiness, trading safety, or permission to submit orders.
"""

_UNSAFE_FLAGS = {
    "--live",
    "--submit",
    "--broker",
    "--provider",
    "--api-key",
    "--credentials",
    "--endpoint",
    "--account",
    "--account-id",
    "--client-order-id",
    "--place-order",
    "--order-router",
    "--risk-manager",
    "--mode",
    "--kill-switch-override",
    "--approve-live",
    "--approve-submit",
    "--trade",
    "--execute",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas agent operator-approval-gate",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--quality-gate", required=True)
    parser.add_argument("--shadow-comparison", required=True)
    parser.add_argument("--submit-conformance", required=True)
    parser.add_argument("--readiness-envelope", required=True)
    parser.add_argument("--operator-identity", required=True)
    parser.add_argument("--approval-policy", required=True)
    parser.add_argument("--kill-switch-observation", required=True)
    parser.add_argument("--operator-acknowledgment", required=True)
    parser.add_argument("--audit-policy", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _print_text_report(report: Any) -> None:
    print(f"status: {report.status}")
    print(f"evaluation_id: {report.evaluation_id}")
    print(f"as_of: {report.as_of}")
    print(f"symbol: {report.symbol or '-'}")
    print(f"run_id: {report.run_id or '-'}")
    print(f"input_digest: {report.input_digest}")
    print(f"approval_gate_digest: {report.approval_gate_digest}")
    print("gates:")
    for gate in report.gates:
        reason = f" ({gate.reason})" if gate.reason else ""
        print(f"  {gate.gate_id}: {gate.status}{reason}")
    if report.blockers:
        print("blockers:")
        for reason in report.blockers:
            print(f"  - {reason}")
    if report.status == "operator_gate_recorded":
        print("artifacts recorded.")


def _reject_unsafe_flags(argv: list[str] | None) -> int:
    args = argv if argv is not None else []
    for token in args:
        name = token.split("=", 1)[0]
        if name in _UNSAFE_FLAGS:
            print(f"error: unsafe flag rejected: {name}", file=sys.stderr)
            return 2
    return 0


def _resolve_unique_id(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.resolve().stat()
        return (stat.st_dev, stat.st_ino)
    except Exception:
        return None


def _check_path_aliasing(inputs: OperatorApprovalGateInputs, output_dir: Path) -> None:
    output_dir_id = _resolve_unique_id(output_dir)
    input_paths = [
        inputs.quality_gate_path,
        inputs.shadow_comparison_path,
        inputs.submit_conformance_path,
        inputs.readiness_envelope_path,
        inputs.operator_identity_path,
        inputs.approval_policy_path,
        inputs.kill_switch_observation_path,
        inputs.operator_acknowledgment_path,
        inputs.audit_policy_path,
    ]
    for path in input_paths:
        path_id = _resolve_unique_id(path)
        if path_id is not None and path_id == output_dir_id:
            raise OperatorApprovalGateValidationError(
                f"output_dir aliases input path: {path.name}"
            )


def main(argv: list[str] | None = None) -> int:
    reject_code = _reject_unsafe_flags(argv)
    if reject_code != 0:
        return reject_code
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    inputs = OperatorApprovalGateInputs(
        quality_gate_path=Path(args.quality_gate),
        shadow_comparison_path=Path(args.shadow_comparison),
        submit_conformance_path=Path(args.submit_conformance),
        readiness_envelope_path=Path(args.readiness_envelope),
        operator_identity_path=Path(args.operator_identity),
        approval_policy_path=Path(args.approval_policy),
        kill_switch_observation_path=Path(args.kill_switch_observation),
        operator_acknowledgment_path=Path(args.operator_acknowledgment),
        audit_policy_path=Path(args.audit_policy),
        output_dir=Path(args.output_dir),
        as_of=args.as_of,
    )

    try:
        _check_path_aliasing(inputs, inputs.output_dir)
        report = build_operator_approval_gate_report(inputs)
        if report.status == "operator_gate_synthesized":
            report = write_operator_approval_gate_artifacts(report, inputs.output_dir)
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {"status": "not_evaluated", "error": str(exc), "exit_code": 2},
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print("status: not_evaluated")
            print(f"error: {exc}")
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_text_report(report)

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
