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
tests/             Pytest suite mirroring the package layout
```

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
