from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from atlas_agent.safety.atomic_write import atomic_write_json, atomic_write_text


def test_atomic_write_text_creates_target(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    atomic_write_text(target, "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_atomic_write_json_serializes_payload(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    payload = {"a": 1, "b": [2, 3]}
    atomic_write_json(target, payload, sort_keys=True)
    assert json.loads(target.read_text(encoding="utf-8")) == payload


def test_temp_file_is_in_same_directory(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "target.json"
    atomic_write_json(target, {"x": 1})
    assert target.exists()
    assert target.parent.exists()


def test_temp_file_name_is_unique(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"n": 1})
    atomic_write_json(target, {"n": 2})
    # Two completed writes should leave exactly one target file, no leftover
    # fixed temp name, and a valid final payload.
    assert not (tmp_path / "target.json.tmp").exists()
    assert json.loads(target.read_text(encoding="utf-8")) == {"n": 2}


def test_no_fixed_target_tmp_name(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"x": 1})
    assert not (tmp_path / "target.json.tmp").exists()


def test_old_file_preserved_on_write_failure(tmp_path: Path, monkeypatch: Any) -> None:
    target = tmp_path / "target.json"
    target.write_text("old", encoding="utf-8")

    def failing_write_text(self: Path, data: str, **kwargs: Any) -> int:
        raise RuntimeError("write failed")

    monkeypatch.setattr(Path, "write_text", failing_write_text)

    with pytest.raises(RuntimeError, match="write failed"):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"


def test_old_file_preserved_on_replace_failure(tmp_path: Path, monkeypatch: Any) -> None:
    target = tmp_path / "target.json"
    target.write_text("old", encoding="utf-8")

    def failing_replace(self: Path, target: Path) -> Path:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "new")

    assert target.read_text(encoding="utf-8") == "old"


def test_temp_file_cleaned_up_on_success(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"x": 1})
    # Only the target should remain; no visible fixed temp file.
    assert list(tmp_path.iterdir()) == [target]


def test_temp_file_cleaned_up_on_failure(tmp_path: Path, monkeypatch: Any) -> None:
    target = tmp_path / "target.json"
    target.write_text("old", encoding="utf-8")

    def failing_replace(self: Path, target: Path) -> Path:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", failing_replace)

    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "new")

    # The unique temp file should have been removed best-effort.
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())


def test_chmod_best_effort(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"x": 1}, chmod=0o600)
    assert target.exists()
    # Best-effort only; some platforms/filesystems ignore or restrict modes.
    try:
        mode = target.stat().st_mode
        assert mode & 0o777 == 0o600
    except (OSError, AssertionError):
        pytest.skip("platform does not support requested mode")


def test_invalid_parent_raises(tmp_path: Path) -> None:
    # Create a regular file where the parent directory is expected.
    bogus_parent = tmp_path / "not_a_dir"
    bogus_parent.write_text("i am a file", encoding="utf-8")
    target = bogus_parent / "target.json"

    with pytest.raises(OSError):
        atomic_write_json(target, {"x": 1})

    assert not target.exists()


def test_invalid_json_payload_raises_without_touching_target(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("old", encoding="utf-8")

    with pytest.raises((TypeError, ValueError)):
        atomic_write_json(target, {"self": object()})  # type: ignore[dict-item]

    assert target.read_text(encoding="utf-8") == "old"


def test_repeated_rapid_writes_do_not_collide(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    for i in range(100):
        atomic_write_json(target, {"value": i})
    assert json.loads(target.read_text(encoding="utf-8")) == {"value": 99}
    assert not (tmp_path / "target.json.tmp").exists()


def test_parallel_writes_do_not_raise_file_not_found(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    errors: list[BaseException] = []

    def writer(value: int) -> None:
        try:
            atomic_write_json(target, {"value": value})
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert json.loads(target.read_text(encoding="utf-8"))["value"] in range(20)


def test_no_partial_file_observed(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"version": 0}, sort_keys=True)

    observations: list[dict[str, Any]] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                if target.exists():
                    content = target.read_text(encoding="utf-8")
                    observations.append(json.loads(content))
            except (json.JSONDecodeError, OSError):
                observations.append({"error": "partial or unreadable"})

    def writer(value: int) -> None:
        atomic_write_json(target, {"version": value}, sort_keys=True)

    reader_thread = threading.Thread(target=reader)
    reader_thread.start()

    writer_threads = [
        threading.Thread(target=writer, args=(i,)) for i in range(1, 51)
    ]
    for t in writer_threads:
        t.start()
    for t in writer_threads:
        t.join()

    stop.set()
    reader_thread.join()

    for obs in observations:
        assert "error" not in obs, "observed partial or unreadable file"
        assert obs.get("version") in range(51)


def test_concurrent_writers_old_file_preserved_on_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    target = tmp_path / "target.json"
    atomic_write_json(target, {"version": 0}, sort_keys=True)

    call_count = 0
    original_replace = Path.replace

    def flaky_replace(self: Path, other: Path) -> Path:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise OSError("injected replace failure")
        return original_replace(self, other)

    monkeypatch.setattr(Path, "replace", flaky_replace)

    errors: list[BaseException] = []

    def writer(value: int) -> None:
        try:
            atomic_write_json(target, {"version": value}, sort_keys=True)
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=writer, args=(i,)) for i in range(1, 11)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # At least the first writer failed; target must still contain valid JSON
    # from a successful write (either the original or a later successful one).
    assert any(isinstance(e, OSError) and "injected" in str(e) for e in errors)
    final = json.loads(target.read_text(encoding="utf-8"))
    assert "version" in final
    assert final["version"] in range(11)
