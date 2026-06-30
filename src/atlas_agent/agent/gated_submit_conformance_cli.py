from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from atlas_agent.agent.gated_submit_conformance import (
    SubmitConformanceInputs,
    build_gated_submit_conformance_report,
    write_gated_submit_conformance_artifacts,
)


CLI_DESCRIPTION = """\
Gated submit conformance rehearsal (CAND-006) — simulated only.

This command is a deterministic, local-only, fixture-driven conformance
rehearsal. It consumes CAND-004 quality evidence, CAND-005 shadow-live
comparison evidence, a hypothetical order intent fixture, and simulated
kill-switch, risk-envelope, and approval fixtures.

It evaluates them in strict fail-closed order and records a non-transmittable
dry-run submit request only if every gate passes.

This command does not submit orders, does not call broker APIs, does not call
providers, does not load credentials, does not create real or pending orders,
and does not claim live readiness. It is a simulated-only rehearsal.\
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
        prog="atlas agent submit-conformance",
        description=CLI_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--quality-gate",
        required=True,
        help="Path to CAND-004 trading-quality-gate.json.",
    )
    parser.add_argument(
        "--shadow-comparison",
        required=True,
        help="Path to CAND-005 shadow-live-comparison.json.",
    )
    parser.add_argument(
        "--order-intent",
        required=True,
        help="Path to the hypothetical order intent fixture.",
    )
    parser.add_argument(
        "--kill-switch",
        required=True,
        help="Path to the simulated kill-switch fixture.",
    )
    parser.add_argument(
        "--risk-envelope",
        required=True,
        help="Path to the simulated RiskManager-shaped risk envelope fixture.",
    )
    parser.add_argument(
        "--approval",
        required=True,
        help="Path to the simulated approval fixture.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where gated-submit-conformance.json and gated-submit-conformance-report.md are written.",
    )
    parser.add_argument(
        "--as-of",
        required=True,
        help="ISO-8601 UTC timestamp used for deterministic expiry evaluation (e.g., 2026-06-24T10:00:00Z).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the conformance report as JSON on stdout.",
    )
    return parser


def _print_text_report(report: Any) -> None:
    print(f"status: {report.status}")
    print(f"evaluation_id: {report.evaluation_id}")
    print(f"as_of: {report.as_of}")
    print(f"input_digest: {report.input_digest}")
    if report.dry_run_request is not None:
        print(f"dry_run_request_fingerprint: {report.dry_run_request_fingerprint}")
    print("gates:")
    for gate in report.gates:
        reason = f" ({gate.reason})" if gate.reason else ""
        print(f"  {gate.gate_id}: {gate.status}{reason}")
    if report.blockers:
        print("blockers:")
        for blocker in report.blockers:
            print(f"  - {blocker}")
    if report.status == "dry_run_recorded":
        print("artifacts recorded.")


def _reject_unsafe_flags(argv: list[str] | None) -> int:
    args = argv if argv is not None else []
    for raw_arg in args:
        name = raw_arg.split("=", 1)[0]
        if name in _UNSAFE_FLAGS:
            print(
                f"error: unsupported flag for simulated-only conformance: {name}",
                file=sys.stderr,
            )
            return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    reject_code = _reject_unsafe_flags(argv)
    if reject_code != 0:
        return reject_code
    parser = build_parser()
    args = parser.parse_args(argv)

    inputs = SubmitConformanceInputs(
        quality_gate_path=Path(args.quality_gate),
        shadow_comparison_path=Path(args.shadow_comparison),
        order_intent_path=Path(args.order_intent),
        kill_switch_path=Path(args.kill_switch),
        risk_envelope_path=Path(args.risk_envelope),
        approval_path=Path(args.approval),
        output_dir=Path(args.output_dir),
        as_of=args.as_of,
    )

    try:
        report = build_gated_submit_conformance_report(inputs)
        report = write_gated_submit_conformance_artifacts(report, inputs.output_dir)
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "not_evaluated",
                        "error": str(exc),
                        "exit_code": 2,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(f"status: not_evaluated")
            print(f"error: {exc}")
        return 2

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        _print_text_report(report)

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
