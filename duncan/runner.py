from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class BaselineResult:
    passed: bool
    returncode: int
    summary: str
    stdout: str
    stderr: str
    command: List[str]
    duration_seconds: float
    timed_out: bool = False


def _last_line_of(text: str) -> Optional[str]:
    if not text:
        return None
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1] if lines else None


def run_baseline_tests(project_root: Path, timeout: int = 120, pytest_args: Optional[List[str]] = None) -> BaselineResult:
    """Run the target project's pytest suite as a baseline.

    Returns a BaselineResult that includes stdout and stderr. The summary field
    is heuristically derived from the last non-empty line of stdout or stderr.
    """
    cmd = [sys.executable, "-m", "pytest", "-q"]
    if pytest_args:
        cmd.extend(pytest_args)

    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.TimeoutExpired may include partial stdout/stderr on some versions.
        stdout = getattr(exc, "stdout", "") or ""
        stderr = getattr(exc, "stderr", "") or ""
        summary = f"timed out after {timeout} seconds"
        return BaselineResult(False, 124, summary, stdout, stderr, cmd, time.monotonic() - started, True)

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    # If pytest isn't installed in the target environment, python -m pytest will
    # emit a ModuleNotFoundError to stderr. Surface a clearer summary for that case.
    if proc.returncode != 0 and ("No module named pytest" in stderr or "ModuleNotFoundError: No module named 'pytest'" in stderr):
        summary = "pytest not available in the target interpreter"
        return BaselineResult(False, proc.returncode, summary, stdout, stderr, cmd, time.monotonic() - started)

    # Prefer last line of stdout, fall back to stderr last line, then a default.
    summary = _last_line_of(stdout) or _last_line_of(stderr) or "(no test output — is this a pytest project?)"

    return BaselineResult(proc.returncode == 0, proc.returncode, summary, stdout, stderr, cmd, time.monotonic() - started)
