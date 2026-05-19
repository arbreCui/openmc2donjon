from __future__ import annotations

import tempfile
import unittest

from openmc2donjon import lcm_ascii as lcm


class LcmAsciiTests(unittest.TestCase):
    def test_writer_reader_semantic_round_trip(self) -> None:
        blocks = [
            lcm.string_block(1, "SIGNATURE", "L_MULTICOMPO", width=12),
            lcm.block(1, "ROOT", 0, count=-1),
            lcm.list_item(2, 1),
            lcm.block(3, "PARCAD", 1, [1, 2, 3]),
            lcm.block(3, "VALUES", 2, [1.0, 2.5]),
            lcm.string_block(3, "COMMENT", "abc", width=8),
            lcm.list_placeholder(2, 2),
            lcm.control(-2),
            lcm.control(-1),
        ]
        text = lcm.format_lcm_ascii(blocks)
        parsed = lcm.parse_lcm_ascii_text(text)
        self.assertEqual(
            [b.semantic_tuple() for b in blocks],
            [b.semantic_tuple() for b in parsed],
        )

    def test_reads_unnamed_list_payload(self) -> None:
        text = "\n".join(
            [
                "->       1      12      10       1                                 <-   ",
                "FLUX                                                                            ",
                "->       2       0       2       3                                 <-   00000001",
                "  1.00000000E+00  2.00000000E+00  3.00000000E+00",
                "->      -1       0       0       0                                 <-   ",
            ]
        )

        blocks = lcm.parse_lcm_ascii_text(text)

        self.assertEqual(blocks[1].name, None)
        self.assertFalse(blocks[1].is_control)
        self.assertEqual(blocks[1].trailing, "00000001")
        self.assertEqual(blocks[1].data, (1.0, 2.0, 3.0))
        reread = lcm.parse_lcm_ascii_text(lcm.format_lcm_ascii(blocks))
        self.assertEqual(
            [b.semantic_tuple() for b in blocks],
            [b.semantic_tuple() for b in reread],
        )

    def test_reads_realistic_global_fragment(self) -> None:
        fragment = [
            "->       1      12       3       3                                 <-   ",
            "SIGNATURE                                                                       ",
            "         4         4         4",
            "L_MULTICOMPO",
            "->       1      12       0      -1                                 <-   ",
            "CPO                                                                             ",
            "->       2      12       0      -1                                 <-   ",
            "GLOBAL                                                                          ",
            "->       3      12       1       1                                 <-   ",
            "PARCAD                                                                          ",
            "         1",
            "->      -2       0       0       0                                 <-   ",
            "->       2       0       0      -1                                 <-   00000001",
            "->       3      12       2       2                                 <-   ",
            "VALUES                                                                          ",
            "  1.00000000E+00  2.00000000E+00",
            "->      -1       0       0       0                                 <-   ",
        ]
        blocks = lcm.parse_lcm_ascii_lines(fragment)
        names = [b.name for b in blocks if b.name]
        self.assertIn("GLOBAL", names)
        self.assertIn("PARCAD", names)
        self.assertTrue(any(b.trailing == "00000001" for b in blocks))

        with tempfile.TemporaryDirectory() as tmpdir:
            out = tempfile.NamedTemporaryFile(dir=tmpdir, suffix=".txt", delete=False)
            out.close()
            out_path = out.name
            lcm.write_lcm_ascii(blocks, out_path)
            reread = lcm.read_lcm_ascii(out_path)
        self.assertEqual(
            [b.semantic_tuple() for b in blocks],
            [b.semantic_tuple() for b in reread],
        )


if __name__ == "__main__":
    unittest.main()
