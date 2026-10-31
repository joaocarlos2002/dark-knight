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
  edits/
    service.py     Fetch the startup edits from a GitHub archive
    cli.py         `batman edits ...` commands
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
  bughunt/
    schema.py      BUG schema: classification and the evidence rule
    service.py     record_finding, reclassify
    cli.py         `batman bugs ...` commands
  release/
    analysis.py    Explainable risk, impacted cases, suites, regression
    records.py     REL schema and Markdown rendering
    cli.py         `batman release ...` commands
  sectest/
    authorization.py  Scoped, expiring, audited authorization
    checks.py      Passive checks; confirmed findings vs hypotheses
    runner.py      All-or-nothing run through the action guard
    records.py     SEC schema and rendering
    cli.py         `batman security-tests ...` commands
  publishing/
    schema.py      COMMENT record schema (published is sealed)
    service.py     draft_comment, publish_comment, GitLabComments
    cli.py         `batman comments ...` commands
  security/
    policy.py      Autonomy modes, risk categories, requires_approval
    settings.py    Per-project scope and limits (settings.yaml)
    audit.py       Append-only, hash-chained audit log
    guard.py       ActionGuard, approvals, rate limit, cancellation
    cli.py         `batman security ...` commands
  ai/
    contract.py    Provider contract, messages, tools, CancelToken
    errors.py      ProviderError hierarchy
    agent.py       OwnAgent, SingleShotAgent, evidence rule, approval gate
    selection.py   own / opencode / nvidia / auto (remote engines never auto)
    ollama.py      Ollama adapter
    opencode.py    OpenCode adapter (documented server API)
    nvidia.py      hosted NVIDIA API Catalog adapter (OpenAI-compatible)
    claude_code.py Claude Code CLI adapter (own login, tools disabled)
    guarded.py     JsonHttp behind the action guard and the audit log
    http.py        JSON-over-HTTP port and HTTPX adapter
    cli.py         `batman ai ...` commands
    alfred.py      Alfred: per-project settings, @mentions, ask, format
  integrations/
    ports.py       IssueSource, RepositorySource, PipelineSource
    models.py      Issue, Commit, MergeRequest, Pipeline, Job, states
    errors.py      IntegrationError hierarchy with diagnostic context
    untrusted.py   fence(): external text marked as data
    http.py        HttpGateway port and the HTTPX adapter
    gitlab/        client, issues, repository, pipelines, `gitlab` commands
  api/
    models.py      Definition (steps, auth, expectations) and results
    definition.py  YAML loading with every problem reported together
    transport.py   HttpTransport port and the HTTPX adapter
    runner.py      ApiRunner: requests, checks, timing, chained flows
    sanitize.py    Sanitizer: by name, by value, by shape
    records.py     API record schema; save_flow with a final leak check
    cli.py         `batman api ...` commands
  browser/
    ports.py       BrowserDriver / BrowserSession ports, modes, observations
    agent.py       BrowserAgent: actions, assertions, evidence, preview frames
    playwright_driver.py  The only module that imports Playwright
    chromium.py    Check and guided install of the Chromium download
    preview.py     PreviewChannel (state + frame files), PreviewController
    render.py      Screenshot -> terminal cells (half-blocks, Pillow)
    cli.py         `batman browser ...` and `batman doctor`
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
    data.py        View-models read from records (pure, no widgets)
    browse.py      Rows and detail text for requirements and cases (pure)
    browse_planning.py  The same for suites and test plans
    browse_pipelines.py The same for GitLab pipelines and jobs
    browse_executions.py  The same for executions and their next states
    browse_results.py   The same for defects, API runs, releases, security
    pages/         One Page per navigation key: Overview, Projects,
                   Requirements, Test Cases (BrowserPage is their base)
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
- **Not here yet:** the execution workflow that produces finalized records.

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

### AI providers and the built-in agent

QA code never depends on a specific model. `ai/contract.py` defines one
`Provider` contract (REQ-028): availability check, model listing, `complete`,
`stream`, tool calls, structured output (JSON Schema), cancellation
(`CancelToken`), timeouts, and typed errors (`ProviderUnavailable`,
`ProviderTimeout`, `ProviderRateLimited`, `ProviderResponseError`,
`ProviderCancelled`, `CapabilityNotSupported`). Each provider declares its
`Capabilities`; asking for something it cannot do raises an error instead of
pretending.

- **Engines and selection.** `own` is the built-in agent on a local runtime
  (Ollama), `opencode` is OpenCode, `nvidia` is the hosted NVIDIA API (remote),
  `auto` tries `own` then `opencode` and never a remote engine. A
  specific choice never falls back to another engine; when none is available the
  error lists why for each one. `batman ai status` checks reachability without
  sending anything to a model; `batman ai ask QUESTION -p PROJ-001 --engine auto`
  asks one.
- **Built-in agent (`OwnAgent`).** Loops over `complete` and tool calls (at most
  `max_steps`), with read-only tools over the project's records (`get_record`,
  `list_records`). Tool output and context records are fenced as untrusted data.
  A tool whose risk is not `read` needs the `ApprovalGate`; the default gate
  denies everything. An unknown tool or a failing tool is reported to the model,
  not raised.
- **The evidence rule (REQ-029).** An answer is a list of statements marked
  `fact`, `hypothesis`, `recommendation`, or `inconclusive`. A fact must cite ids
  the agent really saw (given as context or returned by a tool); otherwise it is
  demoted to a hypothesis and flagged, and unseen ids are dropped from `sources`.
  A reply that is not the expected structure, or an agent that never stops
  calling tools, is an explicit error. The AI never decides a result: the command
  prints that its output is analysis and not evidence.
- **Ollama adapter.** Uses the documented REST API (`/api/version`, `/api/tags`,
  `/api/chat` with NDJSON streaming, `format` for structured output, `tools`).
  A stream that ends before its final message is an error, not a partial answer.
  `OLLAMA_HOST` or `--ollama-url` selects the server.
- **NVIDIA adapter and the guard.** `ai/nvidia.py` speaks the OpenAI-compatible
  API of the NVIDIA API Catalog (`GET /models`, `POST /chat/completions`) under a
  configurable base URL (`--nvidia-url`, `NVIDIA_BASE_URL`, default
  `https://integrate.api.nvidia.com/v1`; written against the documentation of
  October 2026). It offers no tool calls or structured output, so it runs behind
  `SingleShotAgent` with the same answer format and evidence rule. Messages go
  through `redact_secrets`; the key comes from `NVIDIA_API_KEY` or the stored
  credentials and never appears in an error (401, 429, 404 for a bad model, other
  statuses and timeouts name the URL and status only). Every engine request goes
  through `ai/guarded.py`: `GuardedJsonHttp` asks the `ActionGuard` before
  sending, so a host outside the allowed hosts is never contacted, the per-host
  rate limit applies, and the audit log gets the action and URL (loopback servers
  are in scope but still audited). `batman ai models` and the Alfred model picker
  list the engine's models.
- **Claude Code adapter.** `ai/claude_code.py` runs `claude -p --output-format
  json` as a child process, so it uses the person's Claude login and needs no key
  (written against Claude Code 2.1, October 2026). The prompt goes through standard
  input; the process is started with `--tools ""`, `--no-session-persistence`,
  `--disable-slash-commands`, and `--strict-mcp-config`, in an empty temporary
  directory, so the model can only answer. `find_claude` looks at
  `CLAUDE_CODE_PATH` / `--claude-path`, then `claude` on the PATH, then the copy
  inside the VS Code extension. The process is behind a `Runner` port (a fake in
  tests) and `GuardedRunner` asks the action guard for `api.anthropic.com` before
  it starts, auditing the start but never the prompt. It is a remote engine like
  `nvidia` (`REMOTE`), runs behind `SingleShotAgent`, and lists the aliases
  `sonnet`, `opus`, `haiku`.
- **OpenCode adapter.** Isolated in `ai/opencode.py`, using only the documented
  `opencode serve` API (`/global/health`, `POST /session`,
  `POST /session/:id/message`, `/session/:id/abort`, `/config/providers`) with
  HTTP basic auth from `OPENCODE_SERVER_PASSWORD`/`OPENCODE_SERVER_USERNAME`; no
  undocumented interface and no Node bridge. Written against the documentation of
  October 2026; the server version is shown, and a reply without the documented
  `{info, parts}` shape is an error. OpenCode runs its own tools, so workbench
  tool calls, structured output, and streaming are reported as unsupported, and
  its engine (`SingleShotAgent`) asks once and applies the same evidence rule.
  Cancelling aborts the session on the server.
- **Not here yet.** Streaming in the TUI, project context selection, per-action
  approvals and autonomy modes (the approval gate is the hook for them),
  external model providers, and a persistent engine setting in `config.toml`
  (today: command options and `OLLAMA_HOST`/`OPENCODE_URL`).
### GitLab integration

`batman gitlab ...` reads from GitLab through replaceable adapters (REQ-026). The
code that uses them depends on the ports in `integrations/ports.py`
(`IssueSource`, `RepositorySource`, `PipelineSource`) and the models in
`integrations/models.py`, so GitHub can be added later without touching it.
Everything here is read-only; writing back is a separate, approved action.

- **GitLab test cases.** The team's test cases are issues of type `test_case` in a
  fixed Portuguese layout (`Objetivo`, `Pré-condições`, `Passos` as a table,
  `Resultado Esperado`, `Critérios/Cobertura`, and `Requisitos relacionados`
  with the wiki link), which is a stable contract (`integrations/gitlab/
  test_cases.py`). `batman gitlab test-cases [LABEL]` and `test-case IID` read
  them; `batman cases push TC-001 --by NAME` (or `G` on the Test Cases page)
  creates or updates one. A push is an outward write, so it asks the guard for
  an approval bound to the exact content (the SHA-256 of the text is part of
  the action, so changing the case needs a new approval, and the requester
  cannot approve their own push) and is audited. An unchanged case is not sent
  again; a case whose title already exists in GitLab is updated, never copied;
  and an update rewrites only the sections that changed (`merge_description`),
  keeping every other character and any section it does not know. The record
  keeps `gitlab_iid`, `gitlab_url`, and `gitlab_sha256`. Labels are the
  requirement codes (from the linked requirements) and `type::testcase`; the
  coverage section lists the business rules (`RN-...`) of those requirements.
  `HttpGateway` gained `put` for updates. Not here yet: pulling GitLab cases
  into local records.
- **Group wiki and requirement import.** The team keeps its requirements in the
  group wiki. `integrations/gitlab/wiki.py` reads it (`GET /groups/:id/wikis`,
  `with_content` only when importing; slugs are passed unencoded and encoded
  there; the group defaults to the project's path without its last segment) and
  finds requirement codes (`GE01.01`, `S02`) and business rules
  (`RN-GE01.01.08`). `integrations/gitlab/connect.py` opens the guarded client
  for the CLI and the TUI alike. `requirements/wiki_import.py` turns one page
  into one `REQ` record with its provenance (slug, URL, SHA-256, read time).
  Importing again skips unchanged pages and updates a changed one in place, back
  to draft so a person reviews the change; the history keeps the earlier text.
  `batman gitlab wiki [QUERY]`, `gitlab wiki-page SLUG`, and `batman
  requirements import-wiki` are the commands; `W` on the Requirements page
  imports in a worker. Wiki text is fenced as untrusted data.
- **Repository reading.** `integrations/gitlab/files.py` (`GitLabFiles`) reads
  branches (newest change first), the tree under a path (folders first), one
  file, and a code search with the matching line. A file over 256 KB, a file
  that is not UTF-8 text, and one with NUL bytes are refused with the reason
  (`FileRefused`), never truncated silently; secrets in file text and in matches
  are masked with `redact_secrets`. A missing path or ref is an explicit 404.
  `batman gitlab branches|tree|file|code` are the commands, `--ref` picks a
  branch, tag, or commit, and `--url` reads another repository of the same
  server. The TUI Repository page (`R` read, `O` open, `U` up, `B` branch) reads
  in a worker and asks the guard first.

| Command | Reads |
|---|---|
| `gitlab issues`, `gitlab issue IID` | open issues by label; one issue with description, labels, and comments |
| `gitlab commits`, `gitlab commit SHA` | commits by ref/date; one commit with the files it changed |
| `gitlab mrs`, `gitlab mr IID` | merge requests; one with the files it changes |
| `gitlab pipelines`, `gitlab pipeline ID` | pipelines by ref/status; one with its jobs, stages, and durations |
| `gitlab log JOB`, `gitlab artifacts JOB`, `gitlab artifact JOB PATH --out F` | the end of a job log, the artifacts a job declares, one artifact file |

- **Connection.** The server and project come from the project's repository URL
  (`https://gitlab.example.com/group/app`) or `--url`. The token is read from
  `GITLAB_TOKEN` (or `--token-env NAME`), or from the value kept with
  `batman config token set gitlab` (the environment wins), and sent in a header;
  it is never put in a URL, printed, or logged, and is masked if an error message
  would contain it. See "Tokens" in the security section.
  Redirects are not followed, so the token is never replayed to another host.
- **Scope (REQ-030).** `GuardedGateway` asks the action guard before every
  request: the GitLab host must be one the project allows (a local server is
  always in scope), the per-host rate limit applies, cancellation stops the read,
  and each request is audited. A host that is not allowed never receives the
  token; the command says so and how to allow it
  (`batman security set --allow-host`). This also covers `--url`.
- **Failures are explicit (NFR-010).** No token or project, rejected token (401),
  missing permission (403), not found (404), rate limit (429, with the retry
  delay), server error, unreachable server, a non-JSON answer, and a malformed
  item each raise a different `IntegrationError` with the endpoint, the HTTP
  status, and what to do. An empty project is an empty list, never confused with
  a failure. There are no silent retries.
- **Pipeline states.** GitLab statuses map to the specification's states
  (created, pending, running, success, failed, canceled, skipped, manual,
  blocked); an unrecognized status becomes `unknown` and keeps the raw value.
  `Pipeline.passed` is true only for `success`; a created or accepted pipeline is
  neither finished nor passed, and an HTTP 2xx never means the tests passed.
- **External text is data.** Issue text, comments, commit titles, merge request
  titles, and job logs are printed inside `fence(...)`, which labels them as
  untrusted and neutralizes fence markers inside the text, so an AI provider that
  later reads them cannot mistake them for instructions. Job logs also pass
  through `redact_secrets` and have terminal codes removed; only the end is shown.
- **Artifacts.** Paths must be relative and stay inside the archive; downloads
  have a size limit.
- **Not here yet.** Pipeline triggering, `.gitlab-ci.yml` analysis, failure
  classification, and posting comments (REQ-027 needs approval and an audit trail).
### API tests and sanitization

`batman api run FILE.yaml -p PROJ-001` runs an API test definition and saves a
sanitized `API` record (REQ-024, REQ-025). `api list` and `api show` read them
back. A definition has a `base_url` and ordered `steps`:

```yaml
name: Users API
base_url: https://staging.example.test
steps:
  - name: login
    method: POST
    url: /login
    json: {user: ada}
    expect: {status: 200, max_ms: 800}
    extract:
      sid: {path: $.session, secret: true}
  - name: profile
    url: /users/{id}
    path_params: {id: "7"}
    headers: {X-Session: "{{sid}}"}
    auth: {type: bearer, env: API_TOKEN}
    expect:
      status: 200
      json_schema: {type: object, required: [name]}
      json_equals: {"$.name": ada}
```

- **Coverage of REQ-024.** All HTTP methods, query and path parameters, JSON or
  text payloads, authentication (`bearer`, `basic`, `header`), expected status,
  response-time limit, header checks, body text, JSON Schema (Draft 2020-12),
  value checks by `$.a.b[0]` path, and chained flows (`extract` carries values to
  later steps as `{{name}}`). Authorization tests are steps that expect 401/403.
- **Credentials are never in the file.** Authentication names an environment
  variable; a definition that holds a literal credential is refused. A missing
  variable is an explicit error and nothing is sent.
- **Results.** A step is `passed`, `failed` (the API answered, but not as
  expected; every failed rule is listed), `error` (it could not run: bad
  definition, missing credential, no connection, timeout), or `skipped` (an
  earlier step stopped the flow, unless `stop_on_failure: false`). Redirects are
  reported, not followed.
- **Sanitization (REQ-025).** `Sanitizer` works by name (sensitive headers, query
  parameters, JSON keys), by value (every credential the run used and every
  value extracted with `secret: true` is removed wherever it appears, even if a
  server echoes it back), and by shape (bearer/basic tokens, JWTs, cloud and Git
  tokens, private keys, `password=...`). E-mail addresses and CPF numbers are
  masked. Bodies are truncated. The step's exchange is built *after* extraction,
  so a secret captured from a response is already known when that response is
  written down.
- **Defense in depth.** `save_flow` scans the final Markdown with the same
  secret detector the record schemas use and refuses to write (nothing is saved)
  if anything still looks like a credential. Saved results are sealed like a
  finalized execution.
- **HTTP port.** `HttpTransport` is replaceable; `HttpxTransport` is the real
  adapter and tests use scripted fakes or `httpx.MockTransport`, never the
  network.
- **Scope and approvals (REQ-030).** `batman api run` sends every request through
  `GuardedTransport`, which asks the action guard first: the host must be one the
  project allows (a local server is always in scope), the per-host rate limit
  applies, cancellation stops the run, and each request is written to the audit
  log with its URL sanitized. By method, reading is a read; `POST`/`PUT`/`PATCH`
  are routine work on a test target (they ask first only in `assisted` mode); and
  `DELETE` is a data change that always needs approval. A request that is not
  allowed is never sent: the step ends as an error saying why, with the approval
  request id, and the flow stops. Approving it (`batman security approve`) and
  running again lets exactly that request through, once.
- **Not here yet.** Registering endpoints for reuse and OpenAPI import.

### Approvals, autonomy modes, and security controls

`security/` implements REQ-030 (and NFR-005, NFR-010). Risky actions go through
`ActionGuard.authorize` before they happen; the answer is "allowed by policy",
"allowed by a person's approval", or an exception that says why not.

- **Modes.** `assisted` (default and safest), `semi_autonomous`, and
  `controlled_autonomous`. Nine categories are *sensitive* and need approval in
  every mode, with no setting to turn that off: data change, production write,
  external comment, intrusive test, code change, configuration change,
  destructive command, credential request, and anything out of scope. Modes only
  change routine work on the workbench's own records: `assisted` asks first,
  the other two do not.
- **Scope.** `<project>/security/settings.yaml` holds the mode, authorized
  environments, allowed hosts, requests per minute, timeout, retries, and data
  policy. A host is allowed when it matches exactly or by a `.suffix`; wildcards,
  paths, and ports are rejected. With no hosts configured, every external host is
  out of scope. An unknown key, a bad mode, or an invalid limit makes loading
  fail instead of falling back to defaults. A missing file means the safe
  defaults.
- **Approvals.** A sensitive action creates a request (`APR-xxxxxxxx`) and
  raises `ApprovalRequired`. A person runs `batman security approve ID --by NAME`
  (or `deny ... --reason`). An approval is bound to the exact action (a hash of
  action, category, detail, and target), is single-use, and expires after an hour;
  the requester cannot decide their own request, a denial needs a reason, and a
  request cannot be decided twice. A denial blocks the same action until it
  expires.
- **Audit log.** `<project>/security/audit.jsonl` is append-only and
  hash-chained: editing, reordering, or removing a line is found by
  `batman security audit --verify`, and a damaged log is never extended.
  Approval state is derived from this log, so there is one source of truth.
  Text is passed through `redact_secrets` before it is written.
- **Limits and cancellation.** A per-host rolling-minute rate limit raises
  `RateLimitExceeded` with a retry time instead of waiting silently.
  `cancel()` is recorded and refuses every later action.
- **Tokens.** `security/credentials.py` keeps API tokens in `credentials.json` in
  the configuration directory, keyed by the name of the environment variable that
  would carry them. `StoredEnvironment` is the process environment with the store
  behind it, so every integration that reads its token from the environment
  (GitLab, API tests) finds a stored one unchanged, and the environment wins. The
  file is written atomically and owner-only where supported; a damaged file is an
  explicit error, never an empty store. Not stored in a project, so exporting or
  sharing one never carries a token. The OS keyring is not used: it would add a
  dependency and behave differently on each platform, and a file in the user's
  configuration folder is the same on all three. `token_report` says, for each
  service, whether a token is set and where it comes from (never the value); the
  CLI `show`, `batman doctor`, and the Settings page all use it.
- **Who calls it.** Browser navigation, API tests, GitLab reads, security checks,
  release analysis, and comment publishing (REQ-027) ask the guard before they
  send anything. Not wired yet: the AI engines (`ApprovalGate` in the AI agent is
  the matching hook). Process isolation is not implemented.

### Bug hunting, release analysis, and security checks

Three modules (REQ-031, REQ-032) that turn observations into records without
claiming more than the evidence supports.

**Bug hunting** (`batman bugs record|reclassify|list|show`). A `BUG` record's
status is its classification: `reproduced`, `suspected` (the default),
`false_positive`, `environment_unavailable`, or `inconclusive`. A defect can only
be `reproduced` with steps, expected and observed results, at least one evidence
record that passes its integrity check, and at least two reproductions; asking
for it without those is an error that lists what is missing, never a quiet
downgrade. The same rule runs when a record is read back, so a hand edit cannot
promote a suspicion. A false positive needs its reason and an environment problem
its description. Reclassifying keeps who, when, and why. Literal credentials are
refused. Execution reports now say whether a referenced `BUG-NNN` exists.

**Release analysis** (`batman release analyze|list|show`). It reads real commits
and merged merge requests (with their changed files) through the GitLab adapter,
after the action guard authorizes reading that host, and saves a sealed `REL`
record. The rules are explainable, not a model's opinion: areas are the first two
path segments; risk rises with sensitive names (auth, payment, migration, ...),
files changed in three or more commits, source changed with no related test
change in the release, and very wide commits. Impacted cases are test cases whose
title, objective, or tags share a word with a changed path, and the matched words
are listed. Suites are recommended when they hold impacted cases (smoke suites
always; regression suites when an area is high risk). Every claim names the
commits and files behind it. The record states its limits: a word match is not
proof of impact and code was not analyzed.

**Security checks** (`batman security-tests authorize|revoke|status|run|list|show`).
Passive, non-destructive checks only: security headers, version and technology
disclosure, cookie flags, CORS, HTTP-to-HTTPS redirect, and access to
declared-protected paths without credentials. Each is a GET, never a payload.

- *Authorized and scoped.* A person grants a file naming who authorizes, why, the
  exact hosts, the allowed checks, and an expiry of at most 30 days; granting and
  revoking are audited. A check also needs its host in the project's allowed hosts
  (two independent gates). A run verifies all of that for every requested check
  before sending the first request.
- *Rate-limited and auditable.* Every request goes through the action guard
  (limits, cancellation), and each check start and end is in the audit log.
- *Confirmed versus hypothesis.* A finding is confirmed only when directly
  observed in a response; inferred ones are hypotheses and say what would settle
  them. An unreachable target is an `error` check and the run is saved as
  `incomplete`.
- *Sanitized and honest.* URLs and text go through the API sanitizer, cookie
  values are never recorded, and the saved result carries the statement that this
  is not a penetration test, not an OWASP or ISTQB certification, and that finding
  nothing does not show a target is secure. OWASP references are pointers only.
- *Not here yet.* Intrusive testing (fuzzing, injection, brute force), which would
  need the `intrusive_test` approval; authenticated sessions; and BugTraceAI.
### Publishing issue comments

`batman comments draft|publish|list|show` (REQ-027, spec 5.17). A comment is a
`COMMENT` record that keeps what was sent, its author, provider, issue URL, state,
the server's answer (external id and URL), and the time it was published. It is
the only external write the workbench makes today, and it only posts a note: it
never closes an issue or changes labels, assignees, or state.

- **Drafting sends nothing.** `draft` canonicalizes the text (LF, one final
  newline), hashes it, and refuses, with every problem listed at once: an empty
  or oversized text, a literal credential, a link to a host that is not the issue's
  or an authorized one (so links are real), no evidence, evidence that is missing
  or fails its integrity check, or no author.
- **Publishing goes through the action guard.** The action is an external
  comment, always sensitive. Its fingerprint includes the text's SHA-256, so an
  approval covers exactly that text; editing the record afterwards is detected
  (the hash no longer matches) and approving one comment never covers another.
  Without approval the record becomes `awaiting_approval`, a request is created,
  and nothing is sent. The author cannot approve their own comment (the guard
  rejects a decider equal to the requester).
- **States, never a false success.** `published` (sealed; never re-sent),
  `failed` (the server refused or errored; the error is kept), and
  `outcome_unknown` (the connection broke after the request left, so the comment
  may exist). From `outcome_unknown` a new attempt needs `--checked-issue`, which
  states that the issue was checked, plus a fresh approval, because an approval is
  single-use.
- **Audit.** Request, decision, use of the approval, and the final
  `comment_published` or `comment_failed` are entries of the hash-chained audit
  log from the security controls.
- **GitLab.** `GitLabComments` posts `POST /projects/:id/issues/:iid/notes`
  through the same client and explicit errors as the readers. The token needs the
  `api` scope (read-only tokens are rejected with a 403 that says so); it comes
  from `GITLAB_TOKEN` and is never stored.
- **Not here yet.** Other providers (the `CommentWriter` port is ready for
  them), editing or deleting published comments, comments on merge requests, and
  an automatic comment from a report.

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

`qa-workbench tui` opens `WorkbenchApp`, which composes a one-line header,
persistent navigation, main content, a shortcut line, and a footer; a context
panel opens on demand.
Decisions live in pure modules (`layout`, `navigation`, `status`, `identity`);
widgets only render them, so business rules stay out of presentation code.

- **Chrome:** the header is one line, the product name on the left and the open
  project on the right (`tui/identity.py` holds only the product name). The
  footer is one line with the project and the global shortcuts, and the line
  above it shows the shortcuts of the current page. Nothing repeats between
  them, and there is no corporate branding or tagline in the interface.
- **Navigation:** four groups, `WORKSPACE`, `OPERATIONS`, `INTELLIGENCE`, and
  `SYSTEM`, with uppercase labels and a blank line between groups. The selected item is highlighted in
  Wayne Red and the focused area is outlined in Signal Red.
- **Theme:** every color is a named token in `tui/theme.py`; the stylesheet
  never repeats a hex value. Tests check the contrast of text and functional
  colors against the surfaces. The alert color meets the 3:1 minimum for UI
  components and is always paired with a symbol and a name.
- **Status:** `PASSED`, `FAILED`, `WARNING`, `RUNNING`, `BLOCKED`, `SKIPPED`,
  `PENDING`, `AI PROCESSING`, and others, each with a symbol and a name.

| Terminal | Navigation | Content | Context |
|---|---|---|---|
| Wide (100+ columns) | sidebar | center | on demand, `F2` |
| Medium (80-99) | sidebar | center | drawer, `F2` |
| Narrow (under 80) | menu, `F1` | single column | drawer, `F2` |
| Short (under 24 rows) | unchanged | tighter spacing | unchanged |

The shell reacts to resize events and never uses fixed coordinates. It is
fully keyboard-driven. Every status is shown as a symbol and a name (for
example `✓ PASSED`), never by color alone. Modules that are not implemented
yet say so explicitly instead of showing placeholder data.

### TUI pages

The workbench shell hosts real pages. `tui/pages/` has one class per navigation
key (`PAGES`); every page is a `Page` built from a `PageContext` (the data
folder and the open project) and redrawn by `refresh_data()`, which reads the
project's records from disk. `Ctrl+R` reloads the visible page, so changes made
by the CLI in another terminal show up. Pages without a class still show
"This module is not available yet" instead of placeholder data.

- **Data stays out of widgets.** `tui/data.py` turns records into plain
  view-models (`build_overview`, `project_rows`) and is tested without Textual.
  Every number comes from persisted records; a damaged record is counted and
  listed on the page, never dropped, and a value that cannot be computed is
  `n/a`, never zero.
- **Projects.** Lists active and archived projects (a damaged project is shown
  as a problem line, not hidden). `Enter` opens the selected project and shows
  its overview, `N` opens a form to create one (name, repository, environment and
  URL; the dialog validates before anything is written and stays open on an
  error), `X` archives the selected one after a confirmation. Opening a project
  updates the header, the status line, and the context panel.
- **Overview.** Project identification, the test case count, executions by
  result (passed, failed, blocked) and in progress, and the most recent
  executions with case title, result, and duration. With no project open it says
  so and points to Projects. Pipelines show an empty state because pipeline
  records are not stored yet.
- **Startup.** With exactly one active project `batman` opens on it; with
  several, or none, the user chooses from Projects.
- **Reusable.** `FormDialog` collects labelled fields, marks required ones, and
  keeps the dialog open with the error shown inline.
- **List + detail pages.** `BrowserPage` is the base for pages that browse
  records: a search box (`Ctrl+K` goes to the search of the *visible* page; every
  word must match the id, title, status, priority, or tags), a status filter
  cycled with `F`, a table, and the selected record's detail below it, which follows
  the cursor. Damaged records are counted under the list instead of being hidden.
  `tui/browse.py` builds the rows and detail text without widgets.
- **Requirements.** Columns ID, priority, status, cases, title; the cases column
  says `N case(s)` or `NOT COVERED`, from the same coverage rule as
  `batman requirements coverage` (there is no coverage percentage because
  criteria are not tracked per case). Detail shows source, author, tags,
  acceptance criteria, related cases by title, cases that are named but missing,
  reviews, and the description. `I` imports a `.md` or `.txt` file through a form
  and reports how many were imported, skipped, and rejected.
- **Test cases.** Columns ID, priority, status, type, title; detail shows the
  objective, requirements, suites, tags, preconditions, numbered steps with what
  to observe, and the expected result. `N` opens a form (steps are written as
  `action => expected` separated by `;`); the form refuses an unknown priority,
  no steps, or a requirement id that does not exist, and stays open with what was
  typed until the case can be saved as a draft.
- **Knowledge Base.** Full-text search over every record kind through
  `RecordIndex` (SQLite FTS5), a disposable cache of the Markdown files: Enter
  searches (every word as a prefix, ignoring case and accents), `F` narrows to one
  record kind, and the detail shows the match snippet and the whole record. With
  no index the page says so and `B` builds it; opening or reloading the page
  syncs only the files that changed. A damaged index is reported as "Search is
  unavailable" with the reason, never as an empty result, and damaged records are
  counted as not indexed.
- **Test suites.** Columns ID, type, status, case count, title. The detail
  lists the member cases with title and status, the total, the summed estimate
  (said to be partial when only some cases have one), the latest execution that
  ran the suite or one of its cases, and a warning for members that no longer
  exist. `N` creates a draft suite (the type and every case id are checked inside
  the form), `A` adds cases to the selected suite and `R` removes them; adding a
  case that is already there, or one that does not exist, keeps the form open
  with the reason.
- **AI Agent (Alfred).** A chat with the project's assistant. `AgentChat` is a
  reusable transcript plus message box in which every speaker is named (YOU,
  ALFRED, NOTICE), never only colored. A question runs in a worker thread, so the
  TUI keeps responding and the box is disabled until the answer arrives. The
  reply is the typed answer of the built-in agent: each statement is tagged FACT,
  HYPOTHESIS, RECOMMENDATION, or INCONCLUSIVE, with its sources, and a "fact"
  that cites a record the agent never saw is shown as a hypothesis. Writing
  `@REQ-001` in the question attaches that record (fenced as untrusted data);
  unknown ids are reported as not attached. When no engine is available the chat
  shows a notice with the reason for each engine, not an invented answer. Alfred
  only has read-only record tools.
- **Review.** The Review page lists the AI-generated records waiting for a
  person (drafts and records in review, from `ReviewService.pending`) with what
  the AI said: each finding as a fact, hypothesis, recommendation, or
  inconclusive, and the source it cites or `[no source]`. `S` submits a draft,
  and `A`, `X`, and `C` approve, reject, or ask for changes through a dialog
  with the reviewer's name (defaulting to the current user) and a comment that
  is required for a rejection or a change request. The decision goes through
  the same service and schema checks as `batman review`, so a record cannot be
  approved by its author or generator: the dialog shows the reason and keeps
  what was typed. The Overview shows how many records wait.
- **Alfred's settings** (`Ctrl+O`, saved per project in `ai/alfred.yaml`): engine
  (`own`, `opencode`, `nvidia`, `auto`), model, style (`balanced`, `concise`,
  `detailed`), answer language, and the Ollama, OpenCode, and NVIDIA URLs. They
  are picked, not typed: `Ctrl+O` opens a menu and each entry opens a list (the
  language list is `LANGUAGES` in `ai/alfred.py`); only the server addresses are a
  form. `Ctrl+G` lists the engine's models in a `ChoiceDialog` and saves the choice
  (the menu's Model entry does the same); without a model the notice says to press
  `Ctrl+G`. An
  answer from a remote engine is labelled as such. Style and language are added
  to the system prompt *after* the fixed rules and state that they never override
  them. A broken settings file is an error, not a silent return to defaults, and
  an archived project's settings cannot be changed. `Ctrl+L` clears the chat.
- **Test plans.** Columns ID, status, suites, selected cases, title. The detail
  shows scope, strategy, objectives, entry and exit criteria, the selected suites
  with their size, the selection (how many cases are included and excluded, the
  estimate, and the recorded reason for each inclusion), and risks. A plan with no
  selection says so and points to `batman plans recommend`. `N` creates a draft
  plan from a form that checks the suites exist.
- **Pipelines.** The recent CI pipelines of the project's GitLab repository.
  Nothing is fetched until the user presses `R`: the read goes through the action
  guard (the GitLab host must be in the project's allowed hosts, otherwise the page
  shows the pending approval request instead of reading), runs in a worker thread,
  and keeps the result only in memory, because a pipeline is the server's current
  word and not a record of the project. Selecting a pipeline loads its jobs in the
  background and shows them by stage, with each job's failure reason, jobs that
  are allowed to fail marked as such, and the failed jobs named with a pointer to
  `batman gitlab log`. States use the specification's names (an unknown GitLab
  status is shown as the server's own word), a reported success is labelled as the
  server's word and not a test result, and an unfinished pipeline says nothing can
  be concluded. A missing token, a rejected token, an unreachable server, or a
  project without a repository URL are shown as errors with their reason, never as
  an empty list.
- **Executions.** Newest first, with the state shown as a symbol *and* its name
  (created, planned, awaiting approval, running, passed, failed, blocked, ...). The
  detail shows the case, type, executor, environment, version, plan, suite, and
  duration; the steps with their marks (`[x]` passed, `[!]` failed, `[-]` blocked,
  `[~]` skipped, `[>]` in progress) and what was observed; the observed result and
  failure type; evidence and defects; and the states it can move to next. `N`
  starts an execution from a test case (the case must exist and be active, except
  for exploratory runs), `M` moves the selected one to its next state: the form
  offers only the states the lifecycle allows, and the same checks as the CLI run
  (a passed execution needs steps and evidence, a failure needs a failure type, an
  approval-gated one needs an approver). A refusal keeps the form open with the
  reason. A finalized execution says it is final, and steps are still recorded
  with `batman executions` so each one is saved before and after it runs.
- **Result pages.** Bug Hunting (`BUG`), API Testing (`API`), and Release
  Analysis (`REL`) are list + detail pages over records the CLI saved: a header
  from the metadata followed by the readable Markdown body written when the record
  was saved (API requests and responses are the sanitized copies; a defect also
  shows its classification history). They are read-only: results are created by
  the commands that produce evidence.
- **Security.** One list of approval requests (`APR-...`) and security-check runs
  (`SEC-...`) with the audit log's health in the summary line (`Audit log intact:
  N entries`, or the damage if the hash chain is broken, in which case the
  approvals are not listed rather than trusted). `A` approves and `D` denies the
  selected pending request through a form that asks for the person's name (and a
  reason for a denial); the same rules as `batman security approve|deny` apply,
  so the requester cannot decide their own request and a decided request cannot
  be decided again.
- **Reports.** Two sections: Saved Reports and Evidence Records. Saved Reports
  lists generated reports (execution, traceability) with their source execution
  and stale status. Evidence Records lists all `EVD` records with their verification
  status (intact/tampered). Selecting an evidence record opens the `EvidenceViewer`
  showing file, size, SHA-256, source, description, verification result with any
  problems, and for text/JSON files the first 50 lines; images are rendered via
  half-block characters. `G` regenerates the execution report for the selected
  saved report.
- **Settings.** Five categories: General (global config), Shortcuts (keyboard
  overrides), Security (per-project autonomy mode, allowed hosts, rate limits),
  Browser (default mode and capture settings), and API tokens (which tokens are
  set and from where; Save Changes sets one and Reset removes a stored one, with
  the token typed hidden and never shown again). Security changes open a validated
  form dialog and write an audit log entry on save. No secrets are stored in
  settings files; only environment variable names are used.
- **Read-only when archived.** On an archived project the lists work and `N`/`I`
  explain that it cannot be changed.
- **Not here yet.** Executions and the integration pages are still
  placeholders. There is no edit or delete from the TUI yet, and the plan
  selection (recommendation) and review decisions are still done with the CLI.

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
| `Ctrl+B` | Show or hide the browser preview |
| `F5` | Ask the running browser for its next mode |
| `F6` | Pause or resume the running browser |
| `Ctrl+R` | Reload the current page from disk |
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
starting with a broken keymap. `Ctrl+N` (new
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

`BrowserPreview` exists (see the Browser Agent). Not built yet because its
subsystem does not exist: `AgentChat`. `EvidenceViewer` displays evidence records
with integrity verification and content preview.

### Browser Agent and Browser Preview

`BrowserAgent` (REQ-021) wraps a `BrowserDriver` port. `PlaywrightDriver` is the
only code that imports Playwright; tests use a fake driver, so no test starts a
browser or touches the network. The agent offers `navigate`, `click`, `fill`,
`expect_text`, `expect_visible`, and `screenshot`, and records every action
(label, outcome, duration). It keeps what the browser reports: console messages,
page errors, and every request with its status. Headers and bodies are never
stored, URLs hide the value of query parameters that look like credentials, and
the values typed into fields are never written to the action log.

- **Three kinds of problem stay apart.** A browser fault is a `BrowserError`
  (with action, selector, and URL; `BrowserTimeout` for timeouts). A page that
  does not match the test is an `AssertionFailed`, a finding that is *not* a
  `BrowserError`. A missing Chromium is a `BrowserSetupError`. A failed
  screenshot is recorded in `screenshot_failures` and never fails the test.
- **Evidence.** `close()` returns the screenshots, the Playwright trace, the video,
  and two JSON logs, `console.json` (console messages and page errors) and
  `network.json` (every request with method, URL, status, and a `failed` flag for
  4xx/5xx, requests that never completed, and requests blocked by the host
  restriction). The logs are sanitized before they are written (a page can print
  a token; URL credentials and sensitive query values are removed) and never hold
  headers or bodies. `register_artifacts` registers all of it as hashed,
  immutable `EVD` records with source `playwright`.
- **Preview (REQ-022, REQ-023).** The mode is `headless`, `preview` (default),
  or `visible`. In `preview` the agent saves a screenshot after an action at most
  once per `refresh_seconds`. Agent and TUI share a folder
  (`<data>/browser-preview/`): `frame.png` and `state.json` are replaced
  atomically, so `batman browser run` in one terminal is followed by the
  workbench in another. The TUI panel reads that folder on a timer, so drawing
  never blocks it, and hiding it (`Ctrl+B`) only stops reading: the run and the
  evidence collection continue, and showing it again draws the latest frame. The
  image is drawn with half-block characters; the TUI does not render web pages.
- **Controls.** `F5` (or `batman browser control --mode ...`) and `F6`
  (`--pause`/`--resume`) write `control.json`, which the agent reads between
  actions. `headless` and `preview` switch immediately; switching to or from
  `visible` needs a browser restart, so while a run is active it is only
  recorded and applies to the next run, and the panel says so.
- **Installation.** Playwright and Pillow are runtime dependencies. Chromium is a
  separate download, handled by `BrowserSetup`: `batman doctor` reports it,
  `batman doctor --fix` (or the first `batman browser run`) explains the ~150 MB
  download and installs it after confirmation (`--yes` skips the question). With
  no terminal to ask, or an answer of no, the command stops with the exact
  command to run later. A download that fails, or an installer that succeeds
  without leaving a usable browser, is an explicit error.
- **Authorized navigation.** With `-p PROJ`, `batman browser run` builds the
  project's action guard; without a project only loopback addresses and local
  files open, so nothing external is reached by accident. Each `navigate` is
  audited and rate-limited by the guard, and a host outside the project's allowed
  hosts is refused before any request (no approval path for the browser). Three
  layers enforce it: the agent's check, a request filter that aborts and records
  blocked subresources (`blocked: host not authorized`), and Chromium's
  `--host-resolver-rules`, which makes every other host unresolvable at the
  network layer, so a redirect to an unauthorized host fails too (Playwright's
  request filter does not see redirects). If a page still ends on an unauthorized
  URL the run stops.
- **Not here yet.** Scripted flows from test cases, authenticated profiles, and
  approval of destructive in-page actions (clicks and form submissions are not
  gated yet).
  Sensitive data inside traces and videos is not scrubbed.

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

The videos are not kept in this repository. When `[startup] repo` names a
GitHub repository, `batman edits fetch` downloads its zip archive
(`codeload.github.com/<owner>/<name>/zip/<ref>`, default branch when no `ref` is
set), verifies the optional SHA-256, and copies the video files into
`edits_dir` (`edits/service.py`). The first interactive launch does the same
when the folder is empty. A private repository is read with
`DARK_KNIGHT_EDITS_TOKEN`, falling back to `GITHUB_TOKEN`; a failed download,
checksum, or archive with no videos is reported and the splash is simply
skipped, never blocking the workbench. `batman edits list` shows what the
splash can choose from.

Everything the app needs at run time is in `[project].dependencies` (Typer,
Textual, Pydantic, PyYAML, Playwright, Pillow), so one install is enough; development tools live in
the `dev` extra. Themes and styles are embedded in the code, so there are no data
files to forget. A clean-environment install of the built wheel is checked: both
commands are created, the CLI works, and the TUI renders. A dependency that needs
a separate download is handled by a guided `batman` step rather than a manual
instruction: Chromium for Playwright is checked and installed by `batman doctor`.

### Configuration

`AppConfig.load()` resolves values in this order, highest priority first:

1. environment variables (`DARK_KNIGHT_CONFIG_DIR`, `DARK_KNIGHT_DATA_DIR`,
   `DARK_KNIGHT_LOG_LEVEL`, `DARK_KNIGHT_LOG_FILE`, `DARK_KNIGHT_SPLASH`,
   `DARK_KNIGHT_EDITS_DIR`, `DARK_KNIGHT_SPLASH_PLAYER`,
   `DARK_KNIGHT_EDITS_REPO`, `DARK_KNIGHT_EDITS_REF`,
   `DARK_KNIGHT_EDITS_SHA256`);
2. the `[application]`, `[shortcuts]`, and `[startup]` tables of `config.toml`
   in the configuration directory;
3. platform defaults (`APPDATA`/`LOCALAPPDATA` on Windows,
   `~/Library/Application Support` on macOS, XDG directories elsewhere).

The `[startup]` table accepts `splash` (a boolean), `edits_dir` (the folder
with the videos; defaults to `assets/batman-edits` in the project), `player`
(an executable name or path; otherwise the first of `mpv`, `ffplay`, `vlc` found
on `PATH`), and the edits source: `repo` (`owner/name` of the GitHub repository
with the videos), `ref` (tag, branch, or commit; the default branch when
absent), and `sha256` (optional checksum of the downloaded archive, normalized
to lowercase).

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
| Evidence Vault | Screenshots, logs, network data, hashes, sources |

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
