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

The first time you run it, with no project yet, the workbench welcomes you and
asks for a project name and, if you have one, the URL of its GitLab repository.
It creates the project, opens it, and asks whether it may read from that
GitLab server (the token comes from `GITLAB_TOKEN`; nothing is sent until you
say yes). With exactly one project, `batman` opens it directly next time.

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

API tokens (GitLab, AI providers) do not have to be exported in every terminal:
`batman config token set gitlab` asks for the token without echo and keeps it in
your configuration folder, `batman config token show` lists which ones are set
(never their values), and `batman config token remove gitlab` deletes it. An
environment variable of the same name (`GITLAB_TOKEN`) still takes precedence.
The password of a protected OpenCode server is kept the same way:
`batman config token set opencode` (the user name stays `opencode` unless
`OPENCODE_SERVER_USERNAME` says otherwise). The same can be done in the TUI,
under Settings > API tokens, and the first-run welcome offers to keep the GitLab
token after your project is created. `batman doctor` lists each token as set or
not, and whether it comes from the environment or from the stored value.

A hosted model is available through the NVIDIA API Catalog. It is remote, so it
is opt-in: keep the key with `batman config token set nvidia` (or set
`NVIDIA_API_KEY`), allow the host for the project with
`batman security set -p PROJ-001 --allow-host integrate.api.nvidia.com --by NAME`,
then `batman ai models -p PROJ-001` lists the models the key can use and
`batman ai ask "..." -p PROJ-001 --engine nvidia --model MODEL` asks one. In
Alfred, `Ctrl+G` picks the model. `auto` never uses it, `batman ai status -p
PROJ-001` shows whether it is reachable, and `batman doctor` shows whether a key
is present. Questions and the records they mention leave your machine; secrets
are redacted first and nothing is sent to a host you did not allow.

If you have Claude Code, Claude is available as an engine with no API key: it
uses your own Claude login. Allow its host once for the project
(`batman security set -p PROJ-001 --allow-host api.anthropic.com --by NAME`),
then `batman ai ask "..." -p PROJ-001 --engine claude [--model sonnet|opus|haiku]`,
or pick `claude` under Engine in Alfred (`Ctrl+O`). The `claude` program is found
on your PATH or inside the VS Code extension; set `CLAUDE_CODE_PATH` if it lives
elsewhere. Claude Code runs with every tool turned off, so it can only answer: it
cannot read files or run commands. Like NVIDIA it is remote, so `auto` never uses it.

Requirements can come from the GitLab group wiki: `batman gitlab wiki -p PROJ-001`
lists the pages under `Requisitos/`, and `batman requirements import-wiki -p PROJ-001`
imports them as draft requirements (or press `W` on the Requirements page). The
group defaults to the project's group; pass `--group` to choose another. Run it
again to pick up changes: pages that changed go back to draft for review.

The code of the repository can be read without leaving the tool:
`batman gitlab branches|tree|file|code ... -p PROJ-001` (add `--ref` for a
branch, `--url` for another repository), or the Repository page in the menu.
Large and binary files are refused, and secrets in code are masked.

To upgrade, run `uv tool upgrade dark-knight-qa` (or `pipx upgrade
dark-knight-qa`). The first run creates its data folder on its own; where it
lives and how to change it is described under Contributing below.

## Current status

**Working prototype // v0.2.0**

The workbench installs as one package and runs on Linux, Windows, and macOS (CI
tests all three and smoke-tests the installed wheel). The CLI covers the whole
workflow, and the terminal interface has a page for each area. It is not
published to PyPI yet and has not had a stable release.

### Roadmap

- [x] CLI, TUI shell, and project lifecycle
- [x] Markdown storage and knowledge base
- [x] Requirements and test case management
- [x] Test planning and reusable suites
- [x] Recoverable execution engine
- [x] Playwright browser agent and terminal preview
- [x] API testing and evidence collection
- [x] CI/CD pipeline analysis (GitLab)
- [ ] GitHub and GitLab integrations (GitLab only: reads and approved comments;
      there is no GitHub adapter yet)
- [x] Bug hunting and release analysis
- [x] Authorized security testing
- [ ] Advanced AI provider orchestration (providers, tools, and the evidence rule
      exist; AI actions do not go through the action guard yet)

Every external action the tool takes on its own (browser, API tests, GitLab
reads, security checks, comments) is checked against the project's authorized
hosts, rate-limited, and written to a tamper-evident audit log. Risky ones wait
for a person's approval.

## Documentation and operations

The local product documentation is intentionally kept in `docs/` for the
current project workspace. Repository collaboration policies are public:

- [Architecture](ARCHITECTURE.md)
- [Examples](examples/README.md): sample files and a first session, step by step
- [Contributing](CONTRIBUTING.md)
- [Releasing](RELEASING.md)
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

Opening the workbench can start with a fullscreen cinematic: a random video
from a folder of Batman edits plays before the terminal user interface appears.
Put the edits in `assets/batman-edits` inside the project (or point `edits_dir`
somewhere else):

```toml
[startup]
splash = true
edits_dir = "assets/batman-edits"
player = "ffplay"
```

The edits can also live in a separate GitHub repository, keeping the videos out
of this one. `batman edits fetch` downloads a tagged archive and copies its
videos into `edits_dir`; on the first launch with an empty folder the same
fetch runs automatically. `ref` defaults to the repository's default branch:

```toml
[startup]
repo = "owner/dark-knight-edits"
ref = "edits-v1"
sha256 = "..."   # optional: SHA-256 of the downloaded archive
```

`batman edits list` shows what the splash can choose from. For a private
repository, set `DARK_KNIGHT_EDITS_TOKEN` (or `GITHUB_TOKEN`) with read access.

The splash needs `ffplay`, `mpv`, or `vlc` on `PATH`; `player` forces a
specific executable. A relative `edits_dir` resolves from the project root. It
only runs when the workbench is opened in an interactive terminal, and any key
or click skips it. Pass `--no-splash` to `batman` or `batman tui` to open the
workbench directly.

Keyboard shortcuts can be remapped in the same file; see
[ARCHITECTURE.md](ARCHITECTURE.md) for the list of actions:

```toml
[shortcuts]
toggle_context = "f3"
```

Supported overrides are `DARK_KNIGHT_CONFIG_DIR`, `DARK_KNIGHT_DATA_DIR`,
`DARK_KNIGHT_LOG_LEVEL`, `DARK_KNIGHT_LOG_FILE`, `DARK_KNIGHT_SPLASH`,
`DARK_KNIGHT_EDITS_DIR`, `DARK_KNIGHT_SPLASH_PLAYER`, `DARK_KNIGHT_EDITS_REPO`,
`DARK_KNIGHT_EDITS_REF`, and `DARK_KNIGHT_EDITS_SHA256`. Secrets are redacted
from application logs; do not place credentials in configuration files.

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
uv run qa-workbench ai ask "Is login covered?" -p PROJ-001 --engine auto
uv run qa-workbench gitlab pipelines -p PROJ-001 --status failed
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
