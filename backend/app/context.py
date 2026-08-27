"""Analysis context — explicit state threaded between modules.

This replaces the notebook's shared namespace: instead of variables leaking
between cells, each module receives a Context, reads what it needs, and writes
its results back (dataframes into `frames`, selector option-lists into
`options`). Modules stay independently testable.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd


class InputValidationError(ValueError):
    """Raised when a user input fails validation; surfaced to the UI as HTTP 400."""


Level = Literal["error", "warning", "info", "success"]

# symbol + ANSI colour per level, for the command-line box.
_STYLE: dict[str, tuple[str, str]] = {
    "error":   ("✕", "\033[31m"),
    "warning": ("⚠", "\033[33m"),
    "info":    ("ℹ", "\033[36m"),
    "success": ("✓", "\033[32m"),
}


def _print_box(entry: dict) -> None:
    """Print a single clean, boxed notice to stderr."""
    sym, color = _STYLE.get(entry["level"], ("•", ""))
    reset = "\033[0m" if color else ""
    wf = f" · {entry['workflow']}" if entry.get("workflow") else ""
    lines = [f"{sym} {entry['level'].upper()}{wf}", entry["message"]]
    width = max(len(x) for x in lines)
    top = f"┌─{'─' * width}─┐"
    bot = f"└─{'─' * width}─┘"
    body = "\n".join(f"│ {x.ljust(width)} │" for x in lines)
    print(f"\n{color}{top}\n{body}\n{bot}{reset}\n", file=sys.stderr)


@dataclass
class Context:
    excel_path: str
    params: dict[str, Any]
    frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)  # display tables, JSON-safe
    charts: dict[str, str] = field(default_factory=dict)   # name -> PNG data URI
    exports: dict[str, Any] = field(default_factory=dict)  # dicts/frames bound for Excel export
    messages: list[dict] = field(default_factory=list)     # user-facing notices (UI + CLI)

    def notify(self, message: str, level: Level = "error", workflow: str | None = None) -> None:
        """Record a user-facing notice and print it as a clean box on the CLI.

        Surfaces in the frontend (as a message box) and the terminal. Use from any
        workflow, e.g. `ctx.notify("No topsoil rows found", "warning", "borehole")`.
        """
        entry = {"level": level, "workflow": workflow, "message": str(message)}
        self.messages.append(entry)
        _print_box(entry)
