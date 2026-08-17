import sys
from pathlib import Path

from duncan.findings import Severity
from duncan.probes.state_guard_bypass import StateGuardBypassProbe

UNPROTECTED_SOURCE = '''
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"
    FINISHED = "finished"


@dataclass
class Session:
    objective: str
    status: Status = Status.PLANNING

    def finish(self) -> None:
        if self.status != Status.RUNNING:
            raise ValueError("cannot finish a session that is not running")
        self.status = Status.FINISHED
'''

PROTECTED_SOURCE = '''
from enum import Enum


class Status(str, Enum):
    PLANNING = "planning"
    RUNNING = "running"


class Plan:
    def __init__(self, objective: str) -> None:
        self.objective = objective
        self._status = Status.PLANNING

    @property
    def status(self) -> Status:
        return self._status

    @status.setter
    def status(self, value) -> None:
        raise AttributeError("status only changes through submit()/approve()")

    def approve(self) -> None:
        if self._status != Status.PLANNING:
            raise ValueError("cannot approve a plan that is not planning")
        self._status = Status.RUNNING
'''


def make_project(tmp_path: Path, filename: str, source: str) -> Path:
    project = tmp_path / "target"
    project.mkdir()
    (project / filename).write_text(source)
    return project


def run_probe(project_root: Path):
    return StateGuardBypassProbe().run(project_root)


NON_DATACLASS_UNPROTECTED_SOURCE = '''
class Folio:
    """A guest's running bill — a plain class, not a @dataclass."""

    def __init__(self, guest_name: str) -> None:
        self.guest_name = guest_name
        self.charges = []
        self.closed = False

    def post_charge(self, amount: float, description: str) -> None:
        if self.closed:
            raise ValueError("cannot post a charge to a closed folio")
        self.charges.append((amount, description))

    def close(self) -> None:
        self.closed = True
'''

RISKY_CONSTRUCTOR_SOURCE = '''
class LogWriter:
    def __init__(self, path: str) -> None:
        self.handle = open(path, "w")
        self.locked = False

    def unlock(self) -> None:
        if self.locked:
            raise ValueError("already unlocked, cannot unlock again")
        self.locked = False
'''


def test_non_dataclass_guarded_attribute_is_confirmed_at_runtime(tmp_path):
    project = make_project(tmp_path, "folio_mod.py", NON_DATACLASS_UNPROTECTED_SOURCE)
    findings = run_probe(project)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.target == "folio_mod.Folio.closed"
    assert finding.severity == Severity.CONFIRMED
    assert "no exception raised" in finding.evidence


def test_risky_constructor_is_not_auto_built(tmp_path):
    project = make_project(tmp_path, "risky_mod.py", RISKY_CONSTRUCTOR_SOURCE)
    findings = run_probe(project)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.severity == Severity.SUSPECTED
    assert "too risky to auto-build" in finding.evidence


def test_publicly_settable_guarded_attribute_is_confirmed_at_runtime(tmp_path):
    project = make_project(tmp_path, "session_mod.py", UNPROTECTED_SOURCE)
    findings = run_probe(project)

    assert len(findings) == 1
    finding = findings[0]
    assert finding.target == "session_mod.Session.status"
    assert finding.severity == Severity.CONFIRMED
    assert "no exception raised" in finding.evidence


def test_property_protected_attribute_produces_no_finding(tmp_path):
    project = make_project(tmp_path, "plan_mod.py", PROTECTED_SOURCE)
    findings = run_probe(project)

    assert findings == []


def test_class_with_no_guard_clauses_is_ignored(tmp_path):
    project = make_project(
        tmp_path,
        "plain_mod.py",
        "class Widget:\n    def __init__(self, size):\n        self.size = size\n",
    )
    findings = run_probe(project)

    assert findings == []


def test_empty_project_yields_no_findings(tmp_path):
    project = tmp_path / "empty"
    project.mkdir()
    findings = run_probe(project)

    assert findings == []


def test_runtime_verification_supports_target_local_imports_and_restores_sys_path(tmp_path):
    project = tmp_path / "target"
    project.mkdir()
    (project / "statuses.py").write_text(
        'from enum import Enum\nclass Status(str, Enum):\n    OPEN = "open"\n    CLOSED = "closed"\n'
    )
    (project / "session.py").write_text(
        "from statuses import Status\n\n"
        "class Session:\n"
        "    def __init__(self):\n"
        "        self.status = Status.OPEN\n"
        "    def close(self):\n"
        "        if self.status != Status.OPEN:\n"
        "            raise ValueError('already closed')\n"
        "        self.status = Status.CLOSED\n"
    )

    project_str = str(project)
    assert project_str not in sys.path
    findings = run_probe(project)

    assert any(f.target == "session.Session.status" for f in findings)
    assert project_str not in sys.path


def test_constructor_validation_is_not_treated_as_state_guard(tmp_path):
    project = make_project(
        tmp_path,
        "reservation.py",
        "class Reservation:\n"
        "    def __init__(self, nights: int):\n"
        "        if self.nights < 1:\n"
        "            raise ValueError('nights must be positive')\n"
        "        self.nights = nights\n",
    )

    assert run_probe(project) == []
