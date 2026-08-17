from __future__ import annotations

import argparse
import sys
import logging
from pathlib import Path
from typing import List, Optional

from duncan.probes.state_guard_bypass import StateGuardBypassProbe
from duncan.ai import analyze_with_openai
from duncan.report import render_json, render_markdown
from duncan.runner import run_baseline_tests
from duncan.sandbox import Sandbox

_log = logging.getLogger(__name__)

# Keep probe classes here (not instances) so we instantiate at runtime and avoid
# side effects on import.
PROBE_CLASSES = [StateGuardBypassProbe]


def _probe_name(cls) -> str:
    return cls.__name__


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="duncan", description="Run the adversarial test suite against a target project."
    )
    parser.add_argument("project", type=Path, help="Path to the project to test")
    parser.add_argument("--out", type=Path, default=None, help="Where to write the markdown report")
    parser.add_argument("--json-out", type=Path, default=None, help="Where to write the JSON report")
    parser.add_argument("--ai", action="store_true", help="Analyze results with OpenAI (requires OPENAI_API_KEY and the ai extra)")
    parser.add_argument("--ai-model", default=None, help="OpenAI model used with --ai")
    parser.add_argument("--list-probes", action="store_true", help="List available probes and exit")
    parser.add_argument("--probe", action="append", help="Run only the named probe (may be given multiple times)")
    parser.add_argument("--pytest-arg", action="append", dest="pytest_args", help="Extra argument passed to pytest (can be given multiple times)")
    parser.add_argument("--keep-sandbox", action="store_true", help="Keep the temporary sandbox directory after run (for debugging)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args(argv)

    # Configure logging
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    source_root = args.project.resolve()
    if not source_root.exists():
        print(f"error: {source_root} does not exist", file=sys.stderr)
        return 2

    if args.list_probes:
        for cls in PROBE_CLASSES:
            print(_probe_name(cls))
        return 0

    # Determine probe classes to run
    selected = None
    if args.probe:
        requested = {name.lower() for name in args.probe}
        selected = [cls for cls in PROBE_CLASSES if _probe_name(cls).lower() in requested]
        missing = [name for name in args.probe if name.lower() not in { _probe_name(cls).lower() for cls in PROBE_CLASSES }]
        if missing:
            print(f"error: unknown probes: {', '.join(missing)}", file=sys.stderr)
            return 3
    else:
        selected = PROBE_CLASSES

    # Use the Sandbox context manager so we clean up automatically unless the user asks to keep it.
    try:
        with Sandbox(source_root, keep=args.keep_sandbox) as sandbox_root:
            _log.info("running baseline tests in sandbox %s", sandbox_root)
            baseline = run_baseline_tests(sandbox_root, pytest_args=args.pytest_args)

            findings = []
            probe_errors = []
            for cls in selected:
                probe_name = _probe_name(cls)
                _log.info("running probe %s", probe_name)
                probe = cls()
                try:
                    probe_findings = probe.run(sandbox_root)
                except Exception as exc:
                    _log.exception("probe %s raised an exception; continuing with others", probe_name)
                    probe_errors.append(f"{probe_name}: {type(exc).__name__}: {exc}")
                    continue
                if probe_findings:
                    findings.extend(probe_findings)

            context = "\n".join([baseline.summary, baseline.stdout, baseline.stderr] + [str(f.to_dict()) for f in findings] + probe_errors)
            ai = analyze_with_openai(context, args.ai_model) if args.ai else None
            report = render_markdown(source_root.name, baseline, findings, ai)
            out_path = args.out or (Path.cwd() / f"duncan_report_{source_root.name}.md")
            json_path = args.json_out or out_path.with_suffix(".json")
            try:
                out_path.write_text(report, encoding="utf-8")
                json_path.write_text(render_json(source_root.name, baseline, findings, ai), encoding="utf-8")
            except Exception:
                _log.exception("failed to write report to %s", out_path)
                print(report)
                print(f"\nfailed to write report to {out_path}", file=sys.stderr)
                return 4

            print(report)
            print(f"\nReports written to {out_path} and {json_path}")
            if probe_errors:
                return 6
            return 0 if baseline.passed else baseline.returncode or 1
    except Exception:
        _log.exception("error while preparing or running the sandbox")
        return 5


if __name__ == "__main__":
    raise SystemExit(main())
