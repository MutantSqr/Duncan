# Duncan

An adversarial test runner for Python projects. Point Duncan at a project and it does two things:

1. Runs the project's own `pytest` suite as a baseline.
2. Looks for security and guardrail failures that the project's own tests may not cover.

Duncan runs against a throwaway copy of the target project and writes both Markdown and JSON reports.

## Usage

```bash
python -m pip install -e .
duncan /path/to/some/project
```

For optional AI-assisted diagnosis:

```bash
python -m pip install -e '.[ai]'
export OPENAI_API_KEY='...'
duncan /path/to/some/project --ai
```

AI analysis is opt-in. Normal baseline testing and adversarial probes work without an API key.
`DUNCAN_AI_MODEL` or `--ai-model` selects the optional analysis model.

Useful probe controls:

```bash
duncan /path/to/project --list-probes
duncan /path/to/project --probe StateGuardBypassProbe
duncan /path/to/project --probe DangerousExecutionProbe
```

Reports include the baseline command, duration, exit code, stdout/stderr, probe findings, and optional AI analysis. Duncan returns the target pytest exit code when the baseline fails.

## Sandbox boundary

Every run happens against a throwaway copy of the target (`duncan/sandbox.py`), so Duncan does not intentionally modify the original working tree.

> **Trust boundary:** the throwaway copy protects the original project files; it is not an operating-system security boundary. Baseline tests execute target code. Run untrusted projects only inside a locked-down disposable container or worker.

## Current probes

### StateGuardBypassProbe

Looks for state or configuration attributes that appear to be protected by a method-level guard but remain directly writable from outside the object.

Example:

```python
def finish(self) -> None:
    if self.status is not SessionStatus.RUNNING:
        raise ValueError("not running")
    self.status = SessionStatus.FINISHED
```

If `status` is a plain public attribute, callers may be able to skip `finish()` entirely by assigning to `status` themselves.

Detection is static (AST). Duncan attempts runtime verification where object construction is safe enough:

- `CONFIRMED` — Duncan reproduced the bypass.
- `SUSPECTED` — the static pattern exists, but Duncan could not safely prove it at runtime.
- `INFO` — the static pattern looked suspicious but runtime verification showed the assignment was protected.

Constructor risk gates prevent Duncan from blindly instantiating classes whose initializer directly performs obvious file, network, subprocess, `eval`, or `exec` operations.

### DangerousExecutionProbe

Looks for high-risk execution surfaces that deserve review in agentic or system-control code.

Currently flags:

- `subprocess.*(..., shell=True)` as **CONFIRMED**.
- dynamic `shell=<expression>` values as **SUSPECTED** when Duncan cannot prove the value is `False`.
- `os.system(...)` and `os.popen(...)` as **CONFIRMED** shell execution.
- built-in `eval(...)` and `exec(...)` as **SUSPECTED** dynamic Python execution.

The probe understands common aliases such as `import subprocess as sp` and directly imported subprocess functions. It requires the relevant `subprocess`/`os` import before treating a matching variable name as that module, reducing false positives. Ordinary subprocess calls with the default `shell=False`, or explicit `shell=False`, are not flagged.

A finding is not automatically proof of exploitability. It is evidence that a dangerous execution primitive exists and should be reviewed in context.

## Supported targets

Duncan currently accepts a local Python project and runs its pytest suite with the same Python interpreter that runs Duncan. Clone remote repositories and install their dependencies in an isolated environment before invoking it.

## Known limitations

- State-guard runtime verification relies on safe constructor inference. Missing type hints or complex validation can leave a real bypass at `SUSPECTED` instead of `CONFIRMED`.
- The constructor risk gate scans `__init__` / `__post_init__` directly. A constructor that delegates risky behavior into a helper may not be recognized by that gate.
- State-guard co-occurrence is not always causation: a guarded method can read an attribute even when that attribute is not the thing the guard is intended to protect.
- Dangerous-execution findings are static. `eval`/`exec` or shell use may operate only on trusted constants, so human review still matters.
- Duncan is not an OS sandbox and does not make executing untrusted test suites safe.

## Adding a probe

Every adversarial angle is a `Probe` subclass (`duncan/probes/base.py`) with one method:

```python
run(source_root: Path) -> list[Finding]
```

Register the class in `duncan/cli.py`'s `PROBE_CLASSES` list. The runner and report pipeline do not need to know probe-specific implementation details.

Good future candidates include boundary-value crash testing, duplicate-registration behavior, provider/dependency exhaustion, path-confinement bypasses, and permission-ordering failures.

## Validation

Duncan's CI currently runs the complete suite on Python 3.10, 3.11, 3.12, and 3.13.

## Author

**MutantSqr**
