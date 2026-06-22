# Contributing to TokenTrim

Thanks for your interest in improving TokenTrim!

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"
```

## Workflow

1. Create a branch: `git checkout -b feature/my-change`.
2. Make your change. Keep the **core dependency-free** — third-party packages
   belong behind an optional extra in `pyproject.toml`.
3. Add or update tests under `tests/`.
4. Run the checks:
   ```bash
   pytest -q
   ruff check src tests
   ```
5. Open a pull request describing the change and the measured token savings, if relevant.

## Design principles

- **Local-first & deterministic.** No network calls and no LLM rewriting in the core. Same input ⇒ same output.
- **Fail open.** A compressor must never raise on malformed input — return the input unchanged instead.
- **Reversible.** If a compressor drops content, the original must remain recoverable via the CCR store.
- **Measure it.** New compressors should ship with a sample in `samples.py` so `tokentrim perf` reflects them.

## Adding a new compressor

1. Implement the `Compressor` protocol in `src/tokentrim/compressors/`.
2. Register it for a `ContentType` in `compressors/__init__.py`.
3. Add detection rules in `router.py` if it's a new content type.
4. Add unit tests and a representative sample.

## Code style

- Python 3.9+ compatible.
- `ruff` for linting/formatting (`line-length = 100`).
- Type hints on public functions.

## License

By contributing, you agree your contributions are licensed under Apache-2.0.
