<p align="center">
  <img src="assets/wayne-signal.gif" alt="Dark Knight QA - Wayne Industries quality engineering signal" width="100%">
</p>

<h1 align="center">DARK KNIGHT QA</h1>

<p align="center">
  <strong>WAYNE INDUSTRIES // QUALITY ENGINEERING DIVISION</strong><br>
  <em>Observe everything. Prove everything. Ship with confidence.</em>
</p>

<p align="center">
  <a href="https://github.com/joaocarlos2002/dark-knight/actions/workflows/repository.yml">
    <img src="https://github.com/joaocarlos2002/dark-knight/actions/workflows/repository.yml/badge.svg" alt="Repository checks">
  </a>
  <a href="https://github.com/joaocarlos2002/dark-knight/releases">
    <img src="https://img.shields.io/badge/version-v0.2.0-b08d57?style=flat-square&labelColor=111827" alt="Version 0.2.0">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-MIT-b08d57?style=flat-square&labelColor=111827" alt="MIT License">
  </a>
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/python-3.12%2B-b08d57?style=flat-square&labelColor=111827" alt="Python 3.12 or newer">
  </a>
</p>

> **Internal designation:** `DK-QA / FOUNDATION-0.2.0`
> **Mission:** turn fragmented QA activity into traceable, evidence-backed engineering intelligence.

## The mission

Modern quality work is scattered across requirements, test cases, browser
sessions, API calls, CI pipelines, issues, screenshots, and conversations
with AI. Dark Knight QA is being built as the command center for that work:
a terminal-native quality engineering workbench for teams that need more than
an automated test result.

It is designed to help a QA engineer:

- understand a requirement before testing it;
- plan tests by risk, scope, and evidence;
- execute manual, assisted, browser, API, and automated flows;
- preserve the evidence behind every conclusion;
- investigate failures without inventing root causes;
- connect requirements, cases, executions, defects, and releases.

**The engine observes. The evidence decides. AI assists.**

## Command center

| Subsystem | Purpose |
|---|---|
| **Requirements Intelligence** | Analyze requirements, acceptance criteria, ambiguity, and testability. |
| **Test Operations** | Create cases, techniques, suites, plans, risks, and exit criteria. |
| **Execution Engine** | Track recoverable executions with explicit state and failure types. |
| **Browser Agent** | Drive authorized Playwright sessions and collect browser evidence. |
| **API Verification** | Validate contracts, schemas, authentication, rules, timing, and flows. |
| **Pipeline Intelligence** | Inspect CI jobs, logs, artifacts, and probable failure context. |
| **Issue Operations** | Connect findings to GitHub/GitLab issues through replaceable adapters. |
| **Evidence Vault** | Preserve screenshots, logs, network data, hashes, and source references. |
| **AI Coordination** | Use replaceable providers without treating generated text as evidence. |

> Availability depends on the current roadmap. This repository is in the
> foundation phase; the table describes the target system, not completed
> functionality.

## Architecture doctrine

```text
┌─────────────────────────────────────────────────────────────────────┐
│                    DARK KNIGHT QA WORKBENCH                         │
├───────────────┬──────────────────┬──────────────────┬───────────────┤
│  REQUIREMENTS │  TEST OPERATIONS │   EXECUTION      │  INTELLIGENCE  │
│  cases / risk │  plans / suites  │   browser / API  │  AI / reports  │
├───────────────┴──────────────────┴──────────────────┴───────────────┤
│              TRACEABILITY + EVIDENCE + AUDIT HISTORY                │
├─────────────────────────────────────────────────────────────────────┤
│         MARKDOWN + YAML FRONTMATTER  │  OPTIONAL SQLITE INDEX        │
└─────────────────────────────────────────────────────────────────────┘
```

### Non-negotiable principles

- **Markdown-first:** records remain human-readable, portable, and
  version-controlled. SQLite is only a rebuildable index.
- **Evidence before conclusion:** no result is declared without observable
  data from the execution engine.
- **AI with boundaries:** facts, hypotheses, recommendations, and
  inconclusive results stay distinct.
- **Controlled execution:** destructive, intrusive, production, credential,
  and external write actions require explicit authorization.
- **Immutable history:** finalized executions are not silently overwritten.
- **Portable by design:** Windows, Linux, and macOS are first-class targets
  wherever dependencies permit.

## Technology stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Interface | Textual TUI, Rich, Typer |
| Domain models | Pydantic |
| Async and HTTP | `asyncio`, HTTPX |
| Browser automation | Playwright |
| Persistence | Markdown + YAML frontmatter |
| Local index | SQLite (optional and rebuildable) |
| AI | Built-in provider contract, OpenCode, optional Ollama |
| Quality gates | Pytest, CI, linting, formatting, security checks |

## Traceability protocol

```text
REQUIREMENT
    └── ACCEPTANCE CRITERIA
        └── TEST CASE
            └── SUITE
                └── TEST PLAN
                    └── EXECUTION
                        ├── EVIDENCE
                        ├── LOGS
                        └── OBSERVED RESULT
                            └── DEFECT / PIPELINE
                                └── QA REPORT
```

Every link exists to answer one question: **why do we believe this result?**

## Install and run

The package installs everything the workbench needs (the terminal interface,
the CLI, and their libraries) and adds one command to your terminal:

```bash
batman
```

Running `batman` with no arguments opens the workbench. `batman --help` lists
the commands (`batman project create`, `batman requirements import`, and so
on); `qa-workbench` and `python -m qa_workbench` are the same program.

Install it as a standalone tool, so it is available in every terminal without
touching your Python projects. It needs Python 3.12 or newer:

```bash
uv tool install dark-knight-qa     # or: pipx install dark-knight-qa
```

The package is not published to PyPI yet. Until it is, install it from a clone of
this repository:

```bash
git clone https://github.com/joaocarlos2002/dark-knight.git
uv tool install ./dark-knight      # or: pipx install ./dark-knight
```

The browser used for web tests (Chromium) is a separate download. The first
time you need it, `batman` explains and installs it after you confirm; you can
do it ahead of time with `batman doctor --fix`, and `batman doctor` tells you
whether it is ready. `batman browser run URL` opens a page, saves a screenshot,
and shows the browser inside the workbench (`Ctrl+B`).

To upgrade, run `uv tool upgrade dark-knight-qa` (or `pipx upgrade
dark-knight-qa`). The first run creates its data folder on its own; where it
lives and how to change it is described under Contributing below.

## Current status

**Foundation phase // v0.2.0**

The product specification, requirements, visual direction, issue catalog, and
repository collaboration standards are established. Core application modules
are intentionally being implemented in small, reviewable phases.

### Roadmap

- [ ] CLI, TUI shell, and project lifecycle
- [ ] Markdown storage and knowledge base
- [ ] Requirements and test case management
- [ ] Test planning and reusable suites
- [ ] Recoverable execution engine
- [ ] Playwright browser agent and terminal preview
- [ ] API testing and evidence collection
- [ ] CI/CD pipeline analysis
- [ ] GitHub and GitLab integrations
- [ ] Bug hunting and release analysis
- [ ] Authorized security testing
- [ ] Advanced AI provider orchestration

## Documentation and operations

The local product documentation is intentionally kept in `docs/` for the
current project workspace. Repository collaboration policies are public:

- [Architecture](ARCHITECTURE.md)
- [Contributing](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)
- [Support](SUPPORT.md)
- [Changelog](CHANGELOG.md)

## Contributing

This is an early-stage open-source engineering project. Start with an
existing issue, keep changes focused, preserve the architecture doctrine,
and include reproducible validation evidence in every pull request.

```bash
git clone https://github.com/joaocarlos2002/dark-knight.git
cd dark-knight
uv sync --extra dev
uv run qa-workbench --help
```

Global configuration can be provided through a platform-appropriate
`config.toml` or environment variables:

```toml
[application]
data_dir = "~/.local/share/dark-knight-qa"
log_level = "INFO"
log_file = "~/.local/share/dark-knight-qa/qa-workbench.log"
```

Keyboard shortcuts can be remapped in the same file; see
[ARCHITECTURE.md](ARCHITECTURE.md) for the list of actions:

```toml
[shortcuts]
toggle_context = "f3"
```

Supported overrides are `DARK_KNIGHT_CONFIG_DIR`, `DARK_KNIGHT_DATA_DIR`,
`DARK_KNIGHT_LOG_LEVEL`, and `DARK_KNIGHT_LOG_FILE`. Secrets are redacted from
application logs; do not place credentials in configuration files.

Projects are managed from the CLI and stored under the data directory:

```bash
uv run qa-workbench project create "Shop" --repository acme/shop \
  --environment staging=https://staging.example.com
uv run qa-workbench project list
uv run qa-workbench tui --project PROJ-001
uv run qa-workbench requirements import requirements.md --project PROJ-001
uv run qa-workbench requirements coverage --project PROJ-001
uv run qa-workbench cases create "Log in" -p PROJ-001 --objective "Validate login" \n  --step "Open the page" --step "Submit => Dashboard is shown" \n  --expected-result "The user is authenticated" --requirement REQ-001
uv run qa-workbench suites create Smoke -p PROJ-001 --type smoke --case TC-001
uv run qa-workbench executions create -p PROJ-001 --type manual --executor Ana --environment staging --case TC-001
uv run qa-workbench executions move EXEC-001 -p PROJ-001 --to planned
uv run qa-workbench reports execution EXEC-001 -p PROJ-001 --save
uv run qa-workbench reports traceability -p PROJ-001
uv run qa-workbench api run users-api.yaml -p PROJ-001
uv run qa-workbench plans recommend -p PROJ-001 --requirement REQ-001 --budget 120
uv run qa-workbench review pending --project PROJ-001
uv run qa-workbench review decide REQ-001 -p PROJ-001 --decision approved --reviewer Ana
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## License

Released under the [MIT License](LICENSE).

<p align="center">
  <br>
  <strong>WAYNE INDUSTRIES // DARK KNIGHT QA</strong><br>
  <em>See beyond the test. Understand the quality.</em>
</p>
