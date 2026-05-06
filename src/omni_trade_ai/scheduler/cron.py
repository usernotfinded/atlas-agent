from __future__ import annotations


def cron_hint(routine: str) -> str:
    return f"0 9 * * 1-5 omni-trade scheduler run --routine {routine} --mode paper"

