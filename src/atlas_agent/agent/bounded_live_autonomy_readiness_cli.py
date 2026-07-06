from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas_agent.agent.bounded_live_autonomy_readiness import (
    BoundedLiveAutonomyReadinessInputs,
    BoundedLiveAutonomyReadinessValidationError,
    build_bounded_live_autonomy_readiness_report,
    write_bounded_live_autonomy_readiness_artifacts,
)


CLI_DESCRIPTION = """\
Bounded live autonomy readiness evaluation (CAND-015) — evidence-only, simulated-only.

This command consumes CAND-004 trading-quality evidence, CAND-005 shadow-live
comparison evidence, CAND-006 gated submit conformance evidence, CAND-007 runtime
readiness envelope evidence, CAND-008 operator approval gate evidence, and
CAND-015-owned static local fixtures. It evaluates them in strict fail-closed
order and records a bounded live autonomy readiness artifact if every gate passes.

This command does not submit orders, does not call broker or provider APIs, does
not load credentials, does not create real or pending orders, does not import
Order/OrderRouter/RiskManager/ApprovalManager/runtime kill switch, and does not
claim live readiness, trading safety, permission to trade, or authorization to
submit orders.
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
    "--enable-l3",
    "--l3-autonomy",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas agent bounded-live-readiness",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--quality-gate", required=True)
    parser.add_argument("--shadow-comparison", required=True)
    parser.add_argument("--submit-conformance", required=True)
    parser.add_argument("--readiness-envelope", required=True)
    parser.add_argument("--operator-approval-gate", required=True)
    parser.add_argument("--bounded-autonomy-policy", required=True)
    parser.add_argument("--risk-limit", required=True)
    parser.add_argument("--symbol-allowlist", required=True)
    parser.add_argument("--heartbeat-deadman", required=True)
    parser.add_argument("--audit-redaction", required=True)
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
    print(f"readiness_digest: {report.readiness_digest}")
    print("gates:")
    for gate in report.gates:
        reason = f" ({gate.reason})" if gate.reason else ""
        print(f"  {gate.gate_id}: {gate.status}{reason}")
    if report.blockers:
        print("blockers:")
        for reason in report.blockers:
            print(f"  - {reason}")
    if report.status == "bounded_live_readiness_recorded":
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


def _check_path_aliasing(inputs: BoundedLiveAutonomyReadinessInputs, output_dir: Path) -> None:
    output_dir_id = _resolve_unique_id(output_dir)
    input_paths = [
        inputs.quality_gate_path,
        inputs.shadow_comparison_path,
        inputs.submit_conformance_path,
        inputs.readiness_envelope_path,
        inputs.operator_approval_gate_path,
        inputs.bounded_autonomy_policy_path,
        inputs.risk_limit_path,
        inputs.symbol_allowlist_path,
        inputs.heartbeat_deadman_path,
        inputs.audit_redaction_path,
    ]
    for path in input_paths:
        path_id = _resolve_unique_id(path)
        if path_id is not None and path_id == output_dir_id:
            raise BoundedLiveAutonomyReadinessValidationError(
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

    inputs = BoundedLiveAutonomyReadinessInputs(
        quality_gate_path=Path(args.quality_gate),
        shadow_comparison_path=Path(args.shadow_comparison),
        submit_conformance_path=Path(args.submit_conformance),
        readiness_envelope_path=Path(args.readiness_envelope),
        operator_approval_gate_path=Path(args.operator_approval_gate),
        bounded_autonomy_policy_path=Path(args.bounded_autonomy_policy),
        risk_limit_path=Path(args.risk_limit),
        symbol_allowlist_path=Path(args.symbol_allowlist),
        heartbeat_deadman_path=Path(args.heartbeat_deadman),
        audit_redaction_path=Path(args.audit_redaction),
        output_dir=Path(args.output_dir),
        as_of=args.as_of,
    )

    try:
        _check_path_aliasing(inputs, inputs.output_dir)
        report = build_bounded_live_autonomy_readiness_report(inputs)
        if report.status == "readiness_synthesized":
            report = write_bounded_live_autonomy_readiness_artifacts(report, inputs.output_dir)
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
