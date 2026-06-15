"""Regression coverage for the historical release-checker archive."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "scripts" / "historical_release_checkers"

HISTORICAL_CHECKERS = {
    "check_v058_gap_prioritization.py",
    "check_v058_rc1_readiness.py",
    "check_v058_rc1_cutover.py",
    "check_v058_rc2_cutover.py",
    "check_v058_rc3_cutover.py",
    "check_v058_rc4_cutover.py",
    "check_v058_rc5_cutover.py",
    "check_v058_stable_cutover.py",
    "check_v0581_hotfix_cutover.py",
    "check_v060_readiness.py",
    "check_v061_candidates.py",
    "check_v061_release_prep.py",
    "check_v062_release_prep.py",
    "check_v063_release_prep.py",
    "check_v064_candidates.py",
    "check_v064_release_prep.py",
    "check_v065_candidates.py",
    "check_v065_release_prep.py",
    "check_v066_release_prep.py",
    "check_v067_release_prep.py",
    "check_v068_release_prep.py",
    "check_v069_release_prep.py",
}


def test_historical_release_checkers_are_archived_not_deleted() -> None:
    archived = {path.name for path in ARCHIVE.glob("check_v*.py")}
    assert archived == HISTORICAL_CHECKERS


def test_historical_release_checkers_are_not_in_active_scripts_root() -> None:
    active_names = {path.name for path in (ROOT / "scripts").glob("check_v*.py")}
    assert active_names.isdisjoint(HISTORICAL_CHECKERS)
    assert {
        "check_v0610_planning.py",
        "check_v0610_release_prep.py",
        "check_v0611_planning.py",
        "check_version_consistency.py",
    }.issubset(active_names)


def test_active_gates_use_current_release_state_checkers() -> None:
    for relative_path in (
        "scripts/dev_check.sh",
        "scripts/ci_check.sh",
        ".github/workflows/ci.yml",
    ):
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "scripts/check_v0610_release_prep.py --post-release" in text
        assert "scripts/check_v0611_release_prep.py --release-prep" in text
        assert "scripts/historical_release_checkers/" not in text
