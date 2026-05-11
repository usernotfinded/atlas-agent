# Release Checklist

Run this before pushing a public GitHub release.

- `pytest`
- `python -m pip install -e . --no-build-isolation`
- `atlas --help`
- `atlas init demo --template routine-trader`
- `cd demo && atlas validate`
- `atlas discipline setup --manual --yes`
- `atlas config set market.symbol DEMO-SYMBOL`
- `atlas routine run pre_market --mode paper`
- Secret scan across `README.md`, `docs/`, `templates/`, `routines/`, `skills/`, `src/`, `tests/`, and `.env.example`
- Confirm no runtime personal data is committed
- Confirm `README.md` reflects current commands and safety behavior
- Confirm `LICENSE` exists
- Confirm `DISCLAIMER.md` exists
- Confirm package install works
- Confirm GitHub Actions workflow generation works
- Confirm live mode fails safely by default
- Confirm paper routine works

