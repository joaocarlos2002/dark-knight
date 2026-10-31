# Changelog

All notable changes to Dark Knight QA are documented in this file.

The project follows [Semantic Versioning](https://semver.org/). Release tags
use the `vMAJOR.MINOR.PATCH` format.

## [Unreleased]

### Added

- TUI pages: Overview with the project's real numbers and recent executions, and
  Projects to choose, create, and archive projects from the workbench; `Ctrl+R`
  reloads the page from disk, and `batman` opens the only project automatically.
- A form dialog component with inline validation.
- Authorized browser navigation: every navigation goes through the action guard,
  a project's allowed hosts are enforced inside Chromium (including redirects and
  subresources), and without a project only local addresses open (#41, #44).
- Bug hunting: `BUG` records classified as reproduced, suspected, false positive,
  environment unavailable, or inconclusive; a defect is never confirmed without
  steps, expected and observed results, intact evidence, and two reproductions,
  with `batman bugs record|reclassify|list|show` (REQ-032).
- Release analysis from real commits, merge requests, and changed files: explainable
  risk areas, impacted cases, recommended suites, and a regression recommendation,
  saved as sealed `REL` records, with `batman release analyze|list|show` (REQ-032).
- Authorized security checks: explicit, scoped, expiring, audited authorization;
  passive checks for headers, disclosure, cookies, CORS, HTTPS redirect, and
  unauthenticated access; confirmed findings kept apart from hypotheses; sanitized
  results with no certification claim, with `batman security-tests ...` (REQ-031).
- Execution reports now say whether a referenced defect record exists.
- Approved comment publishing: drafts that require real evidence and authorized
  links, approval bound to the exact text, outcomes recorded as published, failed,
  or unknown, and an audit trail, with `batman comments draft|publish|list|show`
  and a GitLab note writer (REQ-027).
- Approvals, autonomy modes, and security controls: `assisted`,
  `semi_autonomous`, and `controlled_autonomous` modes, nine always-sensitive
  action categories, per-project authorized hosts, rate limits and timeouts,
  single-use expiring approvals bound to the exact action, cancellation, and a
  hash-chained audit log, with `batman security show|set|approvals|approve|deny|audit`
  (REQ-030, NFR-005, NFR-010).
- AI provider contract (availability, models, completion, streaming, tools,
  structured output, cancellation, timeouts, typed errors), engine selection
  (`own`, `opencode`, `auto`), and the built-in agent whose answers separate
  facts, hypotheses, recommendations, and inconclusive findings, demote facts
  without a verifiable source, and treat outside text as untrusted data
  (REQ-028, REQ-029). `batman ai status|ask`.
- Ollama adapter (local runtime) and OpenCode adapter on its documented server
  API, with explicit unsupported-capability errors and cancellation (REQ-028).
- A random fullscreen Batman edit plays before the workbench opens, chosen from
  `assets/batman-edits` (configurable with `[startup] edits_dir`), with the
  terminal minimized first on Windows, no player controls, any key or click to
  skip, and `--no-splash` to bypass it. Uses `ffplay`, `mpv`, or `vlc`.
- The startup edits can live in a separate GitHub repository: `batman edits
  fetch` downloads a tagged zip archive, verifies an optional SHA-256, and copies
  the videos into `edits_dir`; the first interactive launch fetches them
  automatically when the folder is empty. `batman edits list` shows the
  available edits, private repositories read `DARK_KNIGHT_EDITS_TOKEN` (or
  `GITHUB_TOKEN`), and any failure is reported without blocking the workbench.
- GitLab adapter for issues (description, labels, comments), commits, and merge
  requests with their changed files, behind replaceable ports, with `batman gitlab
  issues|issue|commits|commit|mrs|mr`; external text is marked as untrusted data
  (REQ-026).
- GitLab adapter for pipelines, jobs, logs, and artifacts with the specification's
  states, a rule that only a reported success counts as passed, and
  `batman gitlab pipelines|pipeline|log|artifacts|artifact`; job logs are masked
  and trimmed; failures (token, permission, not found, rate limit, server,
  unreachable) are explicit (REQ-026, NFR-010).
- API test runner on HTTPX: methods, parameters, payloads, bearer/basic/header
  authentication from environment variables, status, timing, header, schema and
  value checks, and chained flows, with `batman api run|list|show` (REQ-024).
- Sanitization of requests, responses, headers, URLs, and tokens before they are
  saved, including values the run itself used or extracted, with a final leak
  check that refuses to write a result that still looks like it holds a
  credential (REQ-025, NFR-005).
- Browser Agent on Playwright behind a replaceable port: navigation, clicks,
  forms, text and visibility checks, screenshots, trace, video, console, network
  and HTTP-failure capture, with browser faults, failed checks, and screenshot
  failures kept apart, and evidence registered with hashes (REQ-021).
- Browser Preview in the TUI: `headless`, `preview`, and `visible` modes, a panel
  that follows the browser without blocking it, `Ctrl+B` to hide and show it with
  the latest image kept, `F5`/`F6` and `batman browser control` for mode and
  pause, with restart-bound changes deferred honestly (REQ-022, REQ-023).
- Guided Chromium setup: `batman doctor [--fix]`, `batman browser install`, and a
  first-run prompt that explains the download; `batman browser run|status|control`.
- A `batman` command: installing the package puts `batman` in the terminal, and
  running it without arguments opens the workbench. `qa-workbench` and
  `python -m qa_workbench` remain as the same program.
- Execution reports (the ten sections of the specification, explicit
  limitations, nothing inferred), a requirement-to-evidence traceability trace
  and matrix, saved reports that detect when they are stale, and
  `reports execution|traceability|trace` (REQ-032).
- The CLI now writes UTF-8 even when its output is piped on Windows, so status
  symbols no longer crash it.
- Incremental, recoverable executions: steps saved before and after they run,
  recovery of interrupted runs without inventing outcomes, reruns that never
  overwrite, corrections as separate events, and failure classification
  (product, test, infrastructure, evidence collection) (REQ-019, REQ-020,
  NFR-004).
- Executions with a validated lifecycle (created, planned, awaiting approval,
  running, results, finalized), five execution types, data rules tied to state,
  approvals, and sealing on finalization, plus `executions create|move|list|show|
  states` and `evidence add|list|verify` (REQ-017, REQ-018).
- Reusable test suites with many-to-many case membership (union of the suite
  and case sides), safe add/remove, verification, and
  `suites create|list|show|add|remove|membership|verify` (REQ-015).
- Test plans with scope, strategy, risks, criteria, owners, and schedule, a
  selection stored with a reason for every inclusion and exclusion, an
  explainable recommendation that states what it could not consider, and
  verification of the selection, plus `plans create|list|show|recommend|verify`
  (REQ-014, REQ-016).
- Human review workflow for AI-generated requirements and test cases: required
  provenance, approval only through a recorded review by someone other than the
  generator, and findings classified as fact, hypothesis, recommendation, or
  inconclusive with real sources, plus `review pending|submit|decide`
  (REQ-013, REQ-029).
- Test cases with the fields of the specification, validation, a secret check,
  and six design techniques (equivalence partitioning, boundary values, decision
  tables, state transitions, use cases, exploratory) with derived conditions,
  plus `cases create|list|show` (REQ-011, REQ-012).
- Requirement import from Markdown and text with source, hash, and author
  preserved, plus `requirements list` and `requirements coverage`
  (REQ-009, REQ-010).
- Immutable history for finalized records (sealed with SHA-256, corrections as
  hash-chained events) and evidence registration with integrity verification
  (NFR-004, NFR-008).
- Rebuildable SQLite full-text index and search over Markdown records, with
  incremental sync and explicit errors for damaged indexes (REQ-008, REQ-032).
- Markdown frontmatter repository: UTF-8 records with YAML frontmatter,
  stable ids with the specified prefixes, immutable `id` and `created_at`,
  timestamps with a timezone, and validation of metadata and relative links
  (REQ-006, REQ-007, NFR-003).
- Reusable TUI components (status badge, metric and detail panels, data table,
  searchable log viewer, empty/loading/error states, confirmation dialog) and
  a command palette on `Ctrl+P` (REQ-004, REQ-005, NFR-006, NFR-007).
- Wayne Industries visual identity: palette tokens with contrast checks,
  corporate header and footer, a brand block above the navigation, and a
  navigation grouped into workspace, operations, and intelligence.
- `WARNING` and `AI PROCESSING` statuses.
- Centralized keyboard shortcuts, configurable through a `[shortcuts]` table in
  `config.toml`, with conflict and reserved-key detection.
- Project lifecycle: `qa-workbench project create|list|show|archive`, stored
  as `project.yaml` and `README.md`, and `qa-workbench tui --project`
  (REQ-002, REQ-003).
- Responsive Textual application shell, opened with `qa-workbench tui`
  (REQ-004, REQ-005, NFR-006, NFR-007), with the three-area layout from 100
  columns.

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
