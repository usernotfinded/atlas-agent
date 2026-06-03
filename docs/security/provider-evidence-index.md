# Provider Evidence Index

The Provider Evidence Index is a local-only registry and audit tool for provider preflight and readiness artifacts.

## Overview

The `evidence-index` module scans a given directory for known JSON artifacts and generates a cryptographic index. It ensures that any artifacts stored on disk are tracked, validated, and hashes are preserved.

This is NOT a database. It is a generated JSON ledger designed to provide evidence to an external auditor (or CI pipeline) that the preflight/readiness constraints were respected.

## Commands

```bash
# Build an index
atlas providers evidence-index build --root <path_to_scan> --output index.json

# Inspect an existing index
atlas providers evidence-index inspect index.json
```

## Security Guarantees

- **Local Only:** Scans local files. Makes no network calls.
- **Secret Redaction Check:** It enforces that no artifact containing secret-like strings (`api_key`, `sk-`, `token`) is marked valid.
- **Absolute Path Check:** Ensures artifacts do not leak the user's filesystem structure (using relative paths).
- **Safety Flags Verified:** These constraints guarantee that evidence cannot perform unauthorized network execution or leak local disk files through symlinks.

## Evidence index reports

`atlas providers evidence-index report <index.json>` renders a Markdown audit report for human reviewers.

`atlas providers evidence-index export-summary <index.json>` writes a compact machine-readable summary.

Reports are local-only and non-authorizing. They do not call providers, load credentials, use the network, touch brokers, or enable execution.
