# Releasing

Releases are cut by changing one file. Pushing a new `VERSION` to `master`
starts the **Release** workflow (`.github/workflows/release.yml`), which checks
the version and creates the GitHub release with generated notes. Nothing is
published to PyPI yet.

## What must agree

The workflow refuses to release unless all of these hold, so check them first:

| Where | Rule |
|---|---|
| `VERSION` | `MAJOR.MINOR.PATCH`, for example `0.3.0`. |
| `pyproject.toml` | `[project].version` is exactly the same. |
| `CHANGELOG.md` | has a heading `## [0.3.0]` for it. |

`tests/test_release_files.py` runs the same checks in the normal test suite, so a
mismatch fails a pull request instead of failing the release.

## Steps

1. **Pick the version** (Semantic Versioning). While the project is `0.x`, a new
   feature raises the minor number and a fix only the patch number.
2. **Update the changelog.** Rename `## [Unreleased]` to `## [0.3.0] - YYYY-MM-DD`
   and add a fresh, empty `## [Unreleased]` above it.
3. **Set the version** in `VERSION` and in `pyproject.toml`.
4. **Verify a clean install** of exactly what will be released. From a clean
   checkout (stale build output can leak files from another branch, so remove
   it first):

   ```bash
   rm -rf build dist
   uv build --wheel
   python -m venv /tmp/release-check            # a folder outside the repository
   /tmp/release-check/bin/pip install dist/*.whl
   /tmp/release-check/bin/batman --version      # prints the new version
   /tmp/release-check/bin/batman doctor         # reports the browser state
   ```

   On Windows the commands are the same with `Scripts\` instead of `bin/`.
5. **Open the pull request.** CI runs lint, formatting, and the full test suite
   on every supported Python.
6. **Merge to `master`.** The Release workflow creates the tag `v0.3.0` and the
   release. If the release already exists the workflow does nothing, so a
   re-run is safe.

## After the release

- Check the release page and its notes.
- Users upgrade with `uv tool upgrade dark-knight-qa` (or
  `pipx upgrade dark-knight-qa`); until the package is published to PyPI they
  reinstall from the repository with `uv tool install --force .`.

## Browsers are not part of the package

Playwright's Chromium is a separate download. The application handles it: the
first command that needs it explains the download and asks, and
`batman doctor --fix` does it ahead of time. A release does not need to ship it.
