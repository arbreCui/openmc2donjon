from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openmc2donjon import lcm_ascii as lcm
from openmc2donjon.cli import build_command_parser, main as cli_main
from openmc2donjon.writer_compare import (
    _blocks_to_tree,
    _compare_nodes,
    _CompareState,
)


class WriterCompareTests(unittest.TestCase):
    def test_semantic_tree_comparison_ignores_table_order_and_tolerates_float32(self) -> None:
        ascii_blocks = [
            lcm.string_block(1, "SIGNATURE", "L_TEST", width=8),
            lcm.block(1, "ROOT", 0, count=-1),
            lcm.block(2, "A", 1, [1, 2]),
            lcm.block(2, "B", 2, [0.1, 0.2]),
            lcm.block(2, "ITEMS", 10, count=1),
            lcm.list_item(3, 1),
            lcm.string_block(4, "NAME", "X", width=4),
            lcm.control(-2),
            lcm.control(-1),
        ]
        pygan_blocks = [
            lcm.block(1, "ROOT", 0, count=-1),
            lcm.block(2, "ITEMS", 10, count=1),
            lcm.list_item(3, 1),
            lcm.string_block(4, "NAME", "X", width=4),
            lcm.block(2, "B", 2, [0.10000000149, 0.20000000298]),
            lcm.block(2, "A", 1, [1, 2]),
            lcm.control(-2),
            lcm.string_block(1, "SIGNATURE", "L_TEST", width=8),
        ]
        state = _CompareState(issues=[])

        _compare_nodes(
            _blocks_to_tree(ascii_blocks),
            _blocks_to_tree(pygan_blocks),
            path="/",
            state=state,
            rtol=1.0e-6,
            atol=1.0e-8,
        )

        self.assertEqual(state.issues, [])
        self.assertEqual(state.compared_payloads, 4)
        self.assertEqual(state.compared_real_payloads, 1)
        self.assertGreater(state.max_abs_diff, 0.0)

    def test_semantic_tree_comparison_reports_real_mismatch(self) -> None:
        state = _CompareState(issues=[])

        _compare_nodes(
            _blocks_to_tree([lcm.block(1, "X", 2, [1.0])]),
            _blocks_to_tree([lcm.block(1, "X", 2, [2.0])]),
            path="/",
            state=state,
            rtol=1.0e-6,
            atol=1.0e-8,
        )

        self.assertEqual(len(state.issues), 1)
        self.assertIn("real payload differs", state.issues[0].message)

    def test_compare_writers_command_uses_summary_json(self) -> None:
        def fake_compare(*args: object, **kwargs: object):
            summary_json = kwargs.get("summary_json")
            from openmc2donjon.writer_compare import WriterComparisonReport

            report = WriterComparisonReport(
                input_h5="input.h5",
                output_format="multicompo",
                ok=True,
                rtol=1.0e-6,
                atol=1.0e-8,
                compared_payloads=2,
                compared_real_payloads=1,
                max_abs_diff=0.0,
                max_rel_diff=0.0,
                issues=(),
            )
            if summary_json is not None:
                Path(summary_json).write_text(
                    json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            return report

        with tempfile.TemporaryDirectory() as tmpdir:
            summary = Path(tmpdir) / "compare.json"
            stream = io.StringIO()
            with patch(
                "openmc2donjon.commands.diagnostics.compare_writer_backends",
                side_effect=fake_compare,
            ):
                with contextlib.redirect_stdout(stream):
                    rc = cli_main(
                        [
                            "compare-writers",
                            "input.h5",
                            "--summary-json",
                            str(summary),
                        ]
                    )
            payload = json.loads(summary.read_text(encoding="utf-8"))

        self.assertEqual(rc, 0)
        self.assertIn("writer backend comparison", stream.getvalue())
        self.assertEqual(payload["schema"], "openmc2donjon.writer-comparison.v1")
        self.assertTrue(payload["ok"])

    def test_compare_writers_command_is_registered(self) -> None:
        args = build_command_parser().parse_args(["compare-writers", "input.h5"])

        self.assertEqual(args.command, "compare-writers")


if __name__ == "__main__":
    unittest.main()
