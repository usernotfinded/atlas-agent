# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    research/command_specs.py
# PURPOSE: Declarative specs for the research CLI commands, so the command surface and
#          its documentation cannot drift apart.
# DEPS:    stdlib only
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResearchCommandSpec:
    """Declarative spec for a family of research subcommands.

    Each family typically has a 'create' command plus zero or more
    read-only subcommands (list, show, validate, replay, summary, doctor).
    """

    prefix: str
    display_name: str
    create_help: str
    create_description: str
    create_positional: tuple[str, str] | None = None
    create_options: tuple[tuple[str, str, dict[str, Any]], ...] = ()
    subcommands: tuple[str, ...] = ("list", "show", "validate", "replay")
    list_limit_default: int = 20
    list_symbol_default: str | None = None
    list_has_limit: bool = True
    show_positional_name: str | None = None
    validate_strict_help: str = "Exit non-zero if validation fails."
    replay_strict_help: str = "Exit non-zero if replay does not match."
    configless: bool = True
    public_prefix: str | None = None


# ---------------------------------------------------------------------------
# Standard families that follow the create/list/show/validate/replay pattern
# ---------------------------------------------------------------------------

_STANDARD_RESEARCH_SPECS: tuple[ResearchCommandSpec, ...] = (
    ResearchCommandSpec(
        prefix="provider-plan",
        display_name="provider call plan",
        create_help="Create a provider call plan artifact from a sandbox request. Local-only.",
        create_description="Create a provider call plan artifact from an existing sandbox request. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("sandbox_request_id", "Source sandbox request ID."),
        create_options=(
            ("--provider", "Provider ID.", {"required": True}),
            ("--model", "Model ID.", {"required": True}),
        ),
        show_positional_name="provider_call_plan_id",
    ),
    ResearchCommandSpec(
        prefix="provider-execution-dry-run",
        display_name="provider execution dry-run",
        create_help="Create a provider execution dry-run artifact from a provider call plan. Local-only.",
        create_description="Create a provider execution dry-run artifact from an existing provider call plan. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("provider_call_plan_id", "Source provider call plan ID."),
        public_prefix="provider-execution",
    ),
    ResearchCommandSpec(
        prefix="provider-execution-state",
        display_name="provider execution state",
        create_help="Create a provider execution state transition artifact. Local-only. No provider calls.",
        create_description="Create a local provider execution opt-in state transition artifact from a dry-run. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("provider_execution_dry_run_id", "Source provider execution dry-run ID."),
        create_options=(
            ("--to", "Requested state. Must be one of: disabled, dry_run_only, manual_unlock_required, provider_call_allowed_but_not_implemented.", {"dest": "requested_state", "required": True}),
        ),
    ),
    ResearchCommandSpec(
        prefix="provider-execution-audit",
        display_name="provider execution audit",
        create_help="Create a provider execution audit packet from a state artifact. Local-only. No provider calls.",
        create_description="Create a local provider execution audit packet artifact from a provider execution state. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("provider_execution_state_id", "Source provider execution state ID."),
        show_positional_name="provider_execution_audit_packet_id",
    ),
    ResearchCommandSpec(
        prefix="provider-execution-readiness",
        display_name="provider execution readiness",
        create_help="Create a provider execution readiness report from an audit packet. Local-only. No provider calls.",
        create_description="Create a local provider execution readiness report artifact from a provider execution audit packet. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("provider_execution_audit_packet_id", "Source provider execution audit packet ID."),
        show_positional_name="provider_execution_readiness_report_id",
    ),
    ResearchCommandSpec(
        prefix="provider-preflight-freeze",
        display_name="provider preflight freeze",
        create_help="Create a provider preflight freeze audit artifact from a readiness report. Local-only.",
        create_description="Create a local provider preflight freeze audit artifact from a provider execution readiness report. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("provider_execution_readiness_report_id", "Source provider execution readiness report ID."),
        subcommands=("list", "show", "validate", "replay", "summary"),
    ),
    ResearchCommandSpec(
        prefix="provider-opt-in-policy",
        display_name="provider opt-in policy",
        create_help="Create a provider opt-in policy artifact from a preflight freeze. Local-only.",
        create_description="Create a local provider opt-in policy artifact from a provider preflight freeze. Local-only. Does not call providers, read API keys, modify config, or authorize live trading.",
        create_positional=("provider_preflight_freeze_id", "Source provider preflight freeze ID."),
        subcommands=("list", "show", "validate", "replay", "summary"),
    ),
    ResearchCommandSpec(
        prefix="provider-credential-boundary",
        display_name="provider credential boundary",
        create_help="Create a provider credential boundary artifact from an opt-in policy. Local-only.",
        create_description="Create a local provider credential boundary artifact from a provider opt-in policy. Local-only. Does not call providers, read API keys, load .env.atlas, read os.environ, modify config, or authorize live trading.",
        create_positional=("provider_opt_in_policy_id", "Source provider opt-in policy ID."),
        subcommands=("list", "show", "validate", "replay", "summary"),
    ),
    ResearchCommandSpec(
        prefix="provider-payload-preview",
        display_name="provider outbound payload preview",
        create_help="Create a provider outbound payload preview artifact from a credential boundary. Local-only.",
        create_description="Create a local provider outbound payload preview artifact from a provider credential boundary. Local-only. Does not call providers, read API keys, load .env.atlas, read os.environ, modify config, or authorize live trading.",
        create_positional=("provider_credential_boundary_id", "Source provider credential boundary ID."),
        subcommands=("list", "show", "validate", "replay", "summary"),
        show_positional_name="provider_outbound_payload_preview_id",
    ),
)

# ---------------------------------------------------------------------------
# Configless command names
# ---------------------------------------------------------------------------

# Commands that are explicitly configless but whose parsers remain manually
# declared in cli.py because they have custom shapes.
_MANUAL_CONFIGLESS_COMMANDS: frozenset[str] = frozenset({
    # Early research commands (manually declared in cli.py)
    "run",
    "list",
    "show",
    "plan",
    "verify",
    "evaluate",
    "summary",
    "check-artifacts",
    "timeline",
    "providers",
    "prompt",
    "simulate-provider",
    "review-response",
    "dossier",
    "sandbox",
    "sandbox-list",
    "sandbox-show",
    "sandbox-validate",
    "sandbox-replay",
    "import-provider-response",
    "provider-targets",
    # Custom families with non-standard list/show/validate/replay shapes
    "provider-response-intake-policy",
    "provider-response-intake-policy-list",
    "provider-response-intake-policy-show",
    "provider-response-intake-policy-validate",
    "provider-response-intake-policy-replay",
    "provider-response-intake-policy-summary",
    "provider-request-response-pairing",
    "provider-request-response-pairing-list",
    "provider-request-response-pairing-show",
    "provider-request-response-pairing-validate",
    "provider-request-response-pairing-replay",
    "provider-request-response-pairing-summary",
    "provider-request-response-pairing-doctor",
    "provider-response-schema-contract",
    "provider-response-schema-contract-list",
    "provider-response-schema-contract-show",
    "provider-response-schema-contract-validate",
    "provider-response-schema-contract-replay",
    "provider-response-schema-contract-summary",
    "provider-response-schema-contract-doctor",
    "provider-response-review-result",
    "provider-response-review-result-list",
    "provider-response-review-result-show",
    "provider-response-review-result-validate",
    "provider-response-review-result-replay",
    "provider-response-review-result-summary",
    "provider-response-review-result-doctor",
    "provider-execution-unlock-state",
    "provider-execution-unlock-state-list",
    "provider-execution-unlock-state-show",
    "provider-execution-unlock-state-validate",
    "provider-execution-unlock-state-replay",
    "provider-execution-unlock-state-summary",
    "provider-execution-unlock-state-doctor",
    "provider-adapter-interface-contract",
    "provider-adapter-interface-contract-list",
    "provider-adapter-interface-contract-show",
    "provider-adapter-interface-contract-validate",
    "provider-adapter-interface-contract-replay",
    "provider-adapter-interface-contract-summary",
    "provider-adapter-interface-contract-doctor",
    "provider-adapter-disabled-smoke",
    "provider-mock-response-simulate",
    "provider-mock-response-list",
    "provider-mock-response-show",
    "provider-mock-response-validate",
    "provider-mock-response-replay",
    "provider-mock-response-summary",
    "provider-mock-response-doctor",
    "provider-mock-response-import-candidate",
    "provider-mock-response-import-candidate-list",
    "provider-mock-response-import-candidate-show",
    "provider-mock-response-import-candidate-validate",
    "provider-mock-response-import-candidate-replay",
    "provider-mock-response-import-candidate-summary",
    "provider-mock-response-import-candidate-doctor",
    "provider-mock-response-review-sandbox",
    "provider-mock-response-review-sandbox-list",
    "provider-mock-response-review-sandbox-show",
    "provider-mock-response-review-sandbox-validate",
    "provider-mock-response-review-sandbox-replay",
    "provider-mock-response-review-sandbox-summary",
    "provider-mock-response-review-sandbox-doctor",
    "provider-mock-response-trust-decision-blocker",
    "provider-mock-response-trust-decision-blocker-list",
    "provider-mock-response-trust-decision-blocker-show",
    "provider-mock-response-trust-decision-blocker-validate",
    "provider-mock-response-trust-decision-blocker-replay",
    "provider-mock-response-trust-decision-blocker-summary",
    "provider-mock-response-trust-decision-blocker-doctor",
    "provider-mock-response-final-safety-seal",
    "provider-mock-response-final-safety-seal-list",
    "provider-mock-response-final-safety-seal-show",
    "provider-mock-response-final-safety-seal-validate",
    "provider-mock-response-final-safety-seal-replay",
    "provider-mock-response-final-safety-seal-summary",
    "provider-mock-response-final-safety-seal-doctor",
    "provider-safety-dossier",
    "provider-safety-dossier-list",
    "provider-safety-dossier-latest",
    "provider-safety-dossier-show",
    "provider-safety-dossier-validate",
    "provider-safety-dossier-replay",
    "provider-safety-dossier-summary",
    "provider-safety-dossier-doctor",
    "provider-safety-dossier-export",
    "release-candidate-readiness",
    "release-candidate-readiness-list",
    "release-candidate-readiness-show",
    "release-candidate-readiness-validate",
    "release-candidate-readiness-summary",
    "release-candidate-readiness-doctor",
    "release-candidate-cutover-dry-run",
    "release-candidate-cutover-dry-run-list",
    "release-candidate-cutover-dry-run-validate",
    "release-candidate-cutover-dry-run-summary",
    "release-candidate-cutover-dry-run-doctor",
    # provider-execution-chain-doctor is a custom manual command
    "provider-execution-chain-doctor",
    # Compatibility shim
    "mock-response-final-safety-seal",
})


def _command_names_from_spec(spec: ResearchCommandSpec) -> set[str]:
    names = {spec.prefix}
    sub_prefix = spec.public_prefix if spec.public_prefix is not None else spec.prefix
    for suffix in spec.subcommands:
        names.add(f"{sub_prefix}-{suffix}")
        names.add(f"{spec.prefix}-{suffix}")
    return names


def iter_research_command_names() -> set[str]:
    """Return all research command names known to the spec layer."""
    names: set[str] = set()
    for spec in _STANDARD_RESEARCH_SPECS:
        names |= _command_names_from_spec(spec)
    names |= _MANUAL_CONFIGLESS_COMMANDS
    return names


CONFIGLESS_RESEARCH_COMMANDS: frozenset[str] = frozenset(
    name for name in iter_research_command_names()
)


# Mapping from alias name -> canonical name for research subcommands that have
# public_prefix overrides.  Used by cli.py to normalize args.research_command.
RESEARCH_COMMAND_ALIAS_MAP: dict[str, str] = {}
for _spec in _STANDARD_RESEARCH_SPECS:
    if _spec.public_prefix is not None and _spec.public_prefix != _spec.prefix:
        for _suffix in _spec.subcommands:
            _alias = f"{_spec.prefix}-{_suffix}"
            _canonical = f"{_spec.public_prefix}-{_suffix}"
            RESEARCH_COMMAND_ALIAS_MAP[_alias] = _canonical



# ---------------------------------------------------------------------------
# Parser helpers
# ---------------------------------------------------------------------------

def _add_standard_subparsers(
    research_sub, spec: ResearchCommandSpec
) -> dict[str, Any]:
    """Add argparse subparsers for a standard research command family.

    Returns a dict mapping suffix -> parser for optional manual tweaking.
    """
    parsers: dict[str, Any] = {}
    prefix = spec.prefix

    # Create
    create_parser = research_sub.add_parser(
        prefix,
        help=spec.create_help,
        description=spec.create_description,
    )
    if spec.create_positional:
        arg_name, arg_help = spec.create_positional
        create_parser.add_argument(arg_name, help=arg_help)
    for opt_name, opt_help, opt_kwargs in spec.create_options:
        create_parser.add_argument(opt_name, help=opt_help, **opt_kwargs)
    create_parser.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
    parsers["create"] = create_parser

    # Show positional name inference
    show_positional = spec.show_positional_name
    if show_positional is None:
        show_positional = prefix.replace("-", "_") + "_id"

    dn = spec.display_name
    sub_prefix = spec.public_prefix if spec.public_prefix is not None else prefix
    for suffix in spec.subcommands:
        alias = None
        if spec.public_prefix is not None and spec.public_prefix != prefix:
            alias = f"{prefix}-{suffix}"
        cmd_name = f"{sub_prefix}-{suffix}"
        parser_aliases = [alias] if alias else []
        if suffix == "list":
            p = research_sub.add_parser(
                cmd_name,
                aliases=parser_aliases,
                help=f"List {dn} artifacts. Read-only. Does not call providers or network."
                if prefix == "provider-plan"
                else f"List {dn} artifacts. Read-only.",
                description=f"List local {dn} artifacts. Read-only. Does not call providers, read API keys, or authorize live trading.",
            )
            p.add_argument("--symbol", help="Filter by symbol.")
            if spec.list_has_limit:
                p.add_argument(
                    "--limit",
                    type=int,
                    default=spec.list_limit_default,
                    help=f"Maximum items to show. Default: {spec.list_limit_default}, max: 100."
                    if spec.list_limit_default != 20
                    else f"Maximum items to show. Default: {spec.list_limit_default}.",
                )
            p.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
            parsers[suffix] = p

        elif suffix == "show":
            p = research_sub.add_parser(
                cmd_name,
                aliases=parser_aliases,
                help=f"Show a {dn} artifact. Read-only. Does not call providers or network."
                if prefix == "provider-plan"
                else f"Show a {dn} artifact. Read-only.",
                description=f"Show one local {dn} artifact by ID. Read-only. Does not call providers, read API keys, or authorize live trading.",
            )
            p.add_argument(show_positional, help=f"{dn.replace('-', ' ').title()} ID.")
            p.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
            parsers[suffix] = p

        elif suffix == "validate":
            p = research_sub.add_parser(
                cmd_name,
                aliases=parser_aliases,
                help=f"Validate a {dn} artifact against the local contract. Read-only."
                if prefix == "provider-plan"
                else f"Validate a {dn} artifact. Read-only.",
                description=f"Validate a {dn} artifact against the local contract. Read-only. Does not call providers, read API keys, or authorize live trading."
                if prefix == "provider-plan"
                else f"Validate a {dn} artifact against safety checks. Read-only. Does not call providers, read API keys, or authorize live trading.",
            )
            p.add_argument(show_positional, help=f"{dn.replace('-', ' ').title()} ID.")
            p.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
            p.add_argument("--strict", action="store_true", help=spec.validate_strict_help)
            parsers[suffix] = p

        elif suffix == "replay":
            p = research_sub.add_parser(
                cmd_name,
                aliases=parser_aliases,
                help=f"Replay a {dn} from its source sandbox request and compare hashes. Read-only by default."
                if prefix == "provider-plan"
                else f"Replay a {dn} from its source and compare hashes. Read-only by default."
                if prefix in ("provider-execution-dry-run", "provider-execution-state", "provider-execution-audit", "provider-execution-readiness")
                else f"Replay a {dn} artifact from its source and compare hashes. Read-only by default.",
                description=f"Rebuild the {dn} from its source sandbox request and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading."
                if prefix == "provider-plan"
                else f"Rebuild the {dn} from its source and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading."
                if prefix in ("provider-execution-dry-run", "provider-execution-state", "provider-execution-audit", "provider-execution-readiness")
                else f"Rebuild the {dn} artifact from its source and compare deterministic hashes. Read-only by default. Does not call providers, read API keys, modify config, or authorize live trading.",
            )
            p.add_argument(show_positional, help=f"{dn.replace('-', ' ').title()} ID.")
            p.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
            p.add_argument("--strict", action="store_true", help=spec.replay_strict_help)
            parsers[suffix] = p

        elif suffix == "summary":
            p = research_sub.add_parser(
                cmd_name,
                aliases=parser_aliases,
                help=f"Summarize the {dn} state for a research run. Read-only.",
                description=f"Read-only summary of the {dn} state for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
            )
            p.add_argument("run_id", help="Research run ID.")
            p.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
            parsers[suffix] = p

        elif suffix == "doctor":
            p = research_sub.add_parser(
                cmd_name,
                aliases=parser_aliases,
                help=f"Diagnose the {dn} chain for a research run. Read-only.",
                description=f"Read-only diagnostic of the {dn} chain for a research run. Does not create artifacts, call providers, read API keys, or authorize live trading.",
            )
            p.add_argument("run_id", help="Research run ID.")
            p.add_argument("--json", action="store_true", help="Emit safe JSON envelope.")
            parsers[suffix] = p

    return parsers


def add_research_subparsers(research_sub) -> None:
    """Add all standard research command families to the research subparser."""
    for spec in _STANDARD_RESEARCH_SPECS:
        _add_standard_subparsers(research_sub, spec)
