from __future__ import annotations

from atlas_agent.reports.generator import generate_report
from atlas_agent.reports.renderers import render_json_string, render_markdown
from atlas_agent.reports.writer import write_report


def generate_adhoc_report(
    workspace: str = ".",
    output_dir: str = "reports",
    output_format: str = "markdown",
) -> str:
    """Generate an ad-hoc report using real local data and write it to output_dir.

    Returns the path to the written report file.
    """
    data = generate_report("ad-hoc", workspace=workspace, output_format=output_format)  # type: ignore[arg-type]
    if output_format == "json":
        content = render_json_string(data)
        path = write_report("adhoc-report", content, output_dir=output_dir, extension="json")
    else:
        content = render_markdown(data)
        path = write_report("adhoc-report", content, output_dir=output_dir)
    return str(path)
