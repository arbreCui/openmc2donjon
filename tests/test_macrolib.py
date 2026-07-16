from __future__ import annotations

import unittest

import numpy as np

from openmc2donjon import lcm_ascii as lcm
from openmc2donjon.macrolib import (
    _limit_scatter_order,
    build_macrolib_blocks,
    derive_reference_kinf,
    parse_macrolib_blocks,
)
from openmc2donjon.multicompo import MixtureXS


class MacrolibParserTests(unittest.TestCase):
    def test_build_root_macrolib_round_trip(self) -> None:
        mixtures = [
            MixtureXS(
                name="fuel",
                total=np.array([0.5, 1.0]),
                absorption=np.array([0.05, 0.1]),
                fission=np.array([0.01, 0.02]),
                nu_fission=np.array([0.025, 0.05]),
                chi=np.array([1.0, 0.0]),
                scatter_matrix=np.array(
                    [
                        [
                            [0.10, 0.20],
                            [0.00, 0.70],
                        ],
                        [
                            [0.01, -0.02],
                            [0.03, 0.00],
                        ],
                    ]
                ),
                fissionable=True,
                volume=2.0,
                flux_weight=np.array([4.0, 5.0]),
                inverse_velocity=np.array([1.0e-8, 2.0e-6]),
                transport_total=np.array([0.25, 0.5]),
                h_factor=np.array([10.0, 20.0]),
                sph=np.array([1.10, 0.90]),
            ),
            MixtureXS(
                name="moderator",
                total=np.array([0.6, 1.2]),
                absorption=np.array([0.06, 0.12]),
                fission=np.array([0.0, 0.0]),
                nu_fission=np.array([0.0, 0.0]),
                chi=np.array([0.0, 0.0]),
                scatter_matrix=np.array(
                    [
                        [
                            [0.11, 0.00],
                            [0.22, 0.33],
                        ],
                        [
                            [0.04, 0.00],
                            [0.05, 0.06],
                        ],
                    ]
                ),
                fissionable=False,
                volume=3.0,
                flux_weight=np.array([6.0, 7.0]),
                transport_total=np.array([0.3, 0.6]),
                h_factor=np.array([30.0, 40.0]),
                sph=np.array([0.95, 1.05]),
            ),
        ]

        blocks = build_macrolib_blocks(
            mixtures,
            np.array([1.0e-5, 1.0, 1.0e7]),
            reference_keff=1.11234,
        )
        macrolib = parse_macrolib_blocks(blocks)

        self.assertEqual(blocks[0].name, "SIGNATURE")
        self.assertEqual(blocks[4].name, "GROUP")
        self.assertEqual(macrolib.state_vector[:4], (2, 2, 2, 1))
        self.assertEqual(macrolib.state_vector[8], 1)
        self.assertEqual(macrolib.state_vector[13], 1)
        self.assertEqual(macrolib.reference_keff, 1.11234)
        self.assertIsNone(macrolib.reference_kinf)
        np.testing.assert_allclose(macrolib.energy, [1.0e7, 1.0, 1.0e-5])
        np.testing.assert_allclose(macrolib.volume, [2.0, 3.0])
        np.testing.assert_allclose(macrolib.flux_intg, [[8.0, 10.0], [18.0, 21.0]])
        np.testing.assert_allclose(macrolib.ntot0, [[0.5, 1.0], [0.6, 1.2]])
        np.testing.assert_allclose(
            macrolib.diff,
            [[1.0 / 0.75, 1.0 / 1.5], [1.0 / 0.9, 1.0 / 1.8]],
        )
        np.testing.assert_allclose(macrolib.h_factor, [[10.0, 20.0], [30.0, 40.0]])
        np.testing.assert_allclose(macrolib.sph, [[1.10, 0.90], [0.95, 1.05]])
        np.testing.assert_allclose(macrolib.nusigf, [[0.025, 0.05], [0.0, 0.0]])
        np.testing.assert_allclose(macrolib.chi, [[1.0, 0.0], [0.0, 0.0]])
        np.testing.assert_allclose(
            macrolib.sigs[0],
            [[0.30, 0.70], [0.11, 0.55]],
        )
        np.testing.assert_allclose(macrolib.scatter[0][0], mixtures[0].scatter_matrix[0])
        np.testing.assert_allclose(macrolib.scatter[0][1], mixtures[1].scatter_matrix[0])
        np.testing.assert_allclose(macrolib.scatter[1][0], mixtures[0].scatter_matrix[1])
        np.testing.assert_allclose(macrolib.scatter[1][1], mixtures[1].scatter_matrix[1])

    def test_parses_solver_edition_without_energy_or_sigs_records(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 1.0]),
            absorption=np.array([0.05, 0.1]),
            fission=np.array([0.01, 0.02]),
            nu_fission=np.array([0.025, 0.05]),
            chi=np.array([1.0, 0.0]),
            scatter_matrix=np.array([[[0.10, 0.20], [0.0, 0.70]]]),
            fissionable=True,
            volume=2.0,
            flux_weight=np.array([4.0, 5.0]),
            transport_total=np.array([0.25, 0.5]),
        )
        blocks = [
            block
            for block in build_macrolib_blocks(
                [mixture],
                np.array([1.0e-5, 1.0, 1.0e7]),
            )
            if block.name not in {"ENERGY", "SIGS00"}
        ]

        macrolib = parse_macrolib_blocks(blocks)

        self.assertEqual(macrolib.energy.size, 0)
        np.testing.assert_allclose(macrolib.sigs[0], [[0.30, 0.70]])

    def test_parse_groupwise_scattering_triplets(self) -> None:
        state = [0] * 40
        state[:3] = [2, 2, 1]
        blocks = [
            lcm.string_block(1, "SIGNATURE", "L_MACROLIB", width=12),
            lcm.block(1, "STATE-VECTOR", 1, state),
            lcm.block(1, "ENERGY", 2, [10.0, 1.0, 0.1]),
            lcm.block(1, "VOLUME", 2, [1.0, 2.0]),
            lcm.block(1, "GROUP", 10, count=2),
            lcm.list_item(2, 1),
            lcm.block(3, "NTOT0", 2, [0.1, 0.2]),
            lcm.block(3, "DIFF", 2, [3.0, 4.0]),
            lcm.block(3, "H-FACTOR", 2, [7.0, 8.0]),
            lcm.block(3, "SIGS00", 2, [0.01, 0.02]),
            lcm.block(3, "SCAT00", 2, [0.11, 0.22, 0.12]),
            lcm.block(3, "NJJS00", 1, [1, 2]),
            lcm.block(3, "IJJS00", 1, [1, 2]),
            lcm.block(3, "IPOS00", 1, [1, 2]),
            lcm.block(3, "SIGS01", 2, [0.001, 0.002]),
            lcm.block(3, "SCAT01", 2, [0.011, 0.022, 0.012]),
            lcm.block(3, "NJJS01", 1, [1, 2]),
            lcm.block(3, "IJJS01", 1, [1, 2]),
            lcm.block(3, "IPOS01", 1, [1, 2]),
            lcm.control(-3),
            lcm.list_item(2, 2),
            lcm.block(3, "NTOT0", 2, [0.3, 0.4]),
            lcm.block(3, "DIFF", 2, [5.0, 6.0]),
            lcm.block(3, "H-FACTOR", 2, [9.0, 10.0]),
            lcm.block(3, "SIGS00", 2, [0.03, 0.04]),
            lcm.block(3, "SCAT00", 2, [0.21, 0.32]),
            lcm.block(3, "NJJS00", 1, [1, 1]),
            lcm.block(3, "IJJS00", 1, [2, 2]),
            lcm.block(3, "IPOS00", 1, [1, 2]),
            lcm.block(3, "SIGS01", 2, [0.003, 0.004]),
            lcm.block(3, "SCAT01", 2, [0.021, 0.032]),
            lcm.block(3, "NJJS01", 1, [1, 1]),
            lcm.block(3, "IJJS01", 1, [2, 2]),
            lcm.block(3, "IPOS01", 1, [1, 2]),
            lcm.control(-3),
            lcm.control(-1),
        ]

        macrolib = parse_macrolib_blocks(blocks)

        self.assertEqual(macrolib.state_vector[:3], (2, 2, 1))
        self.assertEqual(macrolib.adf, {})
        np.testing.assert_allclose(macrolib.ntot0, [[0.1, 0.3], [0.2, 0.4]])
        np.testing.assert_allclose(macrolib.h_factor, [[7.0, 9.0], [8.0, 10.0]])
        np.testing.assert_allclose(
            macrolib.scatter[0],
            [
                [[0.11, 0.0], [0.0, 0.21]],
                [[0.12, 0.0], [0.22, 0.32]],
            ],
        )
        np.testing.assert_allclose(
            macrolib.scatter[1],
            [
                [[0.011, 0.0], [0.0, 0.021]],
                [[0.012, 0.0], [0.022, 0.032]],
            ],
        )

    def test_parse_shifted_level_adf_payload(self) -> None:
        state = [0] * 40
        state[:3] = [2, 2, 1]
        packed_names, name_count = lcm.pack_fixed_strings(["FD_B", "FD_T"], 8)
        blocks = [
            lcm.string_block(3, "SIGNATURE", "L_MACROLIB", width=12),
            lcm.block(3, "STATE-VECTOR", 1, state),
            lcm.block(3, "ENERGY", 2, [10.0, 1.0, 0.1]),
            lcm.block(3, "VOLUME", 2, [1.0, 2.0]),
            lcm.block(3, "GROUP", 10, count=2),
            lcm.list_item(4, 1),
            lcm.block(5, "NTOT0", 2, [0.1, 0.2]),
            lcm.block(5, "DIFF", 2, [3.0, 4.0]),
            lcm.block(5, "SIGS00", 2, [0.01, 0.02]),
            lcm.block(5, "SCAT00", 2, [0.11, 0.22]),
            lcm.block(5, "NJJS00", 1, [1, 1]),
            lcm.block(5, "IJJS00", 1, [1, 1]),
            lcm.block(5, "IPOS00", 1, [1, 2]),
            lcm.control(-5),
            lcm.list_item(4, 2),
            lcm.block(5, "NTOT0", 2, [0.3, 0.4]),
            lcm.block(5, "DIFF", 2, [5.0, 6.0]),
            lcm.block(5, "SIGS00", 2, [0.03, 0.04]),
            lcm.block(5, "SCAT00", 2, [0.21, 0.32]),
            lcm.block(5, "NJJS00", 1, [1, 1]),
            lcm.block(5, "IJJS00", 1, [2, 2]),
            lcm.block(5, "IPOS00", 1, [1, 2]),
            lcm.control(-5),
            lcm.control(-3),
            lcm.block(3, "ADF", 0, count=-1),
            lcm.block(4, "NTYPE", 1, [2]),
            lcm.block(4, "HADF", 3, packed_names, count=name_count),
            lcm.block(4, "FD_B", 2, [11.0, 21.0, 12.0, 22.0]),
            lcm.block(4, "FD_T", 2, [31.0, 41.0, 32.0, 42.0]),
            lcm.control(-4),
            lcm.control(-3),
        ]

        macrolib = parse_macrolib_blocks(blocks)

        self.assertEqual(set(macrolib.adf), {"FD_B", "FD_T"})
        np.testing.assert_allclose(macrolib.adf["FD_B"], [[11.0, 12.0], [21.0, 22.0]])
        np.testing.assert_allclose(macrolib.adf["FD_T"], [[31.0, 32.0], [41.0, 42.0]])

    def test_rejects_descending_energy_bounds(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 1.0]),
            absorption=np.array([0.05, 0.1]),
            fission=np.array([0.01, 0.02]),
            nu_fission=np.array([0.025, 0.05]),
            chi=np.array([1.0, 0.0]),
            scatter_matrix=np.array([[[0.10, 0.20], [0.0, 0.70]]]),
            fissionable=True,
            volume=2.0,
            transport_total=np.array([0.25, 0.5]),
        )

        ascending = np.array([1.0e-5, 1.0, 1.0e7])
        descending = np.array([1.0e7, 1.0, 1.0e-5])

        # Ascending (canonical contract) still works.
        blocks = build_macrolib_blocks([mixture], ascending)
        macrolib = parse_macrolib_blocks(blocks)
        np.testing.assert_allclose(macrolib.energy, [1.0e7, 1.0, 1.0e-5])

        # Descending input raises instead of silently producing a wrong ENERGY
        # block and negative DELTAU.
        with self.assertRaisesRegex(ValueError, "ascending"):
            build_macrolib_blocks([mixture], descending)

    def test_does_not_invent_missing_reference_eigenvalues(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5]),
            absorption=np.array([0.05]),
            fission=np.array([0.01]),
            nu_fission=np.array([0.025]),
            chi=np.array([1.0]),
            scatter_matrix=np.array([[[0.10]]]),
            fissionable=True,
            volume=2.0,
            transport_total=np.array([0.25]),
        )

        blocks = build_macrolib_blocks([mixture], np.array([1.0e-5, 1.0e7]))
        macrolib = parse_macrolib_blocks(blocks)

        self.assertIsNone(macrolib.reference_keff)
        self.assertIsNone(macrolib.reference_kinf)
        self.assertFalse(any(block.name == "K-EFFECTIVE" for block in blocks))
        self.assertFalse(any(block.name == "K-INFINITY" for block in blocks))

    def test_projects_scattering_to_target_solver_order(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5]),
            absorption=np.array([0.05]),
            fission=np.array([0.01]),
            nu_fission=np.array([0.025]),
            chi=np.array([1.0]),
            scatter_matrix=np.array([[[0.10]], [[0.02]], [[-0.01]]]),
            fissionable=True,
        )

        projected = _limit_scatter_order([mixture], 0)

        self.assertEqual(projected[0].scatter_matrix.shape, (1, 1, 1))
        np.testing.assert_allclose(projected[0].scatter_matrix, [[[0.10]]])
        self.assertEqual(mixture.scatter_matrix.shape, (3, 1, 1))

    def test_derives_reference_kinf_from_integrated_rate_balance(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 0.8]),
            absorption=np.array([0.1, 0.2]),
            fission=np.array([0.02, 0.03]),
            nu_fission=np.array([0.05, 0.09]),
            chi=np.array([1.0, 0.0]),
            scatter_matrix=np.array([[[0.3, 0.1], [0.1, 0.5]]]),
            fissionable=True,
            volume=2.0,
            flux_weight=np.array([2.0, 3.0]),
        )

        kinf = derive_reference_kinf([mixture])

        flux_intg = np.array([4.0, 6.0])
        expected = np.dot(mixture.nu_fission, flux_intg) / (
            np.dot(mixture.total, flux_intg)
            - np.sum(mixture.scatter_matrix[0] * flux_intg[:, np.newaxis])
        )
        self.assertAlmostEqual(kinf, expected)


if __name__ == "__main__":
    unittest.main()
