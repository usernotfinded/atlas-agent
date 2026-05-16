from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

from atlas_agent.config import AtlasConfig
from atlas_agent.workspace import WorkspaceResolution


@dataclass(frozen=True)
class CLIContext:
    args: argparse.Namespace
    config: AtlasConfig
    resolution: WorkspaceResolution
    update_checker: Callable[[], str | None] | None = None
