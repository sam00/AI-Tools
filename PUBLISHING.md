# Publishing TokenTrim to GitHub

Step-by-step guide to publish this package as a public GitHub repository, plus
optional steps for releasing to PyPI. Everything here is local and reproducible.

---

## 0. Prerequisites

- Python 3.9+ and `git`
- A GitHub account
- (Optional, for PyPI) a [PyPI](https://pypi.org) account and API token

---

## 1. Set your repository URL

The project metadata uses a placeholder owner (`samgupta`). Replace it with your
GitHub username/org in **`pyproject.toml`** (`[project.urls]`) and, optionally,
the links in `README.md` and `CHANGELOG.md`.

```bash
# from the project root, replace OWNER with your GitHub username/org
OWNER=your-github-username
sed -i '' "s#sam00/AI-Tools#$OWNER/tokentrim#g" pyproject.toml CHANGELOG.md README.md   # macOS
# Linux: sed -i "s#sam00/AI-Tools#$OWNER/tokentrim#g" pyproject.toml CHANGELOG.md README.md
```

---

## 2. Pre-publish checklist (verify locally)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

ruff check src tests        # lint must pass
pytest -q                   # all tests must pass
tokentrim perf              # sanity: prints token + cost savings
```

**Data hygiene (already verified):**
- No proprietary or internal data is tracked. Confirm with:
  ```bash
  git ls-files                                       # only package files are listed
  git grep -iE 'company-name|internal-host|\.corp\b' # should return nothing
  ```
- The only secret-like strings are **synthetic fixtures** in
  `tests/test_redact_store.py` used to test the redaction feature.
- `.venv/`, `.tokentrim/`, caches, and `.env` are git-ignored.

---

## 3. Create the GitHub repo and push

**Option A — GitHub CLI (`gh`):**
```bash
gh repo create tokentrim --public --source=. --remote=origin --push
```

**Option B — manual:**
1. Create an empty public repo named `tokentrim` on GitHub (no README).
2. Then:
```bash
git remote add origin https://github.com/your-github-username/tokentrim.git
git branch -M main
git push -u origin main
```

CI (`.github/workflows/ci.yml`) runs lint + tests on Python 3.9–3.12 for every
push and PR.

---

## 4. Tag a release

```bash
git tag -a v0.1.0 -m "TokenTrim v0.1.0"
git push origin v0.1.0
```

Then draft a GitHub Release from the tag and paste the `0.1.0` section of
`CHANGELOG.md` as the notes.

---

## 5. (Optional) Publish to PyPI

```bash
pip install build twine
python -m build                 # creates dist/*.whl and dist/*.tar.gz
twine check dist/*
twine upload dist/*             # prompts for your PyPI token
```

After that, anyone can `pip install tokentrim`.

> Tip: to automate PyPI releases on tag, add a workflow that runs `python -m build`
> and `pypa/gh-action-pypi-publish`, storing your PyPI token as the
> `PYPI_API_TOKEN` repository secret. Not included by default because it requires
> that secret to exist.

---

## 6. Install-from-GitHub (for your users)

```bash
pip install "git+https://github.com/your-github-username/tokentrim.git"
# with extras:
pip install "tokentrim[all] @ git+https://github.com/your-github-username/tokentrim.git"
```
