# Duncan

An adversarial test runner. Point it at a Python project and it does two things:

1. Runs the project's own `pytest` suite as a baseline.
2. Goes looking for ways to break it that the project's own tests don't
   cover — right now, that means guardrails a class *appears* to enforce but
   doesn't actually, and where it's safe to construct an instance, it actually
   performs the bypass at runtime instead of just flagging a pattern.

It clones its own testing conventions from
[hotel_PMS_core](https://github.com/MutantSqr/hotel_PMS_core): an isolated,
deterministic run; behavior-named tests; rejection paths asserted with
`pytest.raises(..., match=...)`; small builder helpers instead of heavy
fixtures.

## Usage

```bash
pip install -r requirements.txt
python -m duncan /path/to/some/project
```

Writes `duncan_report_<project>.md` and prints it to stdout. Every probe run
happens against a throwaway copy of the target (`duncan/sandbox.py`) — the
original is never touched.

## What it currently checks: guard-ordering bypass

The pattern: a class enforces a rule inside a method —

```python
def finish(self) -> None:
    if self.status is not SessionStatus.RUNNING:
        raise ValueError(f"cannot finish a session that is {self.status.value}")
    self.status = SessionStatus.FINISHED
```

— but `status` is a plain public attribute. Nothing stops
`instance.status = SessionStatus.FINISHED` from skipping `finish()` entirely.
This is a real bug Duncan found and a real fix it verified: see
[Archimedes](https://github.com/MutantSqr/Archimedes-)'s `Session.status`/
`Session.plan`, which had exactly this problem until this tool caught it.

Detection is static (AST — `duncan/probes/state_guard_bypass.py`).
Verification is runtime where it's safe to construct an instance:

- **Dataclasses** — cheap and safe, always attempted.
- **Plain classes** — attempted via constructor introspection
  (`inspect.signature`), *unless* the constructor's own body references
  something risky (file I/O, network, subprocess, `eval`/`exec` — see
  `_RISKY_CALL_NAMES`), in which case it's left `SUSPECTED` rather than
  auto-built blind.

A finding that gets runtime-verified is `CONFIRMED`. A finding that matches
the static pattern but can't be safely verified (constructor needs args we
can't guess, or was risk-gated) is `SUSPECTED`. A finding that looked
suspicious statically but turned out to be properly protected at runtime
(the assignment actually raised) is downgraded to `INFO` — the probe catching
its own false positive.

## Known limitations, honestly

- **No type hints on a constructor parameter → we guess string.** If a class's
  `__init__` isn't annotated (`def __init__(self, room_number)` instead of
  `def __init__(self, room_number: int)`), the dummy value fed in is a plain
  string, which often fails the class's own validation and the whole
  construction attempt bails out — the finding stays `SUSPECTED` even though
  the bug is real. This is why `hotel_PMS_core`'s `Folio.charges`/`credits`/
  `payments` are still suspected rather than confirmed: `Folio.__init__` has
  no annotations at all.
- **The risk gate only scans `__init__`/`__post_init__` directly** — a
  constructor that calls a helper method which *then* does something risky
  won't be caught. It's a floor, not a guarantee.
- **Co-occurrence isn't causation.** The static detector flags any attribute
  referenced inside a guard condition, even if the raise isn't really about
  that attribute's own validity. `Archimedes`'s `AgentKernel.personality` gets
  flagged (and now runtime-confirmed as *settable*) because a guard method
  reads `self.personality.requires_clarification` before raising — but the
  raise is about blocking questions, not about personality being invalid.
  The mechanical claim ("this is publicly settable with no guard") is true;
  whether it's a meaningful finding is a judgment call, not always ours to
  make automatically.

## Adding a new probe

Every adversarial angle is a `Probe` subclass (`duncan/probes/base.py`) with
one method: `run(source_root: Path) -> List[Finding]`. Register it in
`duncan/cli.py`'s `PROBES` list. Nothing else needs to change — the runner
and report don't know or care how many probes exist.

Candidates for next: empty-string/boundary-value crash testing, duplicate
registration handling, provider/dependency exhaustion — the angles already
written up informally in Archimedes' own testing notes
(`.agents/skills/testing-archimedes/SKILL.md` on its `devin/update-skills-*`
branch), just not yet automated here.
