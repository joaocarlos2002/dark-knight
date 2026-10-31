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
- **Nothing external happens by surprise.** The browser opens only hosts a
  project allows (without a project, only local addresses), and the same scope
  and a per-host rate limit apply to GitLab reads and security checks.
- **Writes need a person.** Publishing an issue comment, and every other action
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

Known limits: browser traces and videos are not scrubbed of sensitive data,
process isolation is not implemented, and intrusive security testing does not
exist. If you find a way around any of the above, that is a vulnerability: please
report it as described earlier.
