# Contributing to Dark Knight QA

Thank you for helping build Dark Knight QA. The project is in its
foundation phase, so small, focused contributions are especially valuable.

## Before you start

1. Read the [README](README.md) and the [architecture overview](ARCHITECTURE.md).
2. Check existing issues before opening a new one.
3. For architectural, security, persistence, or compatibility changes,
   describe the proposal in an issue before implementing it.
4. Do not include credentials, private data, real customer evidence, or
   unredacted logs in commits or issue reports.

## Development workflow

1. Create a branch from `master`.
2. Link your pull request to an issue.
3. Keep each pull request focused on one coherent change.
4. Add or update tests and documentation when behavior or public contracts
   change.
5. Run the relevant checks locally and report the exact commands and results.
6. Request review only after the pull request checklist is complete.

### Branches and commits

- Name branches `<type>/<short-description>`, for example
  `feat/project-foundation` or `docs/architecture-and-workflow`.
- Use Conventional Commit prefixes: `feat`, `fix`, `docs`, `test`, `style`,
  `build`, `ci`, `chore`.
- Keep each commit small and focused on one change, with a short imperative
  subject such as `test: cover invalid configuration failure paths`.
- Pull request descriptions link the issue with `Closes #N` and list the
  validation commands that were run.

### Review checklist

A pull request is ready for review when:

- `uv run pytest`, `uv run ruff check .`, and `uv run ruff format --check .`
  pass locally;
- normal, invalid-input, and failure paths of new behavior are tested;
- errors keep their diagnostic context and do not fall back silently;
- [ARCHITECTURE.md](ARCHITECTURE.md), the README, and the changelog are
  updated when structure or behavior changes;
- no credentials, cookies, personal data, private logs, or real evidence are
  committed.

## Local setup

The project uses Python 3.12+ and `uv`.

```bash
uv sync --extra dev
uv run qa-workbench --help
uv run qa-workbench --version
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Checking the installed package

CI runs the tests on Linux, Windows, and macOS, and installs the built wheel
into a clean environment on each of them. To reproduce that locally:

```bash
rm -rf build dist src/*.egg-info   # stale build output leaks old modules into the wheel
uv build --wheel
uv venv /tmp/clean-env              # outside the repository
uv pip install --python /tmp/clean-env/bin/python dist/*.whl
cd /tmp && /tmp/clean-env/bin/python /path/to/repo/.github/scripts/smoke_installed.py
```

On Windows use `Scripts\python.exe` instead of `bin/python`. The script runs the
installed commands and opens every page of the TUI headlessly.

## Design expectations

- Preserve the Markdown-first source of truth.
- Keep domain rules separate from presentation.
- Prefer explicit errors over silent fallbacks.
- Preserve Windows, Linux, and macOS compatibility where dependencies allow.
- Treat AI output as recommendations; execution evidence is authoritative.

## Commit and pull request titles

Use a short imperative title, for example:

```text
Add project metadata validation
```

Pull requests should explain the problem, the solution, scope boundaries,
testing evidence, compatibility impact, and any security considerations.

## Releases

The project uses Semantic Versioning. Releases are created automatically; do
not push tags by hand.

To release, open a pull request that updates, in the same commit:

- [VERSION](VERSION);
- `version` in [pyproject.toml](pyproject.toml);
- [CHANGELOG.md](CHANGELOG.md), with a `## [X.Y.Z]` entry.

When the pull request is merged into `master`, the release workflow checks
that the three agree, creates the `vX.Y.Z` tag, and publishes a GitHub release
with notes generated from merged pull requests. If the release already exists,
the workflow does nothing.

## Questions

Use [GitHub Discussions](https://github.com/joaocarlos2002/dark-knight/discussions)
for design questions and [Issues](https://github.com/joaocarlos2002/dark-knight/issues)
for actionable bugs and work items.
