from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any

from duncan.findings import Finding, Severity
from duncan.probes.base import Probe

_RISKY_CALL_NAMES = {"open", "eval", "exec", "system", "popen", "run", "call", "check_call", "check_output", "urlopen", "request"}


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""


def _mutated_outside_constructor(cls: ast.ClassDef) -> set[str]:
    """Return attributes assigned through ``self.X`` after construction.

    This distinguishes guarded state fields from read-only decision inputs that
    merely appear in the same raising condition as a genuinely guarded field.
    """
    mutated: set[str] = set()
    for method in (n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        if method.name in {"__init__", "__post_init__"}:
            continue
        for node in ast.walk(method):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                    mutated.add(target.attr)
    return mutated


def _guarded_attributes(cls: ast.ClassDef) -> set[str]:
    candidates: set[str] = set()
    for method in (n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))):
        if method.name in {"__init__", "__post_init__"}:
            continue
        for condition in (n.test for n in ast.walk(method) if isinstance(n, (ast.If, ast.While))):
            if not any(isinstance(n, ast.Raise) for n in ast.walk(method)):
                continue
            for node in ast.walk(condition):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "self":
                    candidates.add(node.attr)
    # A candidate only counts as a real guarded-state field if it's also
    # written somewhere after construction. Otherwise it's a read-only
    # decision input that happened to sit near someone else's guard.
    return candidates & _mutated_outside_constructor(cls)


def _has_protection(cls: ast.ClassDef, name: str) -> bool:
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            decorators = {d.id for d in node.decorator_list if isinstance(d, ast.Name)}
            decorators |= {d.attr for d in node.decorator_list if isinstance(d, ast.Attribute)}
            if "property" in decorators or "setter" in decorators:
                return True
    return False


def _constructor_is_risky(cls: ast.ClassDef) -> bool:
    constructors = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {"__init__", "__post_init__"}]
    return any(_call_name(n) in _RISKY_CALL_NAMES for method in constructors for n in ast.walk(method) if isinstance(n, ast.Call))


def _dummy(annotation: Any) -> Any:
    if annotation in (int, float, bool, str, bytes):
        return annotation()
    if inspect.isclass(annotation) and issubclass(annotation, Enum):
        return next(iter(annotation))
    return "duncan"


def _construct(cls: type) -> Any:
    signature = inspect.signature(cls)
    kwargs = {}
    for name, parameter in signature.parameters.items():
        if parameter.default is not inspect.Parameter.empty or parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        annotation = parameter.annotation
        kwargs[name] = _dummy(annotation) if annotation is not inspect.Parameter.empty else "duncan"
    return cls(**kwargs)


def _load(path: Path, root: Path) -> ModuleType:
    relative = path.relative_to(root).with_suffix("")
    name = "duncan_target_" + "_".join(relative.parts)
    root_str = str(root)
    added_root = False
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
        added_root = True
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        if added_root:
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass


class StateGuardBypassProbe(Probe):
    def run(self, source_root: Path) -> list[Finding]:
        findings: list[Finding] = []
        for path in sorted(source_root.rglob("*.py")):
            if any(part.startswith(".") or part in {"venv", ".venv", "__pycache__"} for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
            for class_node in classes:
                for attribute in sorted(_guarded_attributes(class_node)):
                    if attribute.startswith("_") or _has_protection(class_node, attribute):
                        continue
                    target = f"{path.relative_to(source_root).with_suffix('').as_posix().replace('/', '.')}.{class_node.name}.{attribute}"
                    severity = Severity.SUSPECTED
                    evidence = "Public guarded attribute is statically assignable."
                    if _constructor_is_risky(class_node):
                        evidence += " Constructor is too risky to auto-build."
                    else:
                        try:
                            cls = getattr(_load(path, source_root), class_node.name)
                            instance = _construct(cls)
                            current = getattr(instance, attribute)
                            setattr(instance, attribute, current)
                            severity = Severity.CONFIRMED
                            evidence = f"Assigned {attribute!r} directly at runtime; no exception raised."
                        except AttributeError:
                            severity = Severity.INFO
                            evidence = "Direct assignment raised AttributeError; runtime protection exists."
                        except Exception as exc:
                            evidence += f" Runtime verification unavailable: {type(exc).__name__}: {exc}"
                    findings.append(Finding(
                        probe=self.__class__.__name__, target=target, severity=severity,
                        description="A state guard can be bypassed by assigning the public attribute directly.",
                        evidence=evidence,
                        suggested_fix=f"Store state in _{attribute} and expose a read-only property or a validating setter.",
                    ))
        return findings
