# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_research_handlers_use_the_shared_envelope.py
# PURPOSE: Keeps the research CLI on one envelope, so the scaffolding CAND-035
#         removed cannot grow back one handler at a time.
# DEPS:    ast, pathlib, pytest
# ==============================================================================

"""Structural pin on the research handler idiom.

`CAND-035` collapsed 11,196 lines of `cli_commands/research/` to 6,778 by moving
the opening and closing every handler repeated -- a dispatch guard,
`resolve_workspace_path()` with an identical `no_workspace` branch, and the
fail-closed `except` pair -- into `_envelope.py`. 170 handlers now carry one
decorator instead of ~25 lines each.

Nothing stopped it growing back. The research surface gains subcommands often,
and the natural way to write the 171st handler is to copy the 170th; before the
migration that was how the duplication accumulated in the first place. A copy
made from a pre-migration handler, or from a diff, reintroduces the scaffolding
silently -- it still works, because the envelope's clauses simply never fire.

So this file asserts the migration's four properties directly, and pins the
handful of handlers that legitimately keep their own error clause. That last
list is the interesting one: two of its entries exist because a scripted
conversion of them would have changed an exit code, which is exactly the class
of mistake a reviewer should be made to look at rather than left to notice.

The prefix check in `test_the_envelope_prefix_matches_the_registry_key` is not
cosmetic. Before the migration the prefix was the dispatch guard's comparison
operand, so a mismatch was unreachable code; now it is the command name printed
in every error message that handler can emit.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

pytestmark = pytest.mark.quick

RESEARCH_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "atlas_agent"
    / "cli_commands"
    / "research"
)

#: Not handler modules. `_envelope.py` is where the absorbed scaffolding now
#: lives, `_shared.py` holds the two error emitters, `__init__.py` is the
#: dispatch table.
NON_HANDLER_MODULES = {"__init__.py", "_envelope.py", "_shared.py"}

#: The handlers allowed to keep an error clause that duplicates the envelope's,
#: and the reason each one is not a migration leftover.
#:
#: - The two `*_validate` handlers return `2 if args.strict else 1`, where the
#:   envelope returns 1. Absorbing them would silently change the exit status of
#:   `--strict`, which is what a first pass of the conversion script did.
#: - The three `*_list` handlers had no `ResearchSessionError` clause of their
#:   own before the migration, so every failure flattened to `research_error`.
#:   The envelope would map such an error to a specific status instead. Keeping
#:   the clause inside the body preserves the status these commands actually
#:   shipped with; narrowing it later is a contract change, not a cleanup.
#:
#: An addition here means a handler diverging from the shared error contract.
#: That is worth a human deciding, which is the point of pinning the set.
HANDLERS_WITH_THEIR_OWN_ERROR_CLAUSE = {
    ("adapter.py", "handle_provider_adapter_interface_contract_validate"),
    ("execution.py", "handle_provider_execution_state_list"),
    ("execution.py", "handle_provider_execution_audit_list"),
    ("execution.py", "handle_provider_execution_unlock_state_validate"),
    ("release_candidate.py", "handle_release_candidate_cutover_dry_run_list"),
}


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _handler_modules() -> list[Path]:
    modules = [p for p in sorted(RESEARCH_ROOT.glob("*.py")) if p.name not in NON_HANDLER_MODULES]
    # Guards against this whole file passing because a rename emptied the glob.
    assert len(modules) >= 13, f"expected the research handler modules, found {modules}"
    return modules


def _registry(module: Path) -> dict[str, str]:
    """The module's `HANDLERS` dict as {subcommand: function name}."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(target, "id", None) == "HANDLERS" for target in node.targets):
            continue
        assert isinstance(node.value, ast.Dict), f"{module.name}: HANDLERS is not a literal dict"
        return {
            key.value: value.id
            for key, value in zip(node.value.keys, node.value.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(value, ast.Name)
        }
    raise AssertionError(f"{module.name} has no HANDLERS dict")


def _envelope_arguments(module: Path) -> dict[str, str | None]:
    """{function name: the command string it was decorated with}."""
    tree = ast.parse(module.read_text(encoding="utf-8"))
    decorated: dict[str, str | None] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if getattr(decorator.func, "id", None) != "research_envelope":
                continue
            first = decorator.args[0] if decorator.args else None
            decorated[node.name] = first.value if isinstance(first, ast.Constant) else None
    return decorated


def _functions(tree: ast.AST) -> list[ast.FunctionDef]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]


def _enclosing(functions: list[ast.FunctionDef], node: ast.AST) -> str:
    """The innermost function containing `node`, by line span."""
    candidates = [
        fn for fn in functions if fn.lineno <= node.lineno <= (fn.end_lineno or fn.lineno)
    ]
    if not candidates:
        return "<module>"
    return max(candidates, key=lambda fn: fn.lineno).name


def test_no_handler_module_reintroduces_a_dispatch_guard() -> None:
    """`dispatch_research` already matched on the subcommand name before calling
    the handler, so a guard comparing it again can never be false. It was dead in
    all 170 handlers and must not come back as a 171st copy."""
    offenders = [
        module.name
        for module in _handler_modules()
        if "research_command" in module.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_no_handler_module_resolves_the_workspace() -> None:
    """One resolution site, one `no_workspace` envelope. A handler that resolves
    its own workspace gets to disagree with the envelope about what a missing one
    means."""
    offenders: list[str] = []
    for module in _handler_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name == "resolve_workspace_path":
                offenders.append(f"{module.name}::{_enclosing(_functions(tree), node)}")
    assert offenders == []


def test_no_handler_module_emits_a_no_workspace_status() -> None:
    """The status string is the observable half of the branch above. Checked
    separately because a handler can emit it without calling the resolver -- for
    instance by testing `ws` itself, which the envelope has already ruled out."""
    offenders: list[str] = []
    for module in _handler_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value == "no_workspace":
                offenders.append(f"{module.name}:{node.lineno}")
    assert offenders == []


def test_every_registered_handler_carries_the_envelope() -> None:
    """An undecorated handler is one that resolves no workspace and catches
    nothing: it would traceback out of the CLI on any error, leaking the
    exception text the envelope exists to suppress."""
    undecorated: list[str] = []
    total = 0
    for module in _handler_modules():
        decorated = _envelope_arguments(module)
        for subcommand, function in _registry(module).items():
            total += 1
            if function not in decorated:
                undecorated.append(f"{module.name}::{function} ({subcommand})")
    assert total >= 170, f"the registry shrank to {total}; this test may be checking nothing"
    assert undecorated == []


def test_the_envelope_prefix_matches_the_registry_key() -> None:
    """The decorator argument is what the operator sees: `research <prefix>
    skipped safely: ...`. A stale one misreports which command failed."""
    mismatched: list[str] = []
    for module in _handler_modules():
        decorated = _envelope_arguments(module)
        for subcommand, function in _registry(module).items():
            if function in decorated and decorated[function] != subcommand:
                mismatched.append(f"{module.name}::{function} says {decorated[function]!r}, registered as {subcommand!r}")
    assert mismatched == []


def test_only_the_pinned_handlers_keep_their_own_error_clause() -> None:
    """Both directions, so the allowlist cannot rot in either.

    A clause counts as the envelope's own if it calls
    `safe_research_session_error` or emits the `research_error` status. A clause
    that translates one exception into another -- `handle_import_provider_response`
    raises `ResearchSessionError('provider_response_malformed')` from a bare
    `except Exception` -- is doing something the envelope does not, so it is not
    matched here.
    """
    found: set[tuple[str, str]] = set()
    for module in _handler_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        functions = _functions(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            reproduces_the_envelope = any(
                (
                    isinstance(inner, ast.Name)
                    and inner.id == "safe_research_session_error"
                )
                or (isinstance(inner, ast.Constant) and inner.value == "research_error")
                for inner in ast.walk(node)
            )
            if reproduces_the_envelope:
                found.add((module.name, _enclosing(functions, node)))
    assert found == HANDLERS_WITH_THEIR_OWN_ERROR_CLAUSE


def test_no_handler_keeps_an_import_the_envelope_made_dead() -> None:
    """The scaffolding's imports outlived the scaffolding.

    Removing the `except` clauses left 158 function-scoped bindings of
    `ResearchSessionError`, `safe_research_session_error` and `json` that nothing
    referenced -- invisible, harmless, and a standing invitation to paste the
    clause back because the import is already there. A handler that genuinely
    needs an import for its side effect alone would trip this; none does, and one
    that did would be worth a comment either way.
    """
    dead: list[str] = []
    for module in _handler_modules():
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for function in _functions(tree):
            bound = {
                alias.asname or alias.name.split(".")[0]
                for node in ast.walk(function)
                if isinstance(node, (ast.Import, ast.ImportFrom))
                for alias in node.names
            }
            if not bound:
                continue
            loaded = {
                node.id
                for node in ast.walk(function)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            }
            dead.extend(f"{module.name}::{function.name} imports unused {name}" for name in sorted(bound - loaded))
    assert dead == []
