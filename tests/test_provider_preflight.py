import json
from pathlib import Path
from unittest.mock import patch

from atlas_agent.cli import main


def test_provider_preflight_success(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "custom-plan.json"

    args = [
        "providers", "preflight",
        "--provider", "openrouter",
        "--model", "openrouter/auto",
        "--purpose", "research-summary",
        "--max-context-chars", "4000",
        "--output", str(output_path),
    ]
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert "Generated dry-run call-plan artifact" in captured.out
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "provider_call_plan"
    assert payload["schema_version"] == 1
    assert payload["provider_id"] == "openrouter"
    assert payload["model_id"] == "openrouter/auto"
    assert payload["purpose"] == "research-summary"
    assert payload["max_context_chars"] == 4000

    # Assert safety flags are false
    flags = payload["safety_flags"]
    assert flags["provider_enabled"] is False
    assert flags["network_enabled"] is False
    assert flags["credentials_loaded"] is False
    assert flags["outbound_request_sent"] is False
    assert flags["response_received"] is False
    assert flags["broker_touched"] is False
    assert flags["live_trading_enabled"] is False
    assert flags["pending_order_created"] is False
    assert flags["order_approved"] is False
    assert flags["payload_body_stored"] is False

    # Assert no raw bodies are stored
    minimization = payload["payload_minimization_summary"]
    assert minimization["raw_prompt_body_stored"] is False
    assert minimization["raw_request_body_stored"] is False
    assert minimization["raw_response_body_stored"] is False
    assert minimization["hashes_only"] is True


def test_provider_preflight_json_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    args = [
        "providers", "preflight",
        "--provider", "anthropic",
        "--model", "claude-3",
        "--purpose", "test",
        "--json",
    ]
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    envelope = json.loads(captured.out)
    assert envelope["ok"] is True
    assert envelope["command"] == "atlas providers preflight"

    out_path = Path(envelope["data"]["artifact_path"])
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["provider_id"] == "anthropic"


def test_provider_preflight_invalid_inputs_rejected(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    invalid_cases = [
        # Empty provider
        ["--provider", "", "--model", "test", "--purpose", "test"],
        # Too long provider (>64)
        ["--provider", "a" * 65, "--model", "test", "--purpose", "test"],
        # Control characters
        ["--provider", "test\x00", "--model", "test", "--purpose", "test"],
        # Newlines
        ["--provider", "test\n", "--model", "test", "--purpose", "test"],
        # Absolute path
        ["--provider", "test", "--model", "/etc/passwd", "--purpose", "test"],
        # Secret fragment
        ["--provider", "test", "--model", "test", "--purpose", "api_key_stuff"],
    ]

    for flags in invalid_cases:
        args = ["providers", "preflight"] + flags
        code = main(args)
        assert code == 2


def test_provider_preflight_no_api_key_leakage(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    output_path = tmp_path / "secret-test.json"

    # Set fake API keys
    fake_keys = {
        "OPENAI_API_KEY": "fake_sk_openai_123",
        "ANTHROPIC_API_KEY": "fake_sk_ant_123",
        "OPENROUTER_API_KEY": "fake_sk_or_123",
        "MOONSHOT_API_KEY": "fake_sk_moon_123",
        "XAI_API_KEY": "fake_sk_xai_123",
        "GEMINI_API_KEY": "fake_sk_gemini_123",
    }
    for k, v in fake_keys.items():
        monkeypatch.setenv(k, v)

    args = [
        "providers", "preflight",
        "--provider", "openrouter",
        "--model", "openrouter/auto",
        "--purpose", "research",
        "--output", str(output_path),
    ]
    code = main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert output_path.exists()

    # Verify no fake keys leaked in stdout/stderr
    for val in fake_keys.values():
        assert val not in captured.out
        assert val not in captured.err

    # Verify no fake keys leaked in the generated artifact
    artifact_content = output_path.read_text(encoding="utf-8")
    for val in fake_keys.values():
        assert val not in artifact_content


def test_provider_preflight_module_imports_are_safe():
    """Verify that the module does not import provider SDKs or network libraries."""
    import ast
    from atlas_agent.providers import provider_preflight

    source = Path(provider_preflight.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_imports = {
        "openai", "anthropic", "requests", "urllib", "http", "socket", "httpx"
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split('.')[0]
                assert base not in forbidden_imports, f"Forbidden import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            base = node.module.split('.')[0] if node.module else ""
            assert base not in forbidden_imports, f"Forbidden import from: {node.module}"


def test_provider_preflight_does_not_touch_protected_boundaries():
    """Verify that the preflight command does not interact with live trading or brokers."""
    from atlas_agent.providers import provider_preflight

    with patch("atlas_agent.brokers.resolver.BrokerResolver") as mock_resolver:
        provider_preflight.generate_call_plan_artifact(
            provider_id="test",
            model_id="test",
            purpose="test",
        )
    mock_resolver.assert_not_called()
