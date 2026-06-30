from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas_agent.agent.runtime_readiness_envelope import (
    ReadinessEnvelopeInputs,
    build_runtime_readiness_envelope_report,
    write_runtime_readiness_envelope_artifacts,
)

CLI_DESCRIPTION = """\
Runtime readiness envelope evaluation (CAND-007) — simulated only.

This command consumes CAND-004 trading-quality evidence, CAND-005 shadow-live
comparison evidence, CAND-006 gated submit conformance evidence, and five static
local policy fixtures. It evaluates them in strict fail-closed order and records
a runtime readiness envelope artifact if every gate passes.

This command does not submit orders, does not call broker or provider APIs, does
not load credentials, does not create real or pending orders, does not import
Order/OrderRouter/RiskManager/runtime kill switch, and does not claim live
readiness or permission to submit orders.\
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
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atlas agent readiness-envelope",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--quality-gate", required=True)
    parser.add_argument("--shadow-comparison", required=True)
    parser.add_argument("--submit-conformance", required=True)
    parser.add_argument("--runtime-envelope", required=True)
    parser.add_argument("--broker-capabilities", required=True)
    parser.add_argument("--operator-policy", required=True)
    parser.add_argument("--kill-switch-policy", required=True)
    parser.add_argument("--audit-policy", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def _reject_unsafe_flags(argv: list[str] | None) -> int:
    args = argv if argv is not None else []
    for token in args:
        name = token.split("=", 1)[0]
        if name in _UNSAFE_FLAGS:
            print(f"error: unsafe flag rejected: {name}", file=sys.stderr)
            return 2
    return 0


def _print_text_report(report: Any) -> None:
    print(f"status: {report.status}")
    print(f"evaluation_id: {report.evaluation_id}")
    print(f"as_of: {report.as_of}")
    print(f"symbol: {report.symbol or '-'}")
    print(f"run_id: {report.run_id or '-'}")
    print(f"input_digest: {report.input_digest}")
    print(f"envelope_digest: {report.envelope_digest}")
    print("gates:")
    for gate in report.gates:
        reason = f" ({gate.reason})" if gate.reason else ""
        print(f"  {gate.gate_id}: {gate.status}{reason}")
    if report.blockers:
        print("blockers:")
        for reason in report.blockers:
            print(f"  - {reason}")
    if report.status == "readiness_envelope_recorded":
        print("artifacts recorded.")


def main(argv: list[str] | None = None) -> int:
    reject_code = _reject_unsafe_flags(argv)
    if reject_code != 0:
        return reject_code
    parser = build_parser()
    args = parser.parse_args(argv)

    inputs = ReadinessEnvelopeInputs(
        quality_gate_path=Path(args.quality_gate),
        shadow_comparison_path=Path(args.shadow_comparison),
        submit_conformance_path=Path(args.submit_conformance),
        runtime_envelope_path=Path(args.runtime_envelope),
        broker_capabilities_path=Path(args.broker_capabilities),
        operator_policy_path=Path(args.operator_policy),
        kill_switch_policy_path=Path(args.kill_switch_policy),
        audit_policy_path=Path(args.audit_policy),
        output_dir=Path(args.output_dir),
        as_of=args.as_of,
    )

    try:
        report = build_runtime_readiness_envelope_report(inputs)
        if report.status == "envelope_synthesized":
            report = write_runtime_readiness_envelope_artifacts(report, inputs.output_dir)
    except Exception as exc:
        if args.json:
            print(json.dumps({"status": "not_evaluated", "error": str(exc), "exit_code": 2}, indent=2, sort_keys=True))
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
