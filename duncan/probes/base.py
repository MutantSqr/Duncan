from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from duncan.findings import Finding


class Probe(ABC):
    @abstractmethod
    def run(self, source_root: Path) -> list[Finding]:
        raise NotImplementedError
