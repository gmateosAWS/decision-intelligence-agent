"""
scripts/check_memory_boundary.py
────────────────────────────────
Boundary lint for the memory subsystem (item 5.11).

Rules enforced:
  1. Outside memory/, imports from memory.coordinator.* and memory.state.*
     are forbidden. Allowed: `from memory import ...` (facade) and
     `from core.protocols.memory import ...` (contract).
  2. Outside memory/, constructing ActiveAnalyticalState or MemoryCoordinator
     directly is forbidden — use the MemoryService Protocol.
  3. Exceptions live in governance/memory_boundary_exceptions.yaml.
     The lint ratchets — entries are removed as code is cleaned up.

Excluded from scanning:
  memory/     — implementation; owns these imports legitimately
  tests/      — test helpers may reference internals via pytest fixtures
  core/       — protocol definitions reference memory types for signatures
  scripts/    — this file itself contains the forbidden patterns as strings
  .venv/, venv/, build/, .git/, __pycache__

Exits with code 1 if any violation is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable, Set

ROOT = Path(__file__).resolve().parent.parent

_FORBIDDEN_IMPORTS = [
    r"from memory\.coordinator",
    r"from memory\.state",
    r"import memory\.coordinator",
    r"import memory\.state",
]

_FORBIDDEN_CONSTRUCTORS = [
    r"ActiveAnalyticalState\s*\(",
    r"MemoryCoordinator\s*\(",
]

_ALL_PATTERNS = _FORBIDDEN_IMPORTS + _FORBIDDEN_CONSTRUCTORS

_EXCLUDED_ROOTS = {
    "memory",
    "tests",
    "core",
    "scripts",
    ".venv",
    "venv",
    "build",
    ".git",
}


def _files_to_check() -> Iterable[Path]:
    for p in ROOT.rglob("*.py"):
        parts = p.relative_to(ROOT).parts
        if not parts:
            continue
        if parts[0] in _EXCLUDED_ROOTS:
            continue
        if "__pycache__" in parts:
            continue
        yield p


def _load_allowlist() -> Set[str]:
    allow_file = ROOT / "governance" / "memory_boundary_exceptions.yaml"
    if not allow_file.exists():
        return set()
    allowed: Set[str] = set()
    for line in allow_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- file:"):
            allowed.add(line.split(":", 1)[1].strip())
    return allowed


def main() -> int:
    allowlist = _load_allowlist()
    violations: list[str] = []
    files_checked = 0

    for path in _files_to_check():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        if rel in allowlist:
            continue
        files_checked += 1
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in _ALL_PATTERNS:
            for match in re.finditer(pattern, content):
                line_no = content[: match.start()].count("\n") + 1
                violations.append(f"{rel}:{line_no}: forbidden — {match.group()!r}")

    if violations:
        print("Memory boundary violations:", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nMemory subsystem must be accessed only via the MemoryService Protocol.\n"
            "Import from `memory` (facade) or `core.protocols.memory` (contract).\n"
            "See docs/tech_debt.md and docs/audit/ for the rationale.\n"
            "To add a justified exception: governance/memory_boundary_exceptions.yaml",
            file=sys.stderr,
        )
        return 1

    print(
        f"Memory boundary lint: clean ({files_checked} files checked).",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
