from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum


class Severity(str, Enum):
    CONFIRMED = "confirmed"
    SUSPECTED = "suspected"
    INFO = "info"


@dataclass(frozen=True)
class Finding:
    probe: str
    target: str
    severity: Severity
    description: str
    evidence: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data
