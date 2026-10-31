# Security Policy

## Supported versions

Dark Knight QA is in early development. Security fixes are currently
provided for the default branch and the latest published release, when a
release exists.

## Reporting a vulnerability

Please do not open a public issue for an exploitable vulnerability. Use
GitHub's **Report a vulnerability** option in the repository's Security tab
when it is available. If private reporting is unavailable, contact the
repository owner through GitHub and include only the minimum information
needed to reproduce the issue.

Include:

- affected version or commit;
- impact and attack prerequisites;
- minimal reproduction steps;
- logs or evidence with secrets and personal data removed.

Allow maintainers reasonable time to investigate before public disclosure.
Do not test against systems or data you do not own or have explicit
authorization to assess.

## Security principles

The project must not commit secrets, private evidence, or unredacted
credentials. External actions, intrusive testing, and destructive operations
must remain explicitly authorized and auditable.

## How the application applies them

This describes what the code does today, so reports can be checked against it.

- **Secrets stay out of files.** API definitions, project settings, and
  records name environment variables (for example `API_TOKEN`, `GITLAB_TOKEN`)
  instead of holding values, and loading refuses a file that contains a literal
  credential. Requests, responses, logs, console output, and URLs are sanitized
  before they are saved, and a saved result that still looks like it holds a
  credential is not written at all.
- **Tokens kept by the application.** `batman config token set` stores a token
  in `credentials.json` in the user's configuration directory (never in a
  project, a record, an export, or the repository). The file is created
  readable by its owner only on Linux and macOS; on Windows it relies on the
  per-user permissions of the configuration folder, which other standard users
  cannot read, but it is not encrypted. A token is never printed, logged,
  audited, or put in an error message, and an environment variable of the same
  name always wins. Anyone who can read your user profile can read the file; use
  the environment variable if that is not acceptable. The operating system
  keyring is not used, on purpose: a file behaves the same on all three
  platforms and adds no dependency. Tokens can be set, listed, and removed from
  the CLI and from the Settings page of the TUI (typed hidden), and the first-run
  welcome offers to keep the GitLab token. `batman doctor` shows, per service,
  whether a token is set and where it comes from, never the value.
- **Nothing external happens by surprise.** The browser opens only hosts a
  project allows (without a project, only local addresses), and the same scope
  and a per-host rate limit apply to API tests, GitLab reads, and security
  checks. Deleting through an API test always waits for a person.
- **Writes need a person.** Publishing an issue comment, opening an issue from a
  finding (with its evidence uploads, which the workbench cannot delete), and every other action
  the policy marks as sensitive, creates an approval request that a person must
  decide. An approval covers exactly one action, is single-use, expires after an
  hour, and cannot be given by whoever asked.
- **Security checks are authorized and passive.** They run only under an
  expiring, scoped authorization and only read responses; they never send
  payloads, and a clean result is never reported as proof of security.
- **A tamper-evident trail.** Approvals, decisions, settings changes, and
  security checks are written to a hash-chained audit log; editing, removing, or
  reordering an entry is detected.
- **AI output is analysis, not evidence.** Text from issues, pages, and logs is
  handed to AI providers fenced as untrusted data, and a claim the assistant
  cannot source from a record it actually saw is shown as a hypothesis.
- **A hosted AI engine is remote, opt-in, and guarded.** The `nvidia` engine
  sends the question and the records it mentions to the NVIDIA API Catalog, so it
  is never chosen by `auto`; it must be asked for by name, and the CLI and the TUI
  say that data left the machine. Every engine request (local ones too) goes
  through the action guard: a host that is not in the project's allowed hosts gets
  nothing and the message says how to allow it, requests count against the rate
  limit, and the audit log records the action and the URL, never the body or any
  header. Text is passed through secret redaction before it is sent. The `claude`
  engine (the Claude Code CLI, using the person's own login) follows the same
  rules, with `api.anthropic.com` as the host the guard checks before the process
  starts; it runs with every tool disabled, no saved session, no skills or MCP
  servers, and an empty working directory, so it cannot touch local files. The API key
  (`NVIDIA_API_KEY`, or `batman config token set nvidia`) is never printed,
  logged, audited, or put in an error message, even if the server echoes it.

Known limits: browser traces and videos are not scrubbed of sensitive data,
process isolation is not implemented, and intrusive security testing does not
exist. If you find a way around any of the above, that is a vulnerability: please
report it as described earlier.
