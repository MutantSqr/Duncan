from __future__ import annotations

from typing import List

from duncan.findings import Finding, Severity
from duncan.runner import BaselineResult

_ORDER = [Severity.CONFIRMED, Severity.SUSPECTED, Severity.INFO]
_LABELS = {
    Severity.CONFIRMED: "Confirmed",
    Severity.SUSPECTED: "Suspected",
    Severity.INFO: "Info (false positives caught)",
}


def _fence_if_multiline(value: str) -> str:
    if value is None:
        return ""
    if "\n" in value or "`" in value:
        # Use fenced code block for multi-line evidence or if backticks are present.
        return "```\n" + value.rstrip() + "\n```"
    # Single-line content is safe inline.
    return value


def render_markdown(project_name: str, baseline: BaselineResult, findings: List[Finding]) -> str:
    lines = [f"# Duncan report — {project_name}", ""]

    lines.append("## Baseline test suite")
    lines.append(f"- Result: **{'PASS' if baseline.passed else 'FAIL'}**")
    # Show the pytest summary in inline code, but if it's multi-line, render as a code block.
    summary = baseline.summary or ""
    if "\n" in summary:
        lines.append("- pytest summary:")
        lines.append("```")
        lines.append(summary)
        lines.append("```")
    else:
        lines.append(f"- pytest summary: `{summary}`")
    lines.append("")

    by_severity = {sev: [f for f in findings if f.severity == sev] for sev in _ORDER}
    # Sort findings within each severity for deterministic output
    for sev in _ORDER:
        by_severity[sev].sort(key=lambda f: (f.target or "", f.probe or ""))

    counts = ", ".join(f"{len(by_severity[sev])} {_LABELS[sev].lower()}" for sev in _ORDER)
    lines.append(f"## Findings ({counts})")
    lines.append("")

    if not findings:
        lines.append("No issues found by the current probe set.")
        return "\n".join(lines)

    for sev in _ORDER:
        group = by_severity[sev]
        if not group:
            continue
        lines.append(f"### {_LABELS[sev]}")
        for f in group:
            lines.append(f"- **`{f.target}`** — probe: `{f.probe}`")
            # Description is usually short; render inline.
            if f.description:
                lines.append(f"  - {f.description}")
            # Evidence and suggested_fix may be multi-line; fence them when appropriate.
            if f.evidence:
                fenced = _fence_if_multiline(f.evidence)
                if fenced.startswith("```"):
                    lines.append("  - Evidence:")
                    lines.append(f"")
                    for l in fenced.splitlines():
                        lines.append(f"    {l}")
                else:
                    lines.append(f"  - Evidence: {f.evidence}")
            if f.suggested_fix:
                fenced_fix = _fence_if_multiline(f.suggested_fix)
                if fenced_fix.startswith("```"):
                    lines.append("  - Suggested fix:")
                    lines.append("")
                    for l in fenced_fix.splitlines():
                        lines.append(f"    {l}")
                else:
                    lines.append(f"  - Suggested fix: {f.suggested_fix}")
        lines.append("")

    return "\n".join(lines)
