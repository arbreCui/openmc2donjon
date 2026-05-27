"""Audit that ``print()`` calls outside render helpers stay on the whitelist.

The output contract for openmc2donjon (see ``openmc2donjon._logging``) is:

- ``print()`` is for results: rendered reports, paths, summaries, and the
  one-line artifact confirmations the user invoked the command to receive.
- ``logging`` is for diagnostics: errors, progress, fallbacks, debug.

Most ``print()`` calls already live inside a ``print_*`` / ``render_*`` /
``format_*`` helper or in a dedicated report module; those are allowed
automatically. The remaining handful are deliberate "I wrote/exported/
injected X" confirmations in regular CLI handlers - they are enumerated
explicitly in ``ALLOWED_RESULT_PRINTS`` below.

If this test fails, you have three choices, in order of preference:

1. Move the ``print()`` into an existing or new ``print_*`` /
   ``render_*`` / ``format_*`` helper.
2. Replace it with a ``logger.{info, warning, error}`` call obtained
   from ``openmc2donjon._logging.get_logger``.
3. If the call really is a deliberate one-line artifact confirmation
   with no natural render helper, add an entry to
   ``ALLOWED_RESULT_PRINTS`` and explain in your commit message why.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "openmc2donjon"

# Function-name prefixes that mark a "render a Report to stdout" helper.
# Every ``print()`` inside such a function is treated as a result.
RENDER_PREFIXES = (
    "print_",
    "_print_",
    "render_",
    "_render_",
    "format_",
    "_format_",
)

# Modules whose entire job is to render Reports to stdout. Every print()
# inside them is a result, regardless of containing function name.
REPORT_MODULES = frozenset(
    {
        "mgxs_input_report",
        "recipe_dry_run_report",
    }
)

# Explicit whitelist of ``(module, function)`` sites that may call
# ``print()`` outside a render helper because the call is a one-line
# artifact confirmation. Each entry is deliberate.
ALLOWED_RESULT_PRINTS: frozenset[tuple[str, str]] = frozenset(
    {
        ("export_cli", "main"),
        ("from_openmc_adf", "inject_adf"),
        ("from_openmc_cli", "_convert_pipeline_hdf5"),
        ("from_openmc_cli", "_export_pipeline_hdf5"),
        ("from_openmc_cli", "_run_dry_run"),
        ("from_openmc_cli", "_run_pipeline_preflight"),
        ("from_openmc_cli", "_write_pipeline_summary"),
        ("from_openmc_run_dir", "finalize_run_dir"),
        ("from_openmc_sph", "_inject_sph"),
        ("mgxs_inspect", "inspect_files"),
    }
)


def _module_name(path: Path) -> str:
    rel = path.relative_to(PACKAGE_ROOT)
    return ".".join(rel.with_suffix("").parts)


class _PrintVisitor(ast.NodeVisitor):
    """Collect ``(innermost_function_name, lineno)`` for each ``print()`` call."""

    def __init__(self) -> None:
        self._fn_stack: list[str] = []
        self.calls: list[tuple[str | None, int]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._fn_stack.append(node.name)
        self.generic_visit(node)
        self._fn_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "print":
            owner = self._fn_stack[-1] if self._fn_stack else None
            self.calls.append((owner, node.lineno))
        self.generic_visit(node)


def _collect_unexpected_prints() -> list[str]:
    unexpected: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if path.name == "_logging.py":
            continue
        module = _module_name(path)
        if module in REPORT_MODULES:
            continue
        visitor = _PrintVisitor()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        for owner, lineno in visitor.calls:
            if owner is None:
                unexpected.append(f"{path}:{lineno} module-level print()")
                continue
            if owner.startswith(RENDER_PREFIXES):
                continue
            if (module, owner) in ALLOWED_RESULT_PRINTS:
                continue
            unexpected.append(f"{path}:{lineno} in {module}.{owner}()")
    return unexpected


class PrintAuditTests(unittest.TestCase):
    def test_no_unexpected_prints_outside_render_helpers(self) -> None:
        unexpected = _collect_unexpected_prints()
        if unexpected:
            self.fail(
                "Unexpected print() calls outside the documented result-"
                "rendering contract (see openmc2donjon._logging). Either "
                "move the call into a print_*/render_*/format_* helper, "
                "replace it with a logger.{info,warning,error} call from "
                "openmc2donjon._logging.get_logger, or - if it really is "
                "a deliberate artifact confirmation - add an entry to "
                "ALLOWED_RESULT_PRINTS in this test.\n  "
                + "\n  ".join(unexpected)
            )

    def test_whitelist_entries_all_correspond_to_real_sites(self) -> None:
        """A whitelist entry that no longer matches code is dead weight; flag it."""

        observed: set[tuple[str, str]] = set()
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            if path.name == "_logging.py":
                continue
            module = _module_name(path)
            if module in REPORT_MODULES:
                continue
            visitor = _PrintVisitor()
            visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
            for owner, _lineno in visitor.calls:
                if owner is None or owner.startswith(RENDER_PREFIXES):
                    continue
                observed.add((module, owner))

        stale = sorted(ALLOWED_RESULT_PRINTS - observed)
        self.assertFalse(
            stale,
            "ALLOWED_RESULT_PRINTS contains entries that no longer match any "
            "print() in the source tree; remove them:\n  "
            + "\n  ".join(f"{m}.{owner}" for m, owner in stale),
        )


if __name__ == "__main__":
    unittest.main()
