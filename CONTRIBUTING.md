# Contributing

## Commit messages

Use Conventional Commits:

```text
<type>(optional-scope): concise imperative summary

Explain why the change is needed, its behavior or tradeoffs, and any important
verification for non-trivial work.
```

Allowed types: `feat`, `fix`, `test`, `docs`, `refactor`, `ci`, `chore`,
`perf`, `build`, and `revert`.

Examples:

```text
feat(probes): detect mutable guarded state

Reduce false positives by requiring state candidates to be written outside
construction before runtime verification.
```

```text
fix(runner): preserve target pytest exit codes
```

## Atomic changes

- Keep one logical change in each commit.
- Separate implementation, unrelated cleanup, and documentation when they can
  be reviewed or reverted independently.
- Every commit must leave the repository in a testable state.
- Add or update tests with behavior changes.

## Pull requests

- Use the same Conventional Commit format for the PR title.
- Explain why the change exists, what it affects, and how it was verified.
- Keep the PR focused on one feature, fix, or maintenance objective.
- Run the full test suite and an end-to-end fixture before merging.

## Releases

Use annotated semantic-version tags (`vMAJOR.MINOR.PATCH`) for meaningful,
verified milestones. Never move or reuse a published tag.
