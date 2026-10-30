# Requirements

This document converts the product and visual specifications into
traceable requirements. Each requirement has a stable ID, priority,
acceptance criteria, and related implementation phase.

Priority levels are `must`, `should`, and `could`. A requirement is not
considered complete until its acceptance criteria are covered by automated
tests or an explicit, reproducible manual test.

## Functional requirements

| ID | Requirement | Priority | Phase |
|---|---|---|---|
| REQ-001 | The CLI must start the application and expose help/version information. | must | 0 |
| REQ-002 | The application must create, list, open, and archive projects. | must | 1 |
| REQ-003 | A project must store repository, directory, environments, URLs, frameworks, languages, and commands. | must | 1 |
| REQ-004 | The TUI must provide persistent navigation, main content, contextual information, and status bar regions. | must | 1 |
| REQ-005 | The TUI must adapt to wide, medium, narrow, and short terminals without fixed full-screen coordinates. | must | 1 |
| REQ-006 | The system must persist QA records as UTF-8 Markdown with YAML frontmatter. | must | 2 |
| REQ-007 | The system must validate required frontmatter, IDs, statuses, dates, and relative links. | must | 2 |
| REQ-008 | An optional SQLite index must be rebuildable from Markdown and never be the source of truth. | should | 2 |
| REQ-009 | The system must import requirements from Markdown and text while preserving source and author metadata. | must | 3 |
| REQ-010 | Requirements must support status, priority, acceptance criteria, tags, related cases, and coverage. | must | 3 |
| REQ-011 | Test cases must support preconditions, data, steps, expected results, priority, type, profile, environment, and tags. | must | 3 |
| REQ-012 | Test cases must support equivalence partitioning, boundary values, decision tables, state transitions, use cases, and exploratory testing. | should | 3 |
| REQ-013 | AI-generated requirements and test cases must require human review before approval. | must | 3 |
| REQ-014 | Test plans must record scope, strategy, environments, data, risks, entry/exit criteria, suites, owners, and schedule. | must | 4 |
| REQ-015 | A test case must be allowed in multiple reusable suites. | must | 4 |
| REQ-016 | Suite recommendations must explain inclusion and exclusion using changed requirements, risk, history, dependencies, coverage, and time. | should | 4 |
| REQ-017 | The execution engine must support manual, assisted-manual, agent-driven, automated, and exploratory executions. | must | 5 |
| REQ-018 | Execution state transitions must be validated from Created through Finalized. | must | 5 |
| REQ-019 | Execution records must be created before the first action, updated incrementally, recoverable after interruption, and immutable after finalization. | must | 5 |
| REQ-020 | The system must distinguish product, test, infrastructure, and evidence-collection failures. | must | 5 |
| REQ-021 | The Browser Agent must encapsulate Playwright navigation, interaction, assertions, screenshots, video, traces, console, network, and HTTP failures. | must | 6 |
| REQ-022 | Browser preview must support headless, preview, and visible modes and must not block execution. | must | 6 |
| REQ-023 | Hiding and reopening browser preview must preserve execution and show the latest available image. | must | 6 |
| REQ-024 | API testing must support HTTP methods, parameters, payloads, authentication, schemas, contracts, rules, timing, and chained flows. | must | 7 |
| REQ-025 | Requests, responses, headers, credentials, and tokens must be sanitized before persistence. | must | 7 |
| REQ-026 | Integrations must read issues, pipelines, jobs, logs, artifacts, commits, merge/pull requests, and comments through replaceable adapters. | should | 7-9 |
| REQ-027 | Publishing external comments or changes must require explicit human approval and create an audit record. | must | 9 |
| REQ-028 | AI providers must implement a replaceable contract for the built-in agent, Ollama, and OpenCode adapters. | should | 10 |
| REQ-029 | AI output must distinguish facts, hypotheses, recommendations, and inconclusive results and must never invent evidence. | must | 10 |
| REQ-030 | High-risk, destructive, production, intrusive, credential, and out-of-scope actions must require approval. | must | 10-11 |
| REQ-031 | Security testing must be authorized, scoped, rate-limited, sanitized, and auditable. | must | 11 |
| REQ-032 | Reports must link requirements, cases, suites, plans, executions, evidence, defects, and pipelines. | must | 2-12 |

## Non-functional requirements

| ID | Requirement | Priority | Phase |
|---|---|---|---|
| NFR-001 | The application must support Windows, Linux, and macOS where dependencies permit. | must | 0-12 |
| NFR-002 | Python code must use type hints, explicit error handling, and testable dependency injection. | must | 0-12 |
| NFR-003 | Markdown records must use stable immutable IDs and ISO 8601 timestamps with timezone. | must | 2 |
| NFR-004 | Finalized executions must never be silently overwritten; corrections must be separate events. | must | 5 |
| NFR-005 | Secrets, cookies, personal data, private logs, and real evidence must not be committed or emitted in logs. | must | 0-12 |
| NFR-006 | Components must keep business rules out of presentation widgets. | must | 1-12 |
| NFR-007 | The TUI must expose status names and symbols without relying on color alone. | must | 1 |
| NFR-008 | Evidence integrity must be verifiable through hashes, metadata, and source references. | must | 2, 5-6 |
| NFR-009 | The repository must provide CI, tests, linting, formatting, contribution guidance, and security reporting guidance. | must | 0, 12 |
| NFR-010 | External integrations must fail explicitly with diagnostic context and must not return success-shaped fallbacks. | must | 7-11 |

## Traceability rules

Every implementation issue must reference at least one requirement. Every
requirement must reference one or more roadmap phases. A requirement may
only be marked complete when its acceptance criteria and evidence links
are recorded.
