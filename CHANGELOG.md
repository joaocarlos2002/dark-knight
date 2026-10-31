# Changelog

All notable changes to Dark Knight QA are documented in this file.

The project follows [Semantic Versioning](https://semver.org/). Release tags
use the `vMAJOR.MINOR.PATCH` format.

## [Unreleased]

### Changed

- Alfred's settings are picked, not typed: `Ctrl+O` opens a menu to choose the
  engine, the model (listed from the engine), the style, and the answer language
  (English, Português (Brasil), Español, Français, Deutsch, Italiano). Only the
  server addresses are still typed. A question without a model now says to press
  `Ctrl+G`.

### Changed

- The TUI shell was simplified. The header is one line (product on the left,
  project on the right); the Wayne Industries / Gotham City branding, the
  tagline, and the corporate footer line are gone; the footer is one line, and the
  shortcuts of the current page show on their own line (the bar used to have no
  room and never appeared). The menu groups are separated by a blank line, list
  pages give the table and the detail their own space, and the context panel opens
  on demand with `F2` instead of taking space on wide terminals.

### Added

- GitLab test cases: `batman gitlab test-cases` and `test-case` read them, and
  `batman cases push` (or `G` in the TUI) creates or updates a `test_case` issue
  in the team's standard layout, after a person approves the exact content. It
  never duplicates (unchanged is skipped, same title is updated) and an update
  rewrites only the changed sections (#165).
- A Review page in the TUI to read, submit, approve, reject, or ask changes on
  the records the AI generated, with its findings and sources, and the same
  rules as `batman review` (no self-approval, a reason for a rejection). The
  Overview shows how many records are waiting (#173).
- Requirements from the GitLab group wiki: `batman gitlab wiki` and `wiki-page`
  read it, `batman requirements import-wiki` (or `W` on the Requirements page)
  imports each page as a draft requirement with its source, URL, and hash, and
  business rules (`RN-...`) are recorded. Importing again skips unchanged pages
  and updates a changed one in place, back to draft (#164).
- Read a GitLab repository: `batman gitlab branches`, `tree`, `file`, and `code`
  (code search with path and line), plus a Repository page in the TUI. Files
  over 256 KB and binary files are refused with a reason, secrets are masked,
  file text is marked as untrusted, and every read goes through the guard (#168).
- Claude as an AI engine through Claude Code, with no API key: `batman ai ask
  --engine claude [--model sonnet|opus|haiku]`, or `claude` under Engine in
  Alfred. It uses your own Claude login, is found automatically (PATH, the VS Code
  extension, or `CLAUDE_CODE_PATH`), and runs with every tool disabled so it can
  only answer. It is remote: `auto` never picks it, the UI says data leaves the
  machine, secrets are redacted first, and the process starts only if
  `api.anthropic.com` is allowed for the project. `batman ai status` shows it.
- API tokens in the interface: Settings has an API tokens category to set and
  remove a token (typed hidden, never shown again), the first-run welcome offers to
  keep the GitLab token after the project is created, and `batman doctor` lists
  every token as set or not and where it comes from. The Settings page was not
  reachable from the menu before; it is now (#158).
- A hosted AI engine: `batman ai ask --engine nvidia --model MODEL` uses the NVIDIA
  API Catalog (OpenAI-compatible, configurable URL). `batman ai models` lists the
  models the key can use and Alfred's `Ctrl+G` picks one. It is remote, so `auto`
  never chooses it, the UI says data left the machine, secrets are redacted first,
  and the key (`NVIDIA_API_KEY` or `batman config token set nvidia`) is never
  printed, logged, or audited. All AI engine requests now go through the action
  guard and the audit log: a host that is not allowed gets nothing and the message
  says how to allow it. `batman ai status -p ID` and `batman doctor` show
  reachability and key presence (#159).
- `batman config token set|show|remove`: keep API tokens in the application
  instead of exporting them in every terminal. Stored outside any project, owner-only
  where the platform allows, never printed or logged; the environment variable
  still wins. GitLab reads, API tests, and the OpenCode engine (its server
  password: `batman config token set opencode`) use them.
- CI now runs the tests on Windows and macOS and installs the built wheel into a
  clean environment on all three platforms, smoke-testing the installed commands
  and every TUI page.
- TUI Reports page (spec 4.16): browse saved execution and traceability reports,
  list all evidence records with integrity status (intact/tampered), and inspect
  evidence with the new `EvidenceViewer` component showing file metadata, SHA-256
  verification result, problems, and content preview (text/JSON first 50 lines,
  images via half-block rendering). `G` regenerates the execution report for a
  selected saved report (#100).
- TUI Settings page (spec 4.19): view and edit global shortcuts (config.toml),
  per-project security settings (autonomy mode, allowed hosts, rate limits) with
  audit log entry on change, and browser defaults. Security form validates before
  saving; no secrets stored in files (#100).
- `EvidenceViewer` component in `tui/components/`: displays an EVD record with
  verification status, file details, and content preview.
- `DataTable.Highlighted` message now includes `table_id` to support pages with
  multiple tables.
- TUI Pipelines page: read the latest GitLab pipelines on demand through the
  action guard, with their jobs by stage and failure reasons; every navigation
  destination now has a page.
- Documentation (#54): an `examples/` folder (a requirements file, an API test, and a
  first session end to end, all exercised by the test suite), `RELEASING.md`
  with the release checks the workflow enforces, and a Security Policy section that
  states how the application applies its security principles and its known limits.
- TUI Executions page: follow executions with steps, evidence, and next states,
  start one from a test case, and move it through its lifecycle with the same
  validation as the CLI. Form fields can now carry a default value.
- TUI Bug Hunting, API Testing, Release Analysis, and Security pages: browse the
  saved results, and approve or deny pending approval requests from the
  workbench with the audit log's integrity shown.
- Pages register themselves from their own modules, and the docs merge with the
  `union` strategy so parallel changes do not conflict.
- TUI Test Suites and Test Plans pages: browse with search and filters, see
  members, estimates, last execution, and the plan's selection with reasons;
  create suites and plans, and add or remove cases, from forms that validate
  before saving.
- TUI Requirements and Test Cases pages: searchable, filterable lists with the
  selected record's detail (coverage, acceptance criteria, steps), importing
  requirements from a file and writing a test case from forms that validate
  before saving.
- TUI pages: Overview with the project's real numbers and recent executions, and
  Projects to choose, create, and archive projects from the workbench; `Ctrl+R`
  reloads the page from disk, and `batman` opens the only project automatically.
- A form dialog component with inline validation.
- `batman api run` now goes through the action guard: requests only reach the
  hosts a project allows, are rate-limited and audited, and a `DELETE` always
  needs approval; a request that is not allowed is never sent.
- First-run welcome: opening `batman` with no project shows a Wayne Industries
  welcome and walks through creating a project from a repository URL, then asks
  before allowing reads from that server.
- `batman gitlab ...` reads now go through the action guard: the token is only
  sent to hosts the project allows (also for `--url`), reads are rate-limited and
  audited, and a host that is not allowed never receives a request.
- Authorized browser navigation: every navigation goes through the action guard,
  a project's allowed hosts are enforced inside Chromium (including redirects and
  subresources), and without a project only local addresses open (#41, #44).
- Bug hunting: `BUG` records classified as reproduced, suspected, false positive,
  environment unavailable, or inconclusive; a defect is never confirmed without
  steps, expected and observed results, intact evidence, and two reproductions,
  with `batman bugs record|reclassify|list|show` (REQ-032).
- TUI Knowledge Base page: full-text search across requirements, cases, plans,
  executions, defects, and the rest, with a kind filter, match snippets, and
  building or syncing the rebuildable search index.
- Release analysis from real commits, merge requests, and changed files: explainable
  risk areas, impacted cases, recommended suites, and a regression recommendation,
  saved as sealed `REL` records, with `batman release analyze|list|show` (REQ-032).
- Alfred, the QA assistant, in the TUI: an AI Agent page with a reusable chat
  component, `@ID` context attachment, typed answers (facts, hypotheses,
  recommendations), and per-project settings for engine, model, style, and
  language (`Ctrl+O`).
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

### Fixed

- Alfred no longer fails with "no final answer after 6 steps" when a small model keeps
  calling tools: on the last step the tools are withheld and the model is told to
  answer, and the prompt says to answer greetings and general questions directly.

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
