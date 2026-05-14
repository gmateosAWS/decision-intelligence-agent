"""
tests/scripts/test_memory_boundary_lint.py
------------------------------------------
Unit tests for scripts/check_memory_boundary.py (item 5.11).

No subprocess — the script's main() is imported and called directly so tests
are fast and work cross-platform without relying on a specific Python executable.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import scripts.check_memory_boundary as linter

# ── Helpers ───────────────────────────────────────────────────────────────────


def _fake_path(content: str, rel: str = "agents/fake_module.py") -> MagicMock:
    """Return a MagicMock that behaves like a Path with the given content."""
    p = MagicMock(spec=Path)
    p.relative_to.return_value = Path(rel)
    p.read_text.return_value = content
    return p


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_lint_passes_on_clean_repo() -> None:
    """Running the linter on the actual project root must return exit code 0.

    This is a lightweight smoke-check that the codebase never contains a
    forbidden direct import of memory internals outside the allowed packages.
    """
    result = linter.main()
    assert result == 0, "Memory boundary violations found — see stderr for details"


def test_lint_fails_on_forbidden_import() -> None:
    """A file containing 'from memory.coordinator import ...' must produce exit 1."""
    bad_file = _fake_path(
        "from memory.coordinator import MemoryCoordinator\n",
        rel="agents/bad_module.py",
    )

    with (
        patch.object(linter, "_files_to_check", return_value=[bad_file]),
        patch.object(linter, "_load_allowlist", return_value=set()),
    ):
        result = linter.main()

    assert result == 1


def test_lint_fails_on_forbidden_constructor() -> None:
    """Direct instantiation of MemoryCoordinator outside memory/ must produce exit 1."""
    bad_file = _fake_path(
        "coord = MemoryCoordinator(session_id=sid)\n",
        rel="agents/direct_construct.py",
    )

    with (
        patch.object(linter, "_files_to_check", return_value=[bad_file]),
        patch.object(linter, "_load_allowlist", return_value=set()),
    ):
        result = linter.main()

    assert result == 1


def test_lint_respects_allowlist() -> None:
    """A file listed in the governance allowlist must be skipped even if it has
    forbidden imports — the allowlist is the escape hatch for justified exceptions."""
    bad_file = _fake_path(
        "from memory.state import ActiveAnalyticalState\n",
        rel="agents/legacy_module.py",
    )

    with (
        patch.object(linter, "_files_to_check", return_value=[bad_file]),
        patch.object(
            linter, "_load_allowlist", return_value={"agents/legacy_module.py"}
        ),
    ):
        result = linter.main()

    assert result == 0


def test_lint_clean_file_passes() -> None:
    """A file that only uses the facade (from memory import ...) must not trigger."""
    clean_file = _fake_path(
        "from memory import get_memory_service\n\nsvc = get_memory_service()\n",
        rel="agents/clean_module.py",
    )

    with (
        patch.object(linter, "_files_to_check", return_value=[clean_file]),
        patch.object(linter, "_load_allowlist", return_value=set()),
    ):
        result = linter.main()

    assert result == 0
