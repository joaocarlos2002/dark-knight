# Dark Knight QA

Terminal-native AI Quality Assurance Workbench.

This repository is being built from the product and visual specifications
in [`docs/product-spec.md`](docs/product-spec.md) and
[`docs/design/tui-screen-spec.md`](docs/design/tui-screen-spec.md).

## Status

The project is in the foundation and requirements-definition phase.
Requirements, acceptance criteria, roadmap phases, and issue planning are
tracked in [`docs/requirements.md`](docs/requirements.md) and
[`docs/issue-catalog.md`](docs/issue-catalog.md).

## Principles

- Terminal-first TUI using Textual.
- Markdown with YAML frontmatter as the official persistence format.
- Rebuildable indexes only; no mandatory server database.
- Evidence-based results: the execution engine is authoritative.
- Human approval for external, destructive, or high-risk actions.
- Cross-platform support for Windows, Linux, and macOS where dependencies allow.

## Planned stack

Python 3.12+, `uv`, Textual, Rich, Typer, Pydantic, asyncio, HTTPX, and
Playwright.

