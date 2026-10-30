# Architecture

This document describes how Dark Knight QA is structured today and the
boundaries that future modules must respect. It separates what exists in the
repository from what is planned, so it can be trusted as a reference.

## Principles

These come from the [README](README.md) and apply to every module.

- **Markdown-first:** records are human-readable, portable, and
  version-controlled. SQLite, when added, is only a rebuildable index.
- **Evidence before conclusion:** a result is declared only from observable
  execution data. AI output is a recommendation, never evidence.
- **Controlled execution:** destructive, intrusive, production, credential,
  and external write actions require explicit authorization.
- **Immutable history:** finalized executions are never silently overwritten.
- **Portable:** Windows, Linux, and macOS are first-class targets.
- **Explicit errors:** failures keep their diagnostic context and never turn
  into success-shaped fallbacks.

## Layers

```text
presentation   CLI (Typer), later the Textual TUI
     |
application    use cases that coordinate domain rules
     |
domain         requirements, cases, plans, executions, evidence
     |
infrastructure Markdown storage, logging, configuration, adapters
```

Dependencies point downward only. Domain rules never import presentation
code, so the same rules can be driven by the CLI, the TUI, or tests.

## Current layout

Only the foundation exists. Everything else in the roadmap is planned.

```text
src/qa_workbench/
  main.py          Typer application and the `qa-workbench` entry point
  core/
    config.py      AppConfig: TOML file plus environment overrides
    logging.py     Console and file logging with secret redaction
  projects/
    models.py      Project and Environment: validated, secret-free records
    repository.py  ProjectRepository: project.yaml + README.md on disk
    errors.py      ProjectError hierarchy with diagnostic context
    cli.py         `qa-workbench project ...` commands
  tui/
    app.py         WorkbenchApp: the three-area shell and status bar
    keymap.py      Shortcuts: defaults, overrides, conflict detection (pure)
    palette.py     Command palette entries (pure)
    commands.py    Textual command provider backed by palette.py
    components/    Reusable widgets: badge, metric, detail, table, logs, ...
    layout.py      Terminal size -> region visibility (pure, no widgets)
    navigation.py  Sidebar sections and destinations (pure data)
    status.py      Status names, symbols, and tones (pure)
    theme.py       Dark theme tokens and shell stylesheet
tests/             Pytest suite mirroring the package layout
```

### Projects

A project is a folder under the data directory:

```text
<data_dir>/projects/PROJ-001/
  project.yaml   name, description, status, repository, directory,
                 environments, frameworks, languages, commands, timestamps
  README.md      human-readable summary
```

- **Commands:** `qa-workbench project create | list | show | archive`, and
  `qa-workbench tui --project PROJ-001` to open the shell on a project.
- **Ids:** sequential and never reused, even after archiving.
- **Archiving:** sets `status: archived` and keeps every file; nothing is
  deleted, so history is preserved.
- **Secrets:** `project.yaml` rejects unknown fields (such as `token`) and
  URLs with embedded credentials. Keep secrets out of project files.
- **Timestamps:** ISO 8601 with a timezone offset.
- **Writes:** atomic (temporary file, then replace), so a crash never leaves a
  half-written record.
- **Errors:** an unreadable or invalid record raises `InvalidProjectError`
  naming the file and the reason. `list` reports corrupt projects as warnings
  and exits with an error instead of silently skipping them.

### TUI shell

`qa-workbench tui` opens `WorkbenchApp`, which composes persistent
navigation, main content, a contextual panel, and a status bar. Decisions
live in pure modules (`layout`, `navigation`, `status`); widgets only render
them, so business rules stay out of presentation code.

| Terminal | Navigation | Content | Context |
|---|---|---|---|
| Wide (100+ columns) | sidebar | center | side panel |
| Medium (80-99) | sidebar | center | drawer, `F2` |
| Narrow (under 80) | menu, `F1` | single column | drawer, `F2` |
| Short (under 24 rows) | unchanged | tighter spacing | unchanged |

The shell reacts to resize events and never uses fixed coordinates. It is
fully keyboard-driven. Every status is shown as a symbol and a name (for
example `✓ PASSED`), never by color alone. Modules that are not implemented
yet say so explicitly instead of showing placeholder data.

### Keyboard shortcuts

Shortcuts are defined once, in `tui/keymap.py`, and used by the bindings, the
status bar, the help text, and the command palette.

| Key | Action |
|---|---|
| `F1` | Show or hide the navigation menu |
| `F2` | Show or hide the context panel |
| `Ctrl+K` | Command palette: go to any page or run an action |
| `Ctrl+L` | Focus the search field of the current page, if it has one |
| `Esc` | Close a dialog, then the menu or context drawer |
| `?` | List the shortcuts |
| `Ctrl+Q` | Quit |

Override any of them in `config.toml`:

```toml
[shortcuts]
toggle_context = "f3"
command_palette = "ctrl+p"
```

An unknown action, an empty key, a key reserved by the terminal (`Ctrl+C`,
`Ctrl+Z`, `Ctrl+S`, `Ctrl+D`), or two actions on the same key makes
`qa-workbench tui` exit with an error that names the problem, instead of
starting with a broken keymap. `Ctrl+B` (browser preview) and `Ctrl+P`
(project picker) from the visual specification are not bound yet because the
features behind them do not exist.

### Reusable components

Components live in `tui/components/`. They take data and callbacks, hold no
business rules, and never call integrations. Search and filtering logic is in
pure functions so it can be tested without a terminal.

| Component | Purpose |
|---|---|
| `StatusBadge` | A status as symbol and name, tone color as a secondary cue |
| `MetricPanel` | A labeled number; a missing value is `n/a`, never `0` |
| `DetailPanel` | Labeled fields of the selected item |
| `DataTable` | Keyboard-navigable rows with an empty state; rejects ragged rows |
| `LogViewer` | Scrollable log with timestamps, levels, and search |
| `EmptyState`, `LoadingState`, `ErrorState` | No data, waiting, and failure; errors keep their diagnostic detail |
| `ConfirmationDialog` | Modal confirm/cancel; Esc cancels, destructive dialogs start on Cancel |

Not built yet because their subsystems do not exist: `BrowserPreview`,
`AgentChat`, and `EvidenceViewer`.

### Configuration

`AppConfig.load()` resolves values in this order, highest priority first:

1. environment variables (`DARK_KNIGHT_CONFIG_DIR`, `DARK_KNIGHT_DATA_DIR`,
   `DARK_KNIGHT_LOG_LEVEL`, `DARK_KNIGHT_LOG_FILE`);
2. the `[application]` table of `config.toml` in the configuration directory;
3. platform defaults (`APPDATA`/`LOCALAPPDATA` on Windows,
   `~/Library/Application Support` on macOS, XDG directories elsewhere).

Invalid input raises `ConfigurationError`. The message names the offending
file, and the original parser error is kept as the exception cause. The CLI
turns it into a usage error instead of continuing with defaults.

### Logging

`configure_logging()` installs a console handler and an optional file
handler. Every handler carries `SecretRedactionFilter`, which masks values
that follow keys such as `password`, `token`, `api_key`, or `authorization`.
Redaction is a safety net, not permission to log secrets.

## Planned subsystems

These are targets, not available functionality. See the roadmap in the
README for order.

| Subsystem | Responsibility |
|---|---|
| Requirements Intelligence | Analyze requirements, ambiguity, and testability |
| Test Operations | Cases, suites, plans, risks, exit criteria |
| Execution Engine | Recoverable executions with explicit state and failure types |
| Browser Agent | Authorized Playwright sessions and browser evidence |
| API Verification | Contracts, schemas, authentication, timing |
| Pipeline Intelligence | CI jobs, logs, artifacts, probable failure context |
| Issue Operations | GitHub/GitLab through replaceable adapters |
| Evidence Vault | Screenshots, logs, network data, hashes, sources |
| AI Coordination | Replaceable providers behind one contract |

External systems (issue trackers, AI providers, browsers) sit behind
adapters so they can be replaced and faked in tests.

## Traceability

```text
requirement -> acceptance criteria -> test case -> suite -> plan
            -> execution -> evidence / logs -> observed result
            -> defect or pipeline -> QA report
```

Every link answers one question: why do we believe this result?

## Quality gates

Pull requests must pass the `Python quality` jobs (pytest, `ruff check`,
`ruff format --check` on Python 3.12 to 3.14) and the repository hygiene job.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the local commands.

## Changing the architecture

Open an issue before changing a layer boundary, the persistence format,
security behavior, or compatibility guarantees. Update this document in the
same pull request as the change.
