# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/architecture/test_broker_protocol_conformance.py
# PURPOSE: Refuses a broker adapter that implements part of a broker protocol.
# DEPS:    ast, pathlib, pytest, atlas_agent.brokers.base.
# ==============================================================================

"""Structural guard for hard invariant 4.

The governance document says "every broker adapter implements the `Broker`
interface and passes fail-closed guards". `Broker` and `BrokerProvider` are
`typing.Protocol`s, so nothing checks that: Python raises `AttributeError` at the
call site, whenever that call first happens.

For most methods that means a late, loud failure. For `flatten_all` it means an
adapter missing the emergency exit passes every test that never has an emergency,
and is discovered by the operator who needs it.

The rule here is partial implementation, not absence. A class that implements
some of a protocol has claimed to be that kind of object and will be used as one.
A class that implements none has not — which is why `IBKRStub` is not an
exception to this test: it defines no protocol method at all and its
`__getattr__` raises `NotImplementedError` for every access, so a half-written
IBKR adapter cannot masquerade as a working one.

The protocol method names are read from `brokers/base.py` rather than restated,
so a method added to a protocol is immediately required of its implementers.
"""

# --- IMPORTS ---

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# --- CONFIGURATION AND CONSTANTS ---

ROOT = Path(__file__).resolve().parents[2]
BROKERS_DIR = ROOT / "src" / "atlas_agent" / "brokers"
BASE_MODULE = BROKERS_DIR / "base.py"

PROTOCOLS = ("Broker", "BrokerProvider")

#: Modules in `brokers/` that hold no adapter.
NON_ADAPTER_MODULES = frozenset(
    {
        "__init__.py",
        "base.py",
        "errors.py",
        "guards.py",
        "live_sync_validation.py",
        "models.py",
        "resolver.py",
        "status.py",
        "sync.py",
    }
)


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

def _protocol_methods(protocol_name: str) -> frozenset[str]:
    """The method names a protocol in `brokers/base.py` declares."""
    tree = ast.parse(BASE_MODULE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == protocol_name:
            return frozenset(
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not item.name.startswith("_")
            )
    raise AssertionError(f"{protocol_name} is no longer defined in {BASE_MODULE.name}")


def _discriminating_methods(protocol_name: str) -> frozenset[str]:
    """The methods that belong to this protocol and no other.

    `get_positions` is declared by both `Broker` and `BrokerProvider`, so
    implementing it is not evidence of claiming either. Judging the claim on the
    shared method would report every implementer of one protocol as a partial
    implementer of the other.
    """
    own = _protocol_methods(protocol_name)
    shared: set[str] = set()
    for other in PROTOCOLS:
        if other != protocol_name:
            shared |= own & _protocol_methods(other)
    return frozenset(own - shared)


def _adapter_classes() -> list[tuple[str, str, frozenset[str], list[str]]]:
    """Every class in an adapter module, with its methods and base names."""
    found: list[tuple[str, str, frozenset[str], list[str]]] = []
    for path in sorted(BROKERS_DIR.glob("*.py")):
        if path.name in NON_ADAPTER_MODULES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = frozenset(
                item.name
                for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            bases = [ast.unparse(base) for base in node.bases]
            found.append((path.name, node.name, methods, bases))
    return found


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_the_protocol_is_still_readable(protocol: str) -> None:
    """Both checks below pass trivially if the protocols cannot be found.

    Renaming a protocol, or moving it out of `base.py`, would otherwise leave
    every adapter compared against an empty method set.
    """
    methods = _protocol_methods(protocol)

    assert len(methods) >= 4, (
        f"{protocol} declares only {sorted(methods)}; the scan has probably "
        "stopped reading the protocol rather than the protocol having shrunk."
    )


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_no_adapter_implements_part_of_a_protocol(protocol: str) -> None:
    """Implementing some of a protocol is the state that fails at the call site."""
    required = _protocol_methods(protocol)
    discriminating = _discriminating_methods(protocol)
    offenders: list[str] = []

    for module, class_name, methods, _bases in _adapter_classes():
        implemented = methods & discriminating
        if not implemented:
            continue  # claims nothing; IBKRStub is here, refusing everything
        missing = required - methods
        if missing:
            offenders.append(
                f"{module}::{class_name} implements {sorted(implemented)} "
                f"but not {sorted(missing)}"
            )

    assert offenders == [], (
        f"These classes implement part of {protocol}: {offenders}. A partial "
        "implementation is used as the real thing and fails at the call site — "
        "for flatten_all, in the emergency it exists for."
    )


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_declaring_a_protocol_as_a_base_means_implementing_it(protocol: str) -> None:
    """A class that names the protocol has made the claim explicitly."""
    required = _protocol_methods(protocol)
    offenders: list[str] = []

    for module, class_name, methods, bases in _adapter_classes():
        if protocol not in bases:
            continue
        missing = required - methods
        if missing:
            offenders.append(f"{module}::{class_name} is missing {sorted(missing)}")

    assert offenders == [], (
        f"These classes declare {protocol} as a base and do not implement it: "
        f"{offenders}."
    )


def test_the_scan_still_finds_the_known_adapters() -> None:
    """A glob that stops matching would empty every check above."""
    modules = {module for module, _cls, _methods, _bases in _adapter_classes()}

    assert {"alpaca.py", "paper.py", "binance.py"} <= modules, (
        f"the adapter scan found only {sorted(modules)}; it is no longer reaching "
        "the broker adapters."
    )
