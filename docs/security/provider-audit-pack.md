# Provider Audit Pack

## Provider audit pack

`atlas providers audit-pack` creates a local end-to-end audit package for provider preflight evidence.

It runs the dry-run provider preflight chain, builds an evidence index, renders a Markdown report, exports a compact JSON summary, and writes an audit pack manifest.

The command is local-only and non-authorizing. It does not call providers, load credentials, use the network, touch brokers, or enable execution.

## Usage

```bash
atlas providers audit-pack \
  --provider openrouter \
  --model "openrouter/auto" \
  --purpose "research-summary" \
  --max-context-chars 4000 \
  --output-dir artifacts/provider_audit_pack/<timestamp>
```

## Output files

The audit pack is written as a flat local directory:

```text
call-plan.json
validation-report.json
manifest.json
sha256sums.txt
smoke-report.json
evidence-index.json
evidence-report.md
evidence-summary.json
audit-pack-manifest.json
```

`audit-pack-manifest.json` records stage completion, relative file names, closed safety state, `manual_review_required: true`, and `non_authorizing: true`.

## Safety boundaries

- No provider call is made.
- No network is used.
- No credentials or `.env.atlas` values are loaded.
- No broker, execution, risk, or live-trading path is touched.
- No pending order is created.
- No order is approved.
- The generated pack is audit evidence only and does not authorize provider or broker execution.

## Audit pack verification

`atlas providers verify-audit-pack <pack_dir>` verifies that an existing audit pack is complete, internally consistent, and acceptable for external review.

The command checks required files, validates embedded artifacts, rejects secret-like values, rejects absolute paths, rejects executable/script files, verifies closed safety summaries, and confirms that the pack is non-authorizing.

The command is local-only. It does not call providers, load credentials, use the network, touch brokers, or enable execution.
