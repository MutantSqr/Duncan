import json
from pathlib import Path

from duncan.ai import analyze_with_openai
from duncan.cli import main
from duncan.report import render_json, render_markdown
from duncan.runner import BaselineResult, run_baseline_tests
from duncan.sandbox import Sandbox


def make_target(tmp_path: Path, body: str) -> Path:
    target = tmp_path / "target"
    target.mkdir()
    (target / "test_example.py").write_text(body, encoding="utf-8")
    return target


def test_runner_captures_failure_logs_and_exit_code(tmp_path):
    target = make_target(tmp_path, 'def test_bad():\n    print("LOG_MARKER")\n    assert False\n')
    result = run_baseline_tests(target)
    assert not result.passed
    assert result.returncode == 1
    assert "LOG_MARKER" in result.stdout
    assert "1 failed" in result.summary
    assert result.command[-2:] == ["pytest", "-q"]


def test_cli_writes_markdown_and_json_and_propagates_failure(tmp_path):
    target = make_target(tmp_path, "def test_bad():\n    assert False\n")
    markdown = tmp_path / "report.md"
    structured = tmp_path / "report.json"
    code = main([str(target), "--out", str(markdown), "--json-out", str(structured)])
    assert code == 1
    assert "Exit code: `1`" in markdown.read_text(encoding="utf-8")
    payload = json.loads(structured.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["baseline"]["returncode"] == 1
    assert not payload["baseline"]["passed"]


def test_reports_preserve_all_baseline_evidence():
    baseline = BaselineResult(False, 2, "collection failed", "stdout-data", "stderr-data", ["python", "-m", "pytest"], 0.25)
    markdown = render_markdown("sample", baseline, [])
    payload = json.loads(render_json("sample", baseline, []))
    assert "stdout-data" in markdown and "stderr-data" in markdown
    assert payload["baseline"]["stdout"] == "stdout-data"
    assert payload["baseline"]["stderr"] == "stderr-data"


def test_sandbox_does_not_modify_original_and_cleans_up(tmp_path):
    target = make_target(tmp_path, "def test_ok():\n    assert True\n")
    original = (target / "test_example.py").read_text()
    with Sandbox(target) as copy:
        parent = copy.parent
        (copy / "test_example.py").write_text("changed")
    assert (target / "test_example.py").read_text() == original
    assert not parent.exists()


def test_ai_is_disabled_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = analyze_with_openai("test context")
    assert result.status == "disabled"
