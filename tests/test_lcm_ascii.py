from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from openmc2donjon import lcm_ascii as lcm


FIXTURE_DIR = Path(__file__).with_name("fixtures")


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

    def test_block_type_matrix_round_trip(self) -> None:
        long_text = (
            "LCM ASCII string payloads keep padding and can cross the "
            "eighty-character wire line boundary."
        )
        blocks = [
            lcm.block(1, "ROOT", 0, count=-1),
            lcm.block(2, "MIXTURES", 10, count=2),
            lcm.list_item(3, 1),
            lcm.block(4, "INTS", 1, [1, -2, 3, -4, 5, -6, 7, -8, 9]),
            lcm.block(
                4,
                "REALS",
                2,
                [1.0, -2.5, 3.125e-12, -4.25e6, 5.5, 6.75],
            ),
            lcm.string_block(4, "TEXT", long_text),
            lcm.list_item(3, 2),
            lcm.list_placeholder(4, 7),
            lcm.string_block(4, "ALIAS", "FUEL_A", width=8),
            lcm.control(-3),
            lcm.control(-2),
            lcm.control(-1),
        ]

        first_read = lcm.parse_lcm_ascii_text(lcm.format_lcm_ascii(blocks))
        second_read = lcm.parse_lcm_ascii_text(lcm.format_lcm_ascii(first_read))

        self.assertEqual(
            [block.semantic_tuple() for block in blocks],
            [block.semantic_tuple() for block in first_read],
        )
        self.assertEqual(
            [block.semantic_tuple() for block in first_read],
            [block.semantic_tuple() for block in second_read],
        )

    def test_parser_accepts_fortran_d_real_exponents(self) -> None:
        text = "\n".join(
            [
                "->       1      12       2       3                                 <-   ",
                "VALUES                                                                          ",
                "  1.25000000D+00 -2.50000000D-03  3.00000000E+02",
            ]
        )

        blocks = lcm.parse_lcm_ascii_text(text)

        self.assertEqual(blocks[0].data, (1.25, -2.5e-3, 300.0))
        reread = lcm.parse_lcm_ascii_text(lcm.format_lcm_ascii(blocks))
        self.assertEqual(blocks[0].semantic_tuple(), reread[0].semantic_tuple())

    def test_string_payload_padding_is_semantic(self) -> None:
        block = lcm.string_block(1, "COMMENT", "ABC", width=12)

        parsed = lcm.parse_lcm_ascii_text(lcm.format_lcm_ascii([block]))

        self.assertEqual(parsed[0].data, "ABC         ")
        self.assertEqual(block.semantic_tuple(), parsed[0].semantic_tuple())

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

    def test_pack_fixed_strings_rejects_truncation(self) -> None:
        packed, count = lcm.pack_fixed_strings(["ABCDEFGH", "FD_B"], 8)

        self.assertEqual(packed, "ABCDEFGHFD_B    ")
        self.assertEqual(count, 4)
        with self.assertRaisesRegex(ValueError, "longer than 8 characters"):
            lcm.pack_fixed_strings(["ABCDEFGHI"], 8)

    def test_string_block_rejects_implicit_truncation(self) -> None:
        with self.assertRaisesRegex(ValueError, "string block 'SIGNATURE'.*longer"):
            lcm.string_block(1, "SIGNATURE", "L_MULTICOMPO_EXTRA", width=12)

    def test_string_block_allows_explicit_truncation(self) -> None:
        block = lcm.string_block(1, "COMMENT", "abcdef", width=4, truncate=True)

        self.assertEqual(block.data, "abcd")
        self.assertEqual(block.count, 1)

    def test_rejects_bad_string_chunk_declaration(self) -> None:
        text = "\n".join(
            [
                "->       1      12       3       1                                 <-   ",
                "COMMENT                                                                         ",
                "         8",
                "ABCD",
            ]
        )

        with self.assertRaisesRegex(ValueError, "unsupported string chunk width"):
            lcm.parse_lcm_ascii_text(text)

    def test_format_rejects_string_payload_count_mismatch(self) -> None:
        block = lcm.LcmBlock(
            1,
            12,
            3,
            2,
            name="COMMENT",
            data="ABCD",
        )

        with self.assertRaisesRegex(ValueError, "expected 8"):
            lcm.format_lcm_ascii([block])

    def test_rejects_overlong_block_name(self) -> None:
        name = "X" * 81

        with self.assertRaisesRegex(ValueError, "LCM block name .* longer than 80"):
            lcm.block(1, name, 1, [1])
        with self.assertRaisesRegex(ValueError, "LCM block name .* longer than 80"):
            lcm.format_lcm_ascii([lcm.LcmBlock(1, 12, 0, -1, name=name)])

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

    def test_real_donjon_scattering_fragment_semantic_round_trip(self) -> None:
        fixture = FIXTURE_DIR / "donjon_multicompo_scattering_fragment.txt"

        blocks = lcm.read_lcm_ascii(fixture)
        reread = lcm.parse_lcm_ascii_text(lcm.format_lcm_ascii(blocks))

        self.assertEqual(
            [block.semantic_tuple() for block in blocks],
            [block.semantic_tuple() for block in reread],
        )
        by_name = {block.name: block for block in blocks if block.name}
        self.assertEqual(by_name["STATE-VECTOR"].data[:4], (2, 2, 3, 10))
        self.assertEqual(by_name["MIXTURES"].type_code, 10)
        self.assertEqual(by_name["MIXTURES"].count, 2)
        self.assertEqual(by_name["CALCULATIONS"].count, 10)
        self.assertEqual(by_name["ISOTOPESLIST"].count, 1)
        self.assertEqual(by_name["NJJS00"].data, (1, 2))
        self.assertEqual(by_name["IJJS00"].data, (1, 2))
        self.assertEqual(by_name["SCAT00"].count, 3)
        self.assertEqual(by_name["SCAT-SAVED"].data, (1,))
        self.assertEqual(
            [block.trailing for block in blocks if block.trailing],
            ["00000001", "00000001", "00000001"],
        )


if __name__ == "__main__":
    unittest.main()
