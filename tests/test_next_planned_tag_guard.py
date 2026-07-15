# ==============================================================================
# PROJECT: Atlas Agent
# FILE:    tests/test_next_planned_tag_guard.py
# PURPOSE: Verifies next planned tag guard behavior and regression expectations.
# DEPS:    subprocess, pytest, scripts.
# ==============================================================================

"""Regression coverage for the next-planned tag guard in release-metadata checkers.

Guards against the bug class found during the v0.6.21 cutover: a checker's
``git tag --list <tag>`` guard kept a hardcoded prior planning tag (``v0.6.21``)
after release metadata advanced ``next_planned_release`` to ``v0.6.22``. Because
the stale guard only fails once the new release tag is created, the pre-tag
checks stayed green and the drift was invisible until after tagging.

The guard must always query the metadata-derived ``NEXT_PLANNED_TAG`` so it can
never drift from ``next_planned_release`` in release metadata. These tests are
deterministic and offline: ``subprocess.run`` is mocked, so no real git tags are
read or created.
"""
# --- IMPORTS ---

from __future__ import annotations

import subprocess

import pytest

from scripts import (
    check_autonomous_paper_workflow_demo,
    check_bounded_autonomy_governance,
    check_paper_provider_isolation,
)

# (checker module, guard function name) for every checker that guards the
# next-planned release tag by shelling out to ``git tag --list``.
# --- CONFIGURATION AND CONSTANTS ---

_GUARDS = [
    (check_bounded_autonomy_governance, "_check_version_planning_only"),
    (check_autonomous_paper_workflow_demo, "_check_release_metadata"),
    (check_paper_provider_isolation, "_check_release_metadata"),
]

_SENTINEL = "v9.9.9-next-planned-sentinel"


# ==============================================================================
# TEST SUITE
# ==============================================================================

# --- TEST FIXTURES, HELPERS, AND CASES ---

class _FakeCompletedProcess:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0


def _ids(value: object) -> str:
    return getattr(value, "__name__", str(value))


@pytest.mark.parametrize("module, guard_name", _GUARDS, ids=_ids)
def test_guard_queries_metadata_next_planned_tag(module, guard_name, monkeypatch):
    """The guard queries ``git tag --list <NEXT_PLANNED_TAG>``, not a hardcoded tag.

    Fails if the guard hardcodes a release tag, which is exactly how the v0.6.21
    cutover drift would have gone undetected.
    """
    captured: dict[str, list[str]] = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        return _FakeCompletedProcess("")

    monkeypatch.setattr(module, "NEXT_PLANNED_TAG", _SENTINEL)
    monkeypatch.setattr(subprocess, "run", fake_run)

    getattr(module, guard_name)()

    assert captured.get("args") == ["git", "tag", "--list", _SENTINEL], (
        f"{module.__name__}.{guard_name} must guard the metadata next-planned tag "
        f"({_SENTINEL!r}); a hardcoded tag drifts from release metadata."
    )


@pytest.mark.parametrize("module, guard_name", _GUARDS, ids=_ids)
def test_guard_error_names_metadata_next_planned_tag(module, guard_name, monkeypatch):
    """When the next-planned tag already exists locally, the error names that tag."""

    def fake_run(args, **kwargs):
        return _FakeCompletedProcess(_SENTINEL + "\n")

    monkeypatch.setattr(module, "NEXT_PLANNED_TAG", _SENTINEL)
    monkeypatch.setattr(subprocess, "run", fake_run)

    errors = getattr(module, guard_name)()

    assert any(_SENTINEL in err and "already exists" in err for err in errors), (
        f"{module.__name__}.{guard_name} must report the metadata next-planned tag "
        f"({_SENTINEL!r}) as already existing; a hardcoded message drifts."
    )
