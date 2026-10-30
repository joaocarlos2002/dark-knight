# Contributing to Dark Knight QA

Thank you for helping build Dark Knight QA. The project is in its
foundation phase, so small, focused contributions are especially valuable.

## Before you start

1. Read the [README](README.md) and the [product specification](docs/product-spec.md).
2. Check existing issues before opening a new one.
3. For architectural, security, persistence, or compatibility changes,
   describe the proposal in an issue before implementing it.
4. Do not include credentials, private data, real customer evidence, or
   unredacted logs in commits or issue reports.

## Development workflow

1. Create a branch from `master`.
2. Link your pull request to an issue.
3. Keep each pull request focused on one coherent change.
4. Add or update tests and documentation when behavior or public contracts
   change.
5. Run the relevant checks locally and report the exact commands and results.
6. Request review only after the pull request checklist is complete.

## Design expectations

- Preserve the Markdown-first source of truth.
- Keep domain rules separate from presentation.
- Prefer explicit errors over silent fallbacks.
- Preserve Windows, Linux, and macOS compatibility where dependencies allow.
- Treat AI output as recommendations; execution evidence is authoritative.

## Commit and pull request titles

Use a short imperative title, for example:

```text
Add project metadata validation
```

Pull requests should explain the problem, the solution, scope boundaries,
testing evidence, compatibility impact, and any security considerations.

## Questions

Use [GitHub Discussions](https://github.com/joaocarlos2002/dark-knight/discussions)
for design questions and [Issues](https://github.com/joaocarlos2002/dark-knight/issues)
for actionable bugs and work items.
