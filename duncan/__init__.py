"""Duncan: an adversarial test runner that clones a shared testing convention
(frozen clock, builder helpers, message-matched rejection paths — the pattern
proven across hotel_PMS_core and Archimedes) and adds one more layer: probes
that go looking for guardrails a project *thinks* it has but doesn't actually
enforce, and verify the bypass at runtime instead of just flagging a pattern.
"""

__version__ = "0.2.0"
