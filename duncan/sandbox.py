"""Isolation: a probe that tries to break something should never be able to
touch the real repo. Everything runs against a throwaway copy.
"""

from __future__ import annotations

import shutil
import tempfile
import warnings
import logging
from pathlib import Path
from typing import Optional, Callable

_IGNORE = shutil.ignore_patterns(
    ".git", "__pycache__", "*.pyc", ".pytest_cache", ".venv", "venv", "*.egg-info"
)

_log = logging.getLogger(__name__)


class Sandbox:
    """Context manager that creates a throwaway copy of a source tree.

    Usage:
        with Sandbox(source_root) as sandbox_path:
            # run risky actions against sandbox_path
        # sandbox removed unless keep=True

    By default symlinks are copied as symlinks (symlinks=True) so external
    files are not followed into the copy.
    """

    def __init__(self, source_root: Path, *, keep: bool = False, ignore: Optional[Callable] = None):
        self.source_root = Path(source_root)
        self.keep = keep
        self._ignore = ignore or _IGNORE
        self._tmp_parent: Optional[Path] = None
        self._dest: Optional[Path] = None

        if not self.source_root.exists():
            raise ValueError(f"source_root does not exist: {self.source_root!s}")
        if not self.source_root.is_dir():
            raise ValueError(f"source_root is not a directory: {self.source_root!s}")

    def __enter__(self) -> Path:
        self._tmp_parent = Path(tempfile.mkdtemp(prefix="duncan_"))
        self._dest = self._tmp_parent / self.source_root.name
        try:
            # Copy symlinks as symlinks. Do not follow symlinks that might
            # reference files outside the project.
            shutil.copytree(self.source_root, self._dest, ignore=self._ignore, symlinks=True)
        except Exception:
            # Clean up partial copy on failure.
            try:
                if self._tmp_parent and self._tmp_parent.exists():
                    shutil.rmtree(self._tmp_parent)
            except Exception:
                _log.exception("failed to remove incomplete sandbox %s", self._tmp_parent)
            raise
        _log.debug("created sandbox %s (parent %s)", self._dest, self._tmp_parent)
        return self._dest

    def __exit__(self, exc_type, exc, tb):
        if self.keep:
            _log.info("keeping sandbox %s (keep=True)", self._dest)
            return False
        if self._tmp_parent and self._tmp_parent.exists():
            try:
                shutil.rmtree(self._tmp_parent)
                _log.debug("removed sandbox parent %s", self._tmp_parent)
            except Exception:
                _log.exception("failed to remove sandbox %s", self._tmp_parent)

    @property
    def path(self) -> Path:
        if self._dest is None:
            raise RuntimeError("sandbox not yet created; use 'with Sandbox(...) as p'")
        return self._dest


def make_sandbox(source_root: Path) -> Path:
    """Backwards-compatible helper that returns a sandbox path but does NOT
    auto-clean it. Prefer using the Sandbox context manager.

    This emits a warning because callers that use this must remember to clean up.
    """
    warnings.warn(
        "make_sandbox() returns a sandbox without automatic cleanup; prefer 'with Sandbox(...) as p:'",
        DeprecationWarning,
        stacklevel=2,
    )
    tmp_parent = Path(tempfile.mkdtemp(prefix="duncan_"))
    dest = tmp_parent / Path(source_root).name
    shutil.copytree(source_root, dest, ignore=_IGNORE, symlinks=True)
    _log.debug("created non-auto-cleaning sandbox %s", dest)
    return dest
