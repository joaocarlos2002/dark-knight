# Changelog

All notable changes to Dark Knight QA are documented in this file.

The project follows [Semantic Versioning](https://semver.org/). Release tags
use the `vMAJOR.MINOR.PATCH` format.

## [Unreleased]

### Added

- Project lifecycle: `qa-workbench project create|list|show|archive`, stored
  as `project.yaml` and `README.md`, and `qa-workbench tui --project`
  (REQ-002, REQ-003).
- Responsive Textual application shell, opened with `qa-workbench tui`
  (REQ-004, REQ-005, NFR-006, NFR-007).

## [0.2.0] - 2026-10-30

### Added

- Installable Python package with the `qa-workbench` CLI.
- Cross-platform configuration (TOML and environment overrides) and logging
  with secret redaction.
- Python quality CI with tests, ruff lint, and format checks (NFR-009).
- Tests for configuration failure paths.
- Architecture overview and expanded contribution workflow (NFR-009).

## [0.1.0] - 2026-10-30

### Added

- Initial open source repository foundation.
- Product, requirements, visual, and issue planning documents.
- Community contribution, support, conduct, and security policies.
- GitHub issue and pull request templates.
- Repository hygiene checks and Dependabot configuration.

[0.2.0]: https://github.com/joaocarlos2002/dark-knight/releases/tag/v0.2.0
[0.1.0]: https://github.com/joaocarlos2002/dark-knight/releases/tag/v0.1.0
