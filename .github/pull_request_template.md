## Summary

<!-- Brief description of what this PR changes. -->

## Safety Checklist

- [ ] I did not add live trading enablement
- [ ] I did not add broker/order submission paths
- [ ] I did not add provider execution unlocks
- [ ] I did not add credentials/secrets/examples
- [ ] I did not weaken forbidden-claim/path-leak checks
- [ ] I did not stage generated artifacts (`build/`, `dist/`, `*.egg-info/`, temp dirs, `.venv/`)
- [ ] Protected boundary diff is clean, or explicitly justified

Check protected boundaries:

```bash
git diff -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
git diff --cached -- src/atlas_agent/config src/atlas_agent/brokers src/atlas_agent/execution src/atlas_agent/safety src/atlas_agent/risk
```

Expected: no output (or explicitly justified).

## Tests

List commands run and results:

```bash
# Example:
./scripts/release_check.sh --quick
# Result: All dev checks passed.
```

## Docs

- [ ] Docs updated if behavior or public interfaces changed
- [ ] No forbidden claims added to public docs
- [ ] No absolute paths added to public docs
