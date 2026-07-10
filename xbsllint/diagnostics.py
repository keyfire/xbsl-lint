"""The linter's diagnostic model."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Severity(enum.Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Diagnostic:
    """A single linter diagnostic, anchored to a position in a file.

    Line and column are 1-based (as in editors and compiler output).
    """

    path: str
    line: int
    col: int
    rule_id: str
    severity: Severity
    message: str

    def format(self) -> str:
        # A click-to-jump friendly format: path:line:col
        return f"{self.path}:{self.line}:{self.col}: {self.severity.value}: [{self.rule_id}] {self.message}"

    # Sort diagnostics by where they occur
    def sort_key(self) -> tuple:
        return (self.path, self.line, self.col, self.rule_id)
