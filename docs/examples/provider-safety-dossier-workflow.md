# Provider Safety Dossier Workflow Example

This page shows a safe, copy-paste workflow for discovering and exporting provider safety dossiers.

All commands are **read-only** or **local-only**. They do not submit orders, call brokers, load credentials, or enable network access.

## Prerequisites

- An Atlas workspace initialized with `atlas init <workspace>`
- A completed research chain that produced a `provider_safety_dossier` artifact

## Step 1: Discover the latest valid dossier

```bash
atlas research provider-safety-dossier-latest --json
```

Expected safe output fields:

- `found: true`
- `safe_status: "sandbox_chain_complete"`
- `sandbox_only: true`
- `export_available: true`

If no valid dossier exists, the command returns:

- `found: false`
- `reason: "no_provider_safety_dossier_found"`

## Step 2: List complete dossiers

```bash
atlas research provider-safety-dossier-list --status sandbox_chain_complete --limit 5 --json
```

This returns up to 5 dossiers with a complete, valid chain. Items include safe metadata only; no absolute paths or raw invalid fields are exposed.

## Step 3: Export a dossier to Markdown

Replace `<DOSSIER_ID>` with the actual `artifact_id` from step 1 or 2.

```bash
atlas research provider-safety-dossier-export <DOSSIER_ID> --format markdown --output reports/provider-safety-dossier.md
```

The export creates a human-readable Markdown file inside the workspace. The CLI output shows:

- `Dossier ID`
- `Output` (workspace-relative path)
- `Format`

The JSON envelope includes `output_path_relative` and `output_path_redacted: true`.

## Step 4: Inspect the exported Markdown

```bash
cat reports/provider-safety-dossier.md
```

The Markdown report contains:

- Dossier metadata (ID, hash, created_at)
- Chain lineage with artifact hashes
- Safety verdict and sandbox status
- A statement that the pipeline is offline and mock-only

## Safety reminders

- The entire workflow is **sandbox-only** and **offline**.
- **Provider execution remains locked** — no real provider calls are made.
- **Trust remains blocked** — mock responses are not trusted.
- **No broker/order path** — no orders, approvals, or broker contact.
- **No credentials loaded** — `.env.atlas` is not read.
- **No network enabled** — all artifacts are local.
- **Not financial advice** — this is a safety audit report, not trading guidance.
- **Safety validation does not imply profitability or trading correctness** — The dossier validates structural safety, not strategy performance.
