from __future__ import annotations

import ast
from pathlib import Path

from duncan.findings import Finding, Severity
from duncan.probes.base import Probe

_SUBPROCESS_CALLS = {"run", "Popen", "call", "check_call", "check_output"}
_IGNORED_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "__pycache__", "node_modules"}


def _skip(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return any(part.startswith(".") or part in _IGNORED_DIRS for part in relative.parts[:-1])


def _aliases(tree: ast.AST) -> tuple[set[str], set[str], set[str]]:
    """Return subprocess module aliases, os aliases, and directly imported subprocess call names."""
    subprocess_aliases = {"subprocess"}
    os_aliases = {"os"}
    subprocess_functions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                if name.name == "subprocess":
                    subprocess_aliases.add(name.asname or name.name)
                elif name.name == "os":
                    os_aliases.add(name.asname or name.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for name in node.names:
                if name.name in _SUBPROCESS_CALLS:
                    subprocess_functions.add(name.asname or name.name)
    return subprocess_aliases, os_aliases, subprocess_functions


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    return None


def _is_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _is_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _call_target(call: ast.Call) -> tuple[str, str]:
    if isinstance(call.func, ast.Name):
        return "", call.func.id
    if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
        return call.func.value.id, call.func.attr
    return "", ""


class DangerousExecutionProbe(Probe):
    """Find high-risk dynamic or shell-backed execution surfaces.

    This probe is deliberately static and high signal. It does not claim that
    every use is exploitable; it flags execution primitives that deserve human
    review in agentic/system-control code.
    """

    def run(self, source_root: Path) -> list[Finding]:
        findings: list[Finding] = []
        for path in sorted(source_root.rglob("*.py")):
            if _skip(path, source_root):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            subprocess_aliases, os_aliases, subprocess_functions = _aliases(tree)
            relative = path.relative_to(source_root).as_posix()

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                owner, name = _call_target(node)
                target = f"{relative}:{node.lineno}"

                if (owner in subprocess_aliases and name in _SUBPROCESS_CALLS) or (
                    not owner and name in subprocess_functions
                ):
                    shell = _keyword(node, "shell")
                    if shell is None or _is_false(shell):
                        continue
                    if _is_true(shell):
                        severity = Severity.CONFIRMED
                        evidence = f"Line {node.lineno}: subprocess execution explicitly sets shell=True."
                    else:
                        severity = Severity.SUSPECTED
                        evidence = (
                            f"Line {node.lineno}: subprocess shell= value is dynamic and cannot be proven false."
                        )
                    findings.append(
                        Finding(
                            probe=self.__class__.__name__,
                            target=target,
                            severity=severity,
                            description="A subprocess call may execute through a command shell.",
                            evidence=evidence,
                            suggested_fix=(
                                "Prefer shell=False (the default) and pass the executable/arguments as a sequence. "
                                "If a shell is unavoidable, strictly constrain all interpolated input."
                            ),
                        )
                    )
                    continue

                if owner in os_aliases and name in {"system", "popen"}:
                    findings.append(
                        Finding(
                            probe=self.__class__.__name__,
                            target=target,
                            severity=Severity.CONFIRMED,
                            description=f"os.{name} invokes a system shell.",
                            evidence=f"Line {node.lineno}: call to {owner}.{name}(...).",
                            suggested_fix=(
                                "Use subprocess with shell=False and an argument sequence; validate any external input."
                            ),
                        )
                    )
                    continue

                if not owner and name in {"eval", "exec"}:
                    findings.append(
                        Finding(
                            probe=self.__class__.__name__,
                            target=target,
                            severity=Severity.SUSPECTED,
                            description=f"Dynamic Python execution via {name}() expands the code-execution surface.",
                            evidence=f"Line {node.lineno}: call to built-in {name}(...).",
                            suggested_fix=(
                                "Prefer structured parsing/dispatch. If dynamic execution is required, isolate it and "
                                "never feed it untrusted or model-generated text."
                            ),
                        )
                    )
        return findings
