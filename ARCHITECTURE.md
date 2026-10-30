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
    splash.py      Random fullscreen startup edit before the workbench
  requirements/
    schema.py      REQ record schema: statuses, priorities, criteria, tags
    parser.py      Requirements from Markdown or plain text (pure)
    importer.py    Import into a project, preserving source and author
    coverage.py    Which requirements have related test cases
    cli.py         `qa-workbench requirements ...` commands
  reports/
    traceability.py  Link graph, upstream/downstream trace, requirement matrix
    execution.py     Execution report from recorded facts
    writer.py        Save reports with a source hash; detect stale ones
    cli.py           `qa-workbench reports ...` commands
  executions/
    states.py      The lifecycle state machine and its validated transitions
    schema.py      EXEC record schema and rules tying data to state
    service.py     Create executions and move them through the lifecycle
    recording.py   Save steps as they run, before and after each one
    recovery.py    Find interrupted runs, recover, rerun, record corrections
    cli.py         `qa-workbench executions ...` commands
  evidence/
    cli.py         `qa-workbench evidence ...` commands
  suites/
    schema.py      SUITE record schema: type, status, member cases
    service.py     Create suites, add/remove cases, membership, verification
    cli.py         `qa-workbench suites ...` commands
  plans/
    schema.py      TP record schema: scope, risks, criteria, schedule, selection
    builder.py     PlanDraft, create/update, readable Markdown body
    selection.py   Explainable recommendation and verification of a selection
    cli.py         `qa-workbench plans ...` commands
  review/
    policy.py      Review and AI-provenance rules, as schema checks (pure)
    service.py     Submit for review, record human decisions, list pending
    cli.py         `qa-workbench review ...` commands
  testcases/
    schema.py      TC record schema, fields, choices, secret and technique checks
    builder.py     TestCaseDraft, create/update, readable Markdown body
    techniques.py  Six design techniques with derived test conditions
    cli.py         `qa-workbench cases ...` commands
  workspace.py     The record schemas of a project and how to open them
  storage/
    frontmatter.py Markdown + YAML frontmatter documents (parse, dump, read)
    ids.py         Stable ids such as TC-001, with the specified prefixes
    validation.py  RecordSchema, metadata checks, relative link checks
    repository.py  MarkdownRepository: create, get, update, list records
    index.py       RecordIndex: rebuildable SQLite full-text search cache
    history.py     Sealed, hash-chained history for finalized records
    evidence.py    EvidenceStore: SHA-256 registration and verification
    atomic.py      Atomic UTF-8 file writes
    errors.py      StorageError hierarchy with diagnostic context
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

### Markdown storage

Markdown with YAML frontmatter is the source of truth for QA records.
`MarkdownRepository` stores one record per file at
`<project>/<schema directory>/<ID>.md`, driven by a `RecordSchema` per record
kind (prefix, folder, allowed statuses, required fields, references). The
concrete schemas for test cases, requirements, and so on arrive with their own
features.

- **Format:** UTF-8, LF line endings (CRLF files are read and normalized),
  frontmatter fenced by `---`, Markdown body after it. Timestamps are written
  as `2026-01-01T10:00:00-03:00`, unquoted, as in the specification. Files with
  a byte order mark are rejected.
- **Ids:** `<PREFIX>-<NNN>` with the prefixes `PROJ`, `REQ`, `ISSUE`, `TC`,
  `EXEC`, `BUG`, `SEC`, `API`, `REL`, `EVD`, `TP`, `SUITE`, `PIPE`,
  `PIPE-EXEC`, and `COMMENT`. The repository assigns the next number, never
  reuses one, and refuses to change an id or `created_at`. `updated_at` is set
  by the repository on every update.
- **Validation:** required fields, id format and prefix (and that it matches the
  file name), status within the schema, timestamps with a timezone,
  `updated_at` not before `created_at`, reference fields holding ids with the
  allowed prefixes, and Markdown links that are relative, stay inside the
  project folder, and point to existing files. Every problem is reported at
  once. External `http`, `https`, and `mailto` links and anchors are not
  checked; Obsidian `[[wikilinks]]` are allowed but not checked. Records are
  validated both when written and when read, so a hand-edited file cannot slip
  through.
- **Failures:** a record that cannot be read or fails validation raises an
  error naming the file and the reasons. `list_records` reports damaged records
  as errors next to the valid ones instead of hiding them. Writes are atomic.
- **Search index:** `RecordIndex` keeps a SQLite full-text index (FTS5) at
  `<project>/indexes/records.sqlite`. It is a disposable cache and never the
  source of truth: delete it and `rebuild()` recreates it from the Markdown
  files; `sync()` updates only records whose file changed. Search ignores case
  and accents, treats each word as a prefix, requires every word, and can be
  filtered by record kind and status. Records that are damaged or invalid are
  not indexed and are reported in the `IndexReport` instead of disappearing. A
  damaged index, a different index version, or searching before the first build
  raises `SearchIndexError` explaining that rebuilding is the fix.
- **Immutable history:** a `RecordSchema` can declare `immutable_statuses`
  (for example an execution's `finalized`). When a record reaches one, the
  repository seals it: the SHA-256 of the file goes into `<ID>.history.md` as
  the first event. A sealed record cannot be edited in place
  (`RecordFinalizedError`); a correction or addition is a separate history
  event with an author, a timestamp, and a justification, added with
  `add_history_event`. Each event carries the hash of the previous one, so
  editing or removing an event, or editing the sealed record by hand, is found
  by `verify` / `verify_all` instead of going unnoticed.
- **Evidence:** `EvidenceStore` copies a file into
  `<project>/evidence/files/<EVD-id>/` (the original is never moved or
  modified) and writes an immutable `EVD` record with the SHA-256, size, media
  type, origin, description, and optionally the step, execution, source URL,
  and capture time. An annotated or processed version is registered as its own
  file and record with `derived_from` pointing at the original. `verify`
  rechecks the record seal, that the file exists and stays inside the project,
  and its size and hash. A failed registration leaves no file behind, and a
  corrupted copy is never registered.
- **Not here yet:** secret sanitization before persistence (REQ-025) and the
  execution workflow that produces finalized records.

### Requirements

`qa-workbench requirements import FILE -p PROJ-001` reads a `.md` or `.txt`
file and creates one `REQ` record per requirement; `list` and `coverage` show
them. PDF, DOCX, and XLSX are not supported yet and are refused with a clear
message.

- **Markdown:** each `##` section is a requirement (a document with only a `#`
  heading is one requirement). Leading `Key: value` lines set `Priority`,
  `Status`, `Tags`, and `Author` (Portuguese names work too); the list under
  `Acceptance criteria:` or a `### Critérios de aceitação` heading becomes the
  criteria; the rest is the description.
- **Plain text:** each block separated by blank lines is a requirement; its
  first line is the title.
- **Nothing is guessed:** an unknown priority or status is reported and that
  requirement is skipped; the others still import. A missing priority stays
  missing. Imported requirements are `draft` unless the source says otherwise.
- **Provenance:** every record keeps the file name, the line, the SHA-256 of the
  file, the format, an optional `--source-version`, the author, and the import
  time. The source file is never changed. Importing the same, unchanged file
  again skips what is already there instead of duplicating it.
- **Coverage:** a requirement is covered when at least one test case relates to
  it, written on either side (`cases` on the requirement or `requirements` on
  the case). Cases named but missing are reported, not counted.
- **Projects:** archived projects can be read but not changed.

### Test cases and design techniques

`qa-workbench cases create | list | show` manages `TC` records. A case holds
the fields of the specification: objective, preconditions, test data, steps
with an optional expected result per step, a final expected result, priority,
criticality, type, profile, compatible environments, tags, related requirements
and issues, suites, origin and author, and timestamps. Cases start as `draft`.
The structured fields in the frontmatter are the source of truth; the Markdown
body is generated from them (editing the body by hand is overwritten the next
time the case is updated through the workbench).

- **Rules:** a case needs at least one step and an expected result, except
  exploratory cases. Priority, criticality, type, and origin are closed sets.
  References must have the right prefix. The same checks run when a file is
  created and when it is read back, so hand-edited files are validated too.
- **No secrets:** literal credentials in test data, steps, or any text are
  refused (`password=hunter2`, tokens, keys); placeholders such as
  `$TEST_PASSWORD` and prose such as "enter the password" are fine.
- **Techniques:** equivalence partitioning, boundary value analysis, decision
  tables, state transitions, use cases, and exploratory charters. Each is a
  validated model that rejects inconsistent input (for example a decision table
  that does not cover every combination, or a state model with an unknown
  state) and derives test conditions (partition representatives, boundary
  values, every rule combination, valid and refused transitions, use-case
  scenarios). A case can combine several techniques, and the derived conditions
  appear in its body.

### Reports and traceability

`qa-workbench reports execution | traceability | trace` turns records into
reports. Reports are generated, never typed in: they state facts taken from the
records and nothing else.

- **Execution report:** the ten sections of the specification (identification,
  objective, environment, preconditions, procedure, expected result, observed
  result, status, evidence, conclusion), plus limitations and traceability. The
  status shows a symbol and a name. The conclusion only repeats what the record
  says (a pass cites its evidence count; a failure cites what was observed and
  what kind of failure it was; blocked, inconclusive, and cancelled cite their
  reason; a run in progress claims no conclusion).
- **Limitations are explicit:** the execution is not finalized; no evidence was
  collected; steps were not recorded one by one; steps were interrupted or the
  run was recovered; the failure was an infrastructure or test problem, not a
  product one; evidence files fail their integrity check; the finalized record
  was modified; corrections were recorded after finalization; referenced
  defects are not stored. Nothing is inferred to fill a gap.
- **Traceability:** records form the chain requirement, test case, suite, plan,
  execution, evidence or defect. A link can be written on either side, and
  `reports trace ID` follows the chain upstream and downstream without wandering
  sideways into unrelated records (two requirements that share a case do not
  show up in each other's trace). `reports traceability` prints a matrix of
  each requirement, its cases, and the latest execution of each (passed, has
  failures, not executed, in progress or inconclusive, or no test case), plus the
  gaps: requirements without cases and cases without a requirement.
- **Saved reports** go to `<project>/reports/` with the SHA-256 of the execution
  and its history. A correction recorded later makes the saved report stale, and
  `reports execution` says so. Defects and pipelines are not part of the chain
  yet because their records do not exist.

### Executions and their lifecycle

`qa-workbench executions create | move | list | show | states` runs test cases
through a lifecycle validated by the domain, not by convention:

```text
created -> planned -> awaiting_approval -> running
        -> passed | failed | blocked | inconclusive | cancelled -> finalized
```

`planned` may go straight to `running` unless the execution requires approval,
in which case it must pass through `awaiting_approval`. Cancelling is possible
until there is a result. A result can only move to `finalized`, so `blocked`,
`inconclusive`, and `cancelled` are never turned into `passed`.

- **Types:** manual, assisted manual, agent-driven, automated, and exploratory.
  Agent-driven and automated runs must name their `automation_tool` (for
  example `playwright`), and a manual or assisted run cannot, so automation
  driven by an agent is never recorded as a human execution. Only exploratory
  sessions can omit the test case.
- **Rules tied to state** (also checked when a file is read): a pass needs
  evidence and the observed result; a failure needs the observed result;
  blocked, inconclusive, and cancelled need a reason; every result needs a finish
  time, and a started execution needs a start time; the finish cannot precede
  the start; a finalized execution needs its result. Evidence is never invented:
  every cited evidence id must be a record that exists.
- **Approval:** an execution that requires approval records who approved it and
  when before it runs, and an agent cannot approve its own run.
- **Record:** type, executor, environment, version, branch, commit, test case,
  plan, suite, project, the expected result copied from the case when the
  execution was created, observed result, evidence, bugs, notes, reason, start,
  finish, and duration.
- **Finalized means sealed:** finalizing seals the record (see Immutable
  history), so it can never be edited and any change is detected.
- `evidence add | list | verify` registers evidence for an execution and checks
  its integrity.

#### Incremental, recoverable, never overwritten

- **Saved before it happens:** the execution record exists from `created`,
  before any action. `executions step-start` saves a step as *in progress*
  before it is carried out and `step-finish` completes it with what was
  observed, so the file always shows what happened so far. Every write is
  atomic, so a crash leaves the last complete state and never a half-written
  record; leftover temporary files are ignored.
- **Recovery:** `executions interrupted` lists running executions with no recent
  activity (30 minutes by default) and the step that was in progress.
  `executions recover --action resume` closes that step as `interrupted` (its
  outcome was not observed, so none is invented) and keeps the execution
  running so the step can be repeated; `--action abandon` ends it as
  `inconclusive`, keeping the steps that finished. Both record what happened.
- **Never overwritten:** `executions rerun` starts a new execution that points
  back to the original through `rerun_of`; the original stays sealed and intact.
  Corrections and additions to a finalized execution are separate history events
  (`executions correct`, `executions history`) with an author, a time, and a
  justification.
- **Failure classification:** a failed execution (and a failed step) must say
  whether the failure was in the `product`, the `test`, the `infrastructure`, or
  the `evidence_collection`. Defects can only be linked to product failures, so
  environment flakiness and test bugs are not logged as product bugs. Losing the
  evidence is not a pass: without evidence the run is blocked or inconclusive.
- A pass cannot contain a step that did not pass, steps are numbered in order,
  and only the last step may be unfinished.

### Test suites

`qa-workbench suites create | list | show | add | remove | membership | verify`
manages `SUITE` records, stored in `<project>/test-suites/`. A suite has a type
(smoke, sanity, regression, end-to-end, integration, API, functional,
security, compatibility, acceptance, or custom), a status, and a list of test
cases.

- **Many-to-many:** a test case can be in any number of suites and a suite
  holds any number of cases. The workbench writes membership in the suite's
  `cases`; a case may also name its suites in `suites` (handy when editing in
  Obsidian). Effective membership is the union of both sides, so they cannot
  contradict each other.
- **Safe changes:** adding a case that is already a member, adding a case that
  does not exist, or removing one that is not a member is refused with a message.
  Removing a case from a suite never touches the case.
- **Verification:** `suites verify` reports cases that do not exist (an error)
  and cases that are not active yet (information, since a suite under
  construction may hold drafts). `plans verify` now also checks the suites a plan
  references.
- The suite body lists its cases as Obsidian links (`[[TC-001]]`).

### Test plans and selection

`qa-workbench plans create | list | show | recommend | verify` manages `TP`
records. A plan holds the fields of the specification: scope (with in and out
of scope items), objectives, strategy, test levels and types, environments,
profiles, data, dependencies, risks (each with a level and a mitigation), entry
and exit criteria, suites, owners, and an optional schedule. A plan needs
objectives and entry and exit criteria, and plans follow the same review rules
as AI-generated requirements and cases.

- **Selection with rationale:** a plan stores `selection`, a list of
  inclusions and exclusions. Each one must have at least one reason, and each
  reason names a factor (changed requirements, affected features, defect
  history, dependencies, criticality, coverage, time, regression risk, previous
  results, or readiness) and a detail. The selection is plain data in the plan,
  so the user can read and edit it.
- **Recommendation:** `plans recommend` proposes a selection from the changed
  requirements (`--requirement`, repeatable) and an optional time budget
  (`--budget`, in minutes). Only `active` cases are eligible. A case is
  included when it covers a changed requirement, is critical or high priority,
  is the only active case covering a changed requirement, or is a smoke or
  sanity baseline; every other case is excluded with the reason. With a budget,
  the most relevant cases are kept until it is used up, and cases without an
  estimate are included but not counted. The output lists what it could not
  consider (defect history, previous results, and dependencies do not exist as
  data yet) instead of pretending to.
- **Verification:** `plans verify` checks that every selected case exists and
  that included cases are active. Kinds this repository does not store are
  reported as not checked rather than assumed fine.

### Human review of AI-generated records

Requirements and test cases carry an `origin` (`manual`, `imported`, or `ai`).
AI-generated records follow rules enforced as schema checks, so they hold on
create, on update, and when a hand-edited file is read back:

- **Provenance:** an `ai` record names its generator in `generated_by`. Import
  AI-produced requirements with `--generated-by`.
- **Review before approval:** it cannot reach `approved` (requirements) or
  `active` (test cases) without a recorded review that approves it, and the
  reviewer must be a different person from the generator and the author.
  `qa-workbench review submit | decide | pending` runs the workflow
  (`draft` → `in_review` → approved, rejected, or back to `draft` with changes
  requested). Every decision is kept in `reviews` with reviewer, timestamp, and
  comment. Manual records can be approved directly or through the same flow.
- **Facts, hypotheses, and no invented evidence:** `ai_findings` classifies each
  statement as `fact`, `hypothesis`, `recommendation`, or `inconclusive`. A fact
  must cite the id of a real record (a requirement, evidence, and so on);
  free-text "sources" and facts without one are rejected, so an unsupported
  claim has to be marked as a hypothesis.

Known limit: editing an AI record's content after approval does not send it back
to review yet.

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

`qa-workbench tui` opens `WorkbenchApp`, which composes a corporate header,
persistent navigation, main content, a contextual panel, and a footer.
Decisions live in pure modules (`layout`, `navigation`, `status`, `identity`);
widgets only render them, so business rules stay out of presentation code.

- **Identity:** the header and footer carry the Wayne Industries / Dark Knight
  QA identity as text (`tui/identity.py`). No logos or protected symbols are
  used. The secondary header row and the footer identity line are hidden on
  short terminals so the chrome never crowds the work area.
- **Navigation:** three categories, `WORKSPACE`, `OPERATIONS`, and
  `INTELLIGENCE`, with uppercase labels. The selected item is highlighted in
  Wayne Red and the focused area is outlined in Signal Red.
- **Theme:** every color is a named token in `tui/theme.py`; the stylesheet
  never repeats a hex value. Tests check the contrast of text and functional
  colors against the surfaces. The alert color meets the 3:1 minimum for UI
  components and is always paired with a symbol and a name.
- **Status:** `PASSED`, `FAILED`, `WARNING`, `RUNNING`, `BLOCKED`, `SKIPPED`,
  `PENDING`, `AI PROCESSING`, and others, each with a symbol and a name.

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
| `Ctrl+P` | Command palette: go to any page or run an action |
| `Ctrl+K` | Go to the search field of the current page, if it has one |
| `Esc` | Close a dialog, then the menu or context drawer |
| `?` | List the shortcuts |
| `Ctrl+Q` | Quit |

Override any of them in `config.toml`:

```toml
[shortcuts]
toggle_context = "f3"
command_palette = "ctrl+o"
```

An unknown action, an empty key, a key reserved by the terminal (`Ctrl+C`,
`Ctrl+Z`, `Ctrl+S`, `Ctrl+D`), or two actions on the same key makes
`qa-workbench tui` exit with an error that names the problem, instead of
starting with a broken keymap. `Ctrl+B` (browser preview), `Ctrl+N` (new
record), `Ctrl+R` (refresh), and `Ctrl+Enter` (primary action) from the visual
specification are not bound yet because the features behind them do not exist.
`Ctrl+K` focuses the search field of the current page; a cross-module global
search arrives with the knowledge base.

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

### Entry points and distribution

The package declares two console scripts that run the same Typer app:
`batman` (the product command) and `qa-workbench`; `python -m qa_workbench` does
the same. With no command the app opens the TUI, because the terminal interface
is the primary one; every other capability is a subcommand, and `--help` and
`--version` never open the TUI. A broken configuration or an invalid shortcut
keymap stops the launch with an error that names the problem.

Opening the TUI plays a random fullscreen edit from the startup folder before
the workbench appears (`core/splash.py`). The splash runs only when stdout is
an interactive terminal, `splash` is enabled, the folder has a playable file,
and `ffplay`, `mpv`, or `vlc` is available; otherwise it is skipped silently
apart from a debug log. On Windows the console window is minimized for the
duration and restored afterwards, and a playback failure never prevents the
workbench from starting. `--no-splash` skips it for one launch.

Everything the app needs at run time is in `[project].dependencies` (Typer,
Textual, Pydantic, PyYAML), so one install is enough; development tools live in
the `dev` extra. Themes and styles are embedded in the code, so there are no data
files to forget. A clean-environment install of the built wheel was checked: both
commands are created, the CLI works, and the TUI renders. When a dependency that
needs a separate download is added (for example browsers for Playwright), the
install must handle it too, through a guided `batman` step rather than a manual
instruction.

### Configuration

`AppConfig.load()` resolves values in this order, highest priority first:

1. environment variables (`DARK_KNIGHT_CONFIG_DIR`, `DARK_KNIGHT_DATA_DIR`,
   `DARK_KNIGHT_LOG_LEVEL`, `DARK_KNIGHT_LOG_FILE`, `DARK_KNIGHT_SPLASH`,
   `DARK_KNIGHT_EDITS_DIR`, `DARK_KNIGHT_SPLASH_PLAYER`);
2. the `[application]`, `[shortcuts]`, and `[startup]` tables of `config.toml`
   in the configuration directory;
3. platform defaults (`APPDATA`/`LOCALAPPDATA` on Windows,
   `~/Library/Application Support` on macOS, XDG directories elsewhere).

The `[startup]` table accepts `splash` (a boolean), `edits_dir` (the folder
with the videos; defaults to `~/Videos/batman-edits`), and `player` (an
executable name or path; otherwise the first of `mpv`, `ffplay`, `vlc` found on
`PATH`).

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
