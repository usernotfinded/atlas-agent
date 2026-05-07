from __future__ import annotations


def cron_hint(routine: str) -> str:
    return f"0 9 * * 1-5 atlas scheduler run --routine {routine} --mode paper"

