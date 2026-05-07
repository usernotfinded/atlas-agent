# Serverless Jobs

Serverless jobs are useful for closed-market research, learning, reflection,
reporting, and memory updates. Use provider secret stores for keys and keep live
execution behind the same policy gates used in local and VPS runs.

Serverless is best for scheduled non-continuous work. Keep direct broker
execution in the guarded Atlas path, with approvals and audit logs intact.

Good serverless candidates:

- pre-market research
- closed-market simulation
- learning and reflection
- report generation
- guarded Git sync

Do not place secrets in job definitions, logs, generated reports, or memory
files.
