from __future__ import annotations

from atlas_agent.leaderboard.vals_finance_agent import parse_benchmark_html


def test_parser_extracts_model_entries_from_fixture_html() -> None:
    html = """
    <html><body>
      Updated: 5/4/2026
      <table>
        <tr><th>Rank</th><th>Model</th><th>Provider</th><th>Accuracy</th></tr>
        <tr><td>1</td><td>Claude Opus 4.7</td><td>Anthropic</td><td>64.37%</td></tr>
        <tr><td>2</td><td>DeepSeek V4</td><td>DeepSeek</td><td>60.39%</td></tr>
      </table>
    </body></html>
    """

    entries = parse_benchmark_html(html)

    assert entries[0].rank == 1
    assert entries[0].model_name == "Claude Opus 4.7"
    assert entries[0].score == 64.37
    assert entries[0].benchmark_updated == "2026-05-04"
    assert entries[1].provider == "deepseek"


def test_parser_handles_missing_score() -> None:
    html = """
    <table>
      <tr><th>Rank</th><th>Model</th><th>Provider</th><th>Accuracy</th></tr>
      <tr><td>1</td><td>GPT 5.5</td><td>OpenAI</td><td></td></tr>
    </table>
    """

    entries = parse_benchmark_html(html)

    assert entries[0].model_name == "GPT 5.5"
    assert entries[0].score is None


def test_parser_handles_page_structure_change_gracefully() -> None:
    assert parse_benchmark_html("<html><body>No leaderboard here.</body></html>") == []


def test_parser_extracts_key_takeaway_entries() -> None:
    html = """
    <p>Updated: 5/4/2026</p>
    <p>Claude Opus 4.7 is the current top performer on Finance Agent,
    scoring 64.37% accuracy. Claude Sonnet 4.6 follows with 63.33%,
    Muse Spark with 60.59%, DeepSeek V4 with 60.39%, and
    Claude Opus 4.6 (Thinking) with 60.05%.</p>
    """

    entries = parse_benchmark_html(html)

    assert [entry.model_name for entry in entries[:3]] == [
        "Claude Opus 4.7",
        "Claude Sonnet 4.6",
        "Muse Spark",
    ]
