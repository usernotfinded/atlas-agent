# Python Interpreter Portability

Atlas Agent requires Python >= 3.11. The shell wrappers in `scripts/` resolve the interpreter through a single helper so that local environments can override the default without editing files.

## How the interpreter is selected

`scripts/python_env.sh` exports `resolve_python_bin()` and `require_python_311()`:

1. If the environment variable `PYTHON_BIN` is set, use it verbatim.
2. Otherwise, if `python3.11` is on `PATH`, use it.
3. Otherwise, fall back to `python`.
4. `require_python_311` verifies the selected interpreter is Python 3.11 or newer.

All wrapper scripts (`dev_check.sh`, `ci_check.sh`, `release_check.sh`, `smoke_check.sh`, `local_quick_check.sh`) source this helper and then invoke Python as `"$PYTHON_BIN"`. Any remaining bare `python` calls in these wrappers should be treated as a bug.

## Pyenv-specific behavior

In a pyenv-managed shell, `python3.11` is provided by a shim. The shim resolves the actual binary based on the *active* pyenv version (global, local, or shell). If the active version does not provide `python3.11` and no system `python3.11` exists on `PATH`, running `python3.11` produces:

```text
pyenv: python3.11: command not found
```

This is an environment issue, not a repository bug. It can happen when:

- `pyenv global` points to a version other than 3.11 (e.g., 3.14.0).
- The repository has no `.python-version` file pinning a 3.11.x version.
- `/opt/homebrew/bin/python3.11` (or another system Python 3.11) is not on `PATH` for pyenv to fall back to.

## Mitigations

Choose one of the following, ordered from most robust to most explicit:

1. **Set a local pyenv version** in the repository root:

   ```bash
   pyenv local 3.11.9   # or whichever 3.11.x you have installed
   ```

2. **Use `PYTHON_BIN`** to point directly at a working interpreter:

   ```bash
   PYTHON_BIN=/opt/homebrew/bin/python3.11 ./scripts/release_check.sh --quick
   ```

3. **Activate a 3.11 virtualenv** before running checks. A compatible virtualenv's `python` binary satisfies `require_python_311`, and `resolve_python_bin` will fall back to it if `python3.11` is not available.

## What not to do

- Do not change wrapper scripts to hardcode a personal interpreter path.
- Do not set `PYTHON_BIN=python` on an untested Python version (e.g., 3.14); the test suite is validated on 3.11 and may be slower or fail on newer interpreters.
- Do not remove `require_python_311`; doing so would allow the check suite to run on unsupported Python versions and weaken the release gate.

## Checking your local interpreter

```bash
source scripts/python_env.sh
PYTHON_BIN="$(resolve_python_bin)"
echo "Selected interpreter: $PYTHON_BIN"
require_python_311 "$PYTHON_BIN"
"$PYTHON_BIN" --version
```

If the above prints `Python 3.11.x` and exits `0`, the wrappers will work.
