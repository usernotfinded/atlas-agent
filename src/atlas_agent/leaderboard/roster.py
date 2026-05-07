from __future__ import annotations

from pathlib import Path

from atlas_agent.leaderboard.vals_finance_agent import (
    DEFAULT_BENCHMARK_URL,
    BenchmarkEntry,
    fallback_entries,
    fetch_and_parse,
)


def list_roster() -> tuple[BenchmarkEntry, ...]:
    """Returns the default benchmark entries as a reference."""
    return tuple(fallback_entries())


def update_readme_roster() -> None:
    """Updates the README.md with the latest benchmark entries as a reference."""
    readme_path = Path("README.md")
    if not readme_path.exists():
        raise ValueError("README.md not found in current directory.")
        
    content = readme_path.read_text(encoding="utf-8")
    start_marker = "<!-- ATLAS_MODEL_ROSTER_START -->"
    end_marker = "<!-- ATLAS_MODEL_ROSTER_END -->"
    
    if start_marker not in content or end_marker not in content:
        raise ValueError(f"Missing {start_marker} or {end_marker} in README.md.")
    
    # Try to fetch live, fall back to built-in list
    try:
        models = fetch_and_parse(DEFAULT_BENCHMARK_URL)[:7]
    except Exception:
        models = fallback_entries()[:7]
    
    table_lines = [
        "| Rank | Model | Score |",
        "|---|---|---|"
    ]
    
    for model in models:
        rank = str(model.rank)
        model_name = model.model_name
        score_str = f"{model.score:.2f}%" if model.score is not None else "N/A"
        
        table_lines.append(f"| {rank} | {model_name} | {score_str} |")
        
    table_content = "\n".join(table_lines)
    
    start_idx = content.find(start_marker) + len(start_marker)
    end_idx = content.find(end_marker)
    
    new_content = content[:start_idx] + "\n\n" + table_content + "\n\n" + content[end_idx:]
    readme_path.write_text(new_content, encoding="utf-8")
