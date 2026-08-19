from pathlib import Path

from duncan.findings import Severity
from duncan.probes.dangerous_execution import DangerousExecutionProbe


def _scan(tmp_path: Path, source: str):
    (tmp_path / "module.py").write_text(source, encoding="utf-8")
    return DangerousExecutionProbe().run(tmp_path)


def test_shell_true_subprocess_is_confirmed(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run('echo hello', shell=True)\n",
    )

    assert len(findings) == 1
    assert findings[0].severity is Severity.CONFIRMED
    assert findings[0].target == "module.py:2"
    assert "shell=True" in findings[0].evidence


def test_subprocess_alias_and_direct_import_are_detected(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess as sp\nfrom subprocess import Popen as launch\n"
        "sp.check_output('whoami', shell=True)\nlaunch('echo hi', shell=True)\n",
    )

    assert len(findings) == 2
    assert all(finding.severity is Severity.CONFIRMED for finding in findings)


def test_dynamic_shell_flag_is_suspected(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\ndef run(cmd, use_shell):\n    return subprocess.run(cmd, shell=use_shell)\n",
    )

    assert len(findings) == 1
    assert findings[0].severity is Severity.SUSPECTED
    assert "cannot be proven false" in findings[0].evidence


def test_shell_false_or_omitted_is_not_flagged(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "import subprocess\nsubprocess.run(['echo', 'hi'])\nsubprocess.run(['echo', 'hi'], shell=False)\n",
    )

    assert findings == []


def test_names_that_resemble_modules_are_not_flagged_without_imports(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "class Fake:\n"
        "    def run(self, *args, **kwargs): return None\n"
        "    def system(self, *args, **kwargs): return None\n"
        "subprocess = Fake()\n"
        "os = Fake()\n"
        "subprocess.run('echo hi', shell=True)\n"
        "os.system('echo hi')\n",
    )

    assert findings == []


def test_os_system_and_popen_are_confirmed(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "import os as operating\noperating.system('echo hi')\noperating.popen('whoami')\n",
    )

    assert len(findings) == 2
    assert all(finding.severity is Severity.CONFIRMED for finding in findings)
    assert all("system shell" in finding.description for finding in findings)


def test_eval_and_exec_are_suspected(tmp_path) -> None:
    findings = _scan(
        tmp_path,
        "def f(text):\n    value = eval(text)\n    exec(text)\n    return value\n",
    )

    assert len(findings) == 2
    assert all(finding.severity is Severity.SUSPECTED for finding in findings)


def test_hidden_and_virtualenv_directories_are_ignored(tmp_path) -> None:
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "bad.py").write_text("exec('x')\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "bad.py").write_text("exec('x')\n", encoding="utf-8")
    (tmp_path / "safe.py").write_text("print('ok')\n", encoding="utf-8")

    assert DangerousExecutionProbe().run(tmp_path) == []


def test_syntax_errors_do_not_abort_scan(tmp_path) -> None:
    (tmp_path / "broken.py").write_text("def nope(:\n", encoding="utf-8")
    (tmp_path / "good.py").write_text("import os\nos.system('echo hi')\n", encoding="utf-8")

    findings = DangerousExecutionProbe().run(tmp_path)

    assert len(findings) == 1
    assert findings[0].target == "good.py:2"
