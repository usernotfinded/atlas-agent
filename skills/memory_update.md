# Memory Update Skill

Use at the end of every routine.

Inputs: routine result, report path, order result, risk result, research summary.

Outputs: appended Markdown updates to memory files.

Safety rules: append history instead of erasing; do not write secrets; preserve pending order IDs and rejection reasons; only rewrite strategy rules with explicit justification.

Failure modes: missing memory directory, malformed existing notes, accidental secret insertion.

Example: append market-open order result to `memory/trade_journal.md`.

