# GitHub issue catalog

This catalog is the source for creating the repository issues. All issues
must use one of the labels below and include requirement IDs, phase, scope,
acceptance criteria, and dependencies.

## Labels

- `phase:0-foundation`
- `phase:1-tui-projects`
- `phase:2-markdown-storage`
- `phase:3-requirements-cases`
- `phase:4-planning-suites`
- `phase:5-execution`
- `phase:6-browser`
- `phase:7-issue-api`
- `phase:8-pipelines`
- `phase:9-issue-management`
- `phase:10-ai`
- `phase:11-analysis-security`
- `phase:12-stabilization`
- `type:requirement`
- `type:feature`
- `type:architecture`
- `type:documentation`
- `type:testing`
- `priority:must`
- `priority:should`
- `priority:could`
- `good first issue`
- `blocked`

## Issue creation set

### Foundation and repository

1. **Create installable Python project foundation** — `REQ-001`, `NFR-002`,
   `NFR-009`; labels `phase:0-foundation`, `type:architecture`,
   `priority:must`.
2. **Add cross-platform configuration and logging** — `NFR-001`, `NFR-005`,
   `NFR-010`; labels `phase:0-foundation`, `type:feature`, `priority:must`.
3. **Add CI, tests, lint, formatting, and security policy** — `NFR-009`;
   labels `phase:0-foundation`, `type:testing`, `priority:must`.
4. **Document project architecture and contribution workflow** — `NFR-009`;
   labels `phase:0-foundation`, `type:documentation`, `priority:must`.

### TUI and projects

5. **Implement responsive Textual application shell** — `REQ-004`, `REQ-005`,
   `NFR-006`, `NFR-007`; labels `phase:1-tui-projects`, `type:feature`,
   `priority:must`.
6. **Implement project lifecycle and project.yaml** — `REQ-002`, `REQ-003`;
   labels `phase:1-tui-projects`, `type:feature`, `priority:must`.
7. **Implement reusable visual components and keyboard shortcuts** —
   `REQ-004`, `REQ-005`, `NFR-007`; labels `phase:1-tui-projects`,
   `type:feature`, `priority:must`.

### Markdown storage

8. **Implement Markdown frontmatter repository** — `REQ-006`, `REQ-007`,
   `NFR-003`; labels `phase:2-markdown-storage`, `type:feature`,
   `priority:must`.
9. **Implement rebuildable index and search** — `REQ-008`, `REQ-032`;
   labels `phase:2-markdown-storage`, `type:feature`, `priority:should`.
10. **Implement immutable history and evidence integrity** — `NFR-004`,
    `NFR-008`; labels `phase:2-markdown-storage`, `type:architecture`,
    `priority:must`.

### Requirements and cases

11. **Implement requirement import and validation** — `REQ-009`, `REQ-010`;
    labels `phase:3-requirements-cases`, `type:feature`, `priority:must`.
12. **Implement test case models and design techniques** — `REQ-011`,
    `REQ-012`; labels `phase:3-requirements-cases`, `type:feature`,
    `priority:must`.
13. **Add human review workflow for AI-generated artifacts** — `REQ-013`,
    `REQ-029`; labels `phase:3-requirements-cases`, `type:feature`,
    `priority:must`.

### Planning and suites

14. **Implement test plans and selection rationale** — `REQ-014`,
    `REQ-016`; labels `phase:4-planning-suites`, `type:feature`,
    `priority:must`.
15. **Implement reusable suites and many-to-many case membership** —
    `REQ-015`; labels `phase:4-planning-suites`, `type:feature`,
    `priority:must`.

### Execution

16. **Implement execution state machine and execution types** — `REQ-017`,
    `REQ-018`; labels `phase:5-execution`, `type:feature`, `priority:must`.
17. **Implement incremental, recoverable, immutable execution records** —
    `REQ-019`, `REQ-020`, `NFR-004`; labels `phase:5-execution`,
    `type:feature`, `priority:must`.
18. **Implement execution reports and traceability links** — `REQ-032`;
    labels `phase:5-execution`, `type:feature`, `priority:must`.

### Browser and APIs

19. **Implement Playwright Browser Agent** — `REQ-021`; labels
    `phase:6-browser`, `type:feature`, `priority:must`.
20. **Implement non-blocking Browser Preview modes and controls** —
    `REQ-022`, `REQ-023`; labels `phase:6-browser`, `type:feature`,
    `priority:must`.
21. **Implement API test runner and sanitization** — `REQ-024`, `REQ-025`;
    labels `phase:7-issue-api`, `type:feature`, `priority:must`.

### Integrations and pipelines

22. **Implement GitLab issue and repository adapter** — `REQ-026`; labels
    `phase:7-issue-api`, `type:feature`, `priority:should`.
23. **Implement GitLab pipeline, jobs, logs, and artifacts adapter** —
    `REQ-026`; labels `phase:8-pipelines`, `type:feature`, `priority:should`.
24. **Implement approved issue comment publishing and audit trail** —
    `REQ-027`; labels `phase:9-issue-management`, `type:feature`,
    `priority:must`.

### AI, analysis, security, and community

25. **Implement provider contract and built-in agent** — `REQ-028`,
    `REQ-029`; labels `phase:10-ai`, `type:architecture`, `priority:should`.
26. **Implement OpenCode and optional Ollama adapters** — `REQ-028`;
    labels `phase:10-ai`, `type:feature`, `priority:should`.
27. **Implement approvals, autonomy modes, and security controls** —
    `REQ-030`, `NFR-005`, `NFR-010`; labels `phase:10-ai`,
    `type:architecture`, `priority:must`.
28. **Implement bug hunting, release analysis, and authorized security
    testing** — `REQ-031`, `REQ-032`; labels `phase:11-analysis-security`,
    `type:feature`, `priority:must`.
29. **Add reports, evidence export, and Obsidian-compatible navigation** —
    `REQ-032`, `NFR-008`; labels `phase:12-stabilization`, `type:feature`,
    `priority:must`.
30. **Harden packaging, compatibility, examples, releases, and community
    documentation** — `NFR-001`, `NFR-009`; labels `phase:12-stabilization`,
    `type:documentation`, `priority:must`.

## Issue body requirements

Each published issue must contain:

1. Context and user value.
2. Linked requirement IDs.
3. Scope and explicit non-scope.
4. Dependencies.
5. Acceptance criteria as checkboxes.
6. Test strategy and evidence expected.
7. Security and compatibility considerations.
