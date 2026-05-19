from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from openmc2donjon import lcm_ascii as lcm
from openmc2donjon.multicompo import (
    MixtureHistory,
    MixtureXS,
    _select_mixtures,
    build_multicompo_history_blocks,
    build_multicompo_blocks,
    read_mgxs_hdf5,
    write_multicompo,
)


class MultiCompoSmokeTests(unittest.TestCase):
    def test_minimal_multicompo_round_trip(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 1.0]),
            absorption=np.array([0.05, 0.1]),
            fission=np.array([0.01, 0.02]),
            nu_fission=np.array([0.025, 0.05]),
            chi=np.array([1.0, 0.0]),
            scatter_matrix=np.array(
                [
                    [
                        [0.1, 0.2],
                        [0.0, 0.7],
                    ]
                ]
            ),
            fissionable=True,
        )
        energy_bounds = np.array([1.0e-5, 1.0, 1.0e7])

        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.mcompo.txt"
            write_multicompo([mixture], energy_bounds, out, comment="unit smoke")
            blocks = lcm.read_lcm_ascii(out)

        by_name = {}
        for block in blocks:
            if block.name and block.name not in by_name:
                by_name[block.name] = block

        self.assertEqual(by_name["SIGNATURE"].data, "L_MULTICOMPO")
        self.assertEqual(blocks[1].name, "CPO")
        self.assertEqual(by_name["COMMENT"].count, 20)
        self.assertEqual(len(by_name["COMMENT"].data), 80)
        self.assertEqual(by_name["STATE-VECTOR"].data[:4], (1, 2, 1, 1))
        self.assertEqual(by_name["PARCAD"].data, (1,))
        self.assertEqual(by_name["PARPAD"].data, (1,))
        self.assertEqual(by_name["ENERGY"].data, (1.0e7, 1.0, 1.0e-5))
        self.assertEqual(by_name["NVP"].data, (1, 20))
        self.assertEqual(by_name["DEBARB"].data, (2, 1))
        self.assertEqual(by_name["NJJS00"].data, (1, 2))
        self.assertEqual(by_name["IJJS00"].data, (1, 2))
        self.assertEqual(by_name["SCAT-SAVED"].data, (1,))

    def test_writes_optional_single_burnup_axis(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5]),
            absorption=np.array([0.05]),
            fission=np.array([0.0]),
            nu_fission=np.array([0.0]),
            chi=np.array([0.0]),
            scatter_matrix=np.array([[[0.1]]]),
            fissionable=False,
        )

        blocks = build_multicompo_blocks(
            [mixture],
            np.array([1.0e-5, 1.0e7]),
            root_name="CPO",
            comment="burnup smoke",
            burnup=0.0,
        )
        by_name = {block.name: block for block in blocks if block.name}
        cpo_state = [
            block for block in blocks if block.name == "STATE-VECTOR" and block.level == 2
        ][0]

        self.assertEqual(cpo_state.data[4], 1)
        self.assertEqual(lcm.unpack_fixed_strings(by_name["PARKEY"].data, 12), ["BURN        "])
        self.assertEqual(lcm.unpack_fixed_strings(by_name["PARTYP"].data, 4), ["VALU"])
        self.assertEqual(lcm.unpack_fixed_strings(by_name["PARFMT"].data, 8), ["REAL    "])
        self.assertEqual(by_name["PARCAD"].data, (1, 1))
        self.assertEqual(by_name["PARPAD"].data, (1, 1))
        self.assertEqual(by_name["pval00000001"].data, (0.0,))
        self.assertEqual(by_name["NVALUE"].data, (1,))

    def test_writes_burnup_axis_with_multiple_calculations(self) -> None:
        calc0 = MixtureXS(
            name="fuel",
            total=np.array([0.5, 1.0]),
            absorption=np.array([0.05, 0.1]),
            fission=np.array([0.01, 0.02]),
            nu_fission=np.array([0.025, 0.05]),
            chi=np.array([1.0, 0.0]),
            scatter_matrix=np.array([[[0.1, 0.2], [0.0, 0.7]]]),
            fissionable=True,
        )
        calc1 = MixtureXS(
            name="fuel",
            total=np.array([0.55, 1.05]),
            absorption=np.array([0.055, 0.105]),
            fission=np.array([0.011, 0.021]),
            nu_fission=np.array([0.026, 0.051]),
            chi=np.array([0.98, 0.02]),
            scatter_matrix=np.array([[[0.11, 0.21], [0.01, 0.71]]]),
            fissionable=True,
        )

        blocks = build_multicompo_history_blocks(
            [MixtureHistory(name="fuel", calculations=[calc0, calc1])],
            np.array([1.0e-5, 1.0, 1.0e7]),
            root_name="CPO",
            comment="multi burnup smoke",
            burnup_values=[0.0, 10.0],
        )
        by_name = {block.name: block for block in blocks if block.name}
        cpo_state = [
            block for block in blocks if block.name == "STATE-VECTOR" and block.level == 2
        ][0]
        ntot_blocks = [block for block in blocks if block.name == "NTOT0"]
        tree_nvp = [block for block in blocks if block.name == "NVP" and block.level == 5][0]
        tree_ncals = [block for block in blocks if block.name == "NCALS" and block.level == 5][0]
        tree_debarb = [block for block in blocks if block.name == "DEBARB" and block.level == 5][0]
        tree_arbval = [block for block in blocks if block.name == "ARBVAL" and block.level == 5][0]

        self.assertEqual(cpo_state.data[:5], (1, 2, 2, 2, 1))
        self.assertEqual(by_name["NVALUE"].data, (2,))
        self.assertEqual(by_name["pval00000001"].data, (0.0, 10.0))
        self.assertEqual(tree_nvp.data, (3, 20))
        self.assertEqual(tree_ncals.data, (2,))
        self.assertEqual(tree_debarb.data, (2, 4, 1, 2))
        self.assertEqual(tree_arbval.data, (0, 1, 2))
        self.assertEqual(len(ntot_blocks), 2)
        self.assertEqual(ntot_blocks[0].data, (0.5, 1.0))
        self.assertEqual(ntot_blocks[1].data, (0.55, 1.05))

    def test_converts_multistate_hdf5_burnup_axis(self) -> None:
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "multi.h5"
            output_path = Path(tmpdir) / "multi.mcompo.txt"
            with h5py.File(input_path, "w") as h5:
                h5.attrs["energy_groups"] = 1
                h5.attrs["legendre_order"] = 0
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0e7])
                state_points = h5.create_group("state_points")
                state_points.create_dataset("BURN", data=[0.0, 5.0])
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = True
                fuel.attrs["scatter_axes"] = "moment,from,to"
                states = fuel.create_group("states")
                for idx, total in enumerate((0.5, 0.6), start=1):
                    state = states.create_group(f"{idx:08d}")
                    state.create_dataset("total", data=[total])
                    state.create_dataset("absorption", data=[0.05])
                    state.create_dataset("fission", data=[0.01])
                    state.create_dataset("nu_fission", data=[0.025])
                    state.create_dataset("chi", data=[1.0])
                    state.create_dataset("scatter_matrix", data=[[[0.1]]])

            from openmc2donjon.multicompo import convert_mgxs_hdf5

            convert_mgxs_hdf5(input_path, output_path)
            blocks = lcm.read_lcm_ascii(output_path)

        by_name = {block.name: block for block in blocks if block.name}
        ntot_blocks = [block for block in blocks if block.name == "NTOT0"]
        cpo_state = [
            block for block in blocks if block.name == "STATE-VECTOR" and block.level == 2
        ][0]

        self.assertEqual(cpo_state.data[:5], (1, 1, 2, 2, 1))
        self.assertEqual(by_name["pval00000001"].data, (0.0, 5.0))
        self.assertEqual([block.data for block in ntot_blocks], [(0.5,), (0.6,)])

    def test_rejects_unsupported_multistate_axis(self) -> None:
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "multi.h5"
            output_path = Path(tmpdir) / "multi.mcompo.txt"
            with h5py.File(input_path, "w") as h5:
                h5.attrs["energy_groups"] = 1
                h5.attrs["legendre_order"] = 0
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0e7])
                state_points = h5.create_group("state_points")
                state_points.create_dataset("BURN", data=[0.0, 5.0])
                state_points.create_dataset("BORON", data=[500.0, 600.0])
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = True
                fuel.attrs["scatter_axes"] = "moment,from,to"
                states = fuel.create_group("states")
                for idx, total in enumerate((0.5, 0.6), start=1):
                    state = states.create_group(f"{idx:08d}")
                    state.create_dataset("total", data=[total])
                    state.create_dataset("absorption", data=[0.05])
                    state.create_dataset("fission", data=[0.01])
                    state.create_dataset("nu_fission", data=[0.025])
                    state.create_dataset("chi", data=[1.0])
                    state.create_dataset("scatter_matrix", data=[[[0.1]]])

            from openmc2donjon.multicompo import convert_mgxs_hdf5

            with self.assertRaisesRegex(ValueError, "only BURN is supported"):
                convert_mgxs_hdf5(input_path, output_path)

    def test_select_mixtures_by_name(self) -> None:
        mixtures = [
            MixtureXS(
                name=name,
                total=np.array([0.5]),
                absorption=np.array([0.05]),
                fission=np.array([0.0]),
                nu_fission=np.array([0.0]),
                chi=np.array([0.0]),
                scatter_matrix=np.array([[[0.1]]]),
                fissionable=False,
            )
            for name in ("a", "b", "c")
        ]

        selected = _select_mixtures(mixtures, ["c", "a"])

        self.assertEqual([mix.name for mix in selected], ["c", "a"])
        with self.assertRaisesRegex(ValueError, "unknown mixture"):
            _select_mixtures(mixtures, ["missing"])

    def test_writes_optional_h_factor(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 0.6]),
            absorption=np.array([0.05, 0.06]),
            fission=np.array([0.01, 0.02]),
            nu_fission=np.array([0.025, 0.05]),
            chi=np.array([1.0, 0.0]),
            scatter_matrix=np.array([[[0.1, 0.2], [0.0, 0.3]]]),
            fissionable=True,
            h_factor=np.array([10.0, 20.0]),
        )

        blocks = build_multicompo_blocks(
            [mixture],
            np.array([1.0e-5, 1.0, 1.0e7]),
            root_name="CPO",
            comment="h-factor smoke",
        )
        by_name = {block.name: block for block in blocks if block.name}

        self.assertEqual(by_name["H-FACTOR"].data, (10.0, 20.0))

    def test_reads_inverse_velocity_from_hdf5(self) -> None:
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0
                h5.create_dataset("energy_bounds", data=np.array([1.0e-5, 1.0, 1.0e7]))
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = True
                fuel.create_dataset("total", data=np.array([0.5, 1.0]))
                fuel.create_dataset("absorption", data=np.array([0.05, 0.1]))
                fuel.create_dataset("fission", data=np.array([0.01, 0.02]))
                fuel.create_dataset("nu_fission", data=np.array([0.025, 0.05]))
                fuel.create_dataset("chi", data=np.array([1.0, 0.0]))
                fuel.create_dataset("inverse_velocity", data=np.array([1.0e-8, 2.0e-6]))
                fuel.create_dataset(
                    "scatter_matrix",
                    data=np.array([[[0.1, 0.2], [0.0, 0.7]]]),
                )

            mixtures, _ = read_mgxs_hdf5(path)

        np.testing.assert_allclose(mixtures[0].inverse_velocity, [1.0e-8, 2.0e-6])

    def test_nonfissionable_mixture_ignores_fission_noise(self) -> None:
        mixture = MixtureXS(
            name="moderator",
            total=np.array([0.5]),
            absorption=np.array([0.01]),
            fission=np.array([1.0e-5]),
            nu_fission=np.array([2.0e-5]),
            chi=np.array([1.0]),
            scatter_matrix=np.array([[[0.45]]]),
            fissionable=False,
        )

        blocks = build_multicompo_blocks(
            [mixture],
            np.array([1.0e-5, 1.0e7]),
            root_name="CPO",
            comment="noise guard",
        )

        self.assertNotIn("NUSIGF", {block.name for block in blocks if block.name})

    def test_writes_multiple_legendre_moments(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 1.0]),
            absorption=np.array([0.05, 0.1]),
            fission=np.array([0.0, 0.0]),
            nu_fission=np.array([0.0, 0.0]),
            chi=np.array([0.0, 0.0]),
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
            fissionable=False,
        )

        blocks = build_multicompo_blocks(
            [mixture],
            np.array([1.0e-5, 1.0, 1.0e7]),
            root_name="CPO",
            comment="p1 smoke",
        )
        by_name = {block.name: block for block in blocks if block.name}
        library_state = [
            block for block in blocks if block.name == "STATE-VECTOR" and block.level == 6
        ][0]

        self.assertEqual(library_state.data[3], 2)
        self.assertEqual(by_name["SCAT-SAVED"].data, (1, 1))
        self.assertEqual(by_name["SIGS01"].data, (-0.01, 0.03))
        self.assertEqual(by_name["NJJS01"].data, (2, 1))
        self.assertEqual(by_name["IJJS01"].data, (2, 1))
        np.testing.assert_allclose(by_name["SCAT01"].data, (0.03, 0.01, -0.02))

    def test_writes_embedded_macrolib_adf(self) -> None:
        mixture = MixtureXS(
            name="fuel",
            total=np.array([0.5, 1.0]),
            absorption=np.array([0.05, 0.1]),
            fission=np.array([0.0, 0.0]),
            nu_fission=np.array([0.0, 0.0]),
            chi=np.array([0.0, 0.0]),
            scatter_matrix=np.array([[[0.10, 0.20], [0.00, 0.70]]]),
            fissionable=False,
            adf={"FD_B": np.array([1.05, 0.97])},
        )

        blocks = build_multicompo_blocks(
            [mixture],
            np.array([1.0e-5, 1.0, 1.0e7]),
            root_name="CPO",
            comment="adf smoke",
        )
        by_name = {block.name: block for block in blocks if block.name}
        cpo_state = [
            block for block in blocks if block.name == "STATE-VECTOR" and block.level == 2
        ][0]
        library_state = [
            block for block in blocks if block.name == "STATE-VECTOR" and block.level == 6
        ][0]

        self.assertEqual(cpo_state.data[15], 3)
        self.assertEqual(library_state.data[23], 3)
        self.assertEqual(by_name["MACROLIB"].level, 6)
        self.assertEqual(by_name["ADF"].level, 7)
        self.assertEqual(by_name["NTYPE"].data, (1,))
        self.assertEqual(lcm.unpack_fixed_strings(by_name["HADF"].data, 8), ["FD_B    "])
        np.testing.assert_allclose(by_name["FD_B"].data, (1.05, 0.97))
        fd_b_index = blocks.index(by_name["FD_B"])
        self.assertEqual(blocks[fd_b_index + 1].level, -8)
        self.assertEqual(blocks[fd_b_index + 2].level, -7)

    def test_rejects_partial_adf_layout(self) -> None:
        base = dict(
            total=np.array([0.5]),
            absorption=np.array([0.05]),
            fission=np.array([0.0]),
            nu_fission=np.array([0.0]),
            chi=np.array([0.0]),
            scatter_matrix=np.array([[[0.10]]]),
            fissionable=False,
        )
        with self.assertRaisesRegex(ValueError, "ADF data must be present"):
            build_multicompo_blocks(
                [
                    MixtureXS(name="fuel", adf={"FD_B": np.array([1.0])}, **base),
                    MixtureXS(name="mod", **base),
                ],
                np.array([1.0e-5, 1.0e7]),
                root_name="CPO",
                comment="bad adf",
            )

    def test_read_mgxs_hdf5_accepts_openmc_moment_last_axes(self) -> None:
        import h5py

        raw_scatter = np.zeros((3, 3, 2), dtype=float)
        raw_scatter[:, :, 0] = [
            [0.10, 0.20, 0.00],
            [0.00, 0.70, 0.01],
            [0.02, 0.00, 0.30],
        ]
        raw_scatter[:, :, 1] = [
            [0.01, -0.02, 0.00],
            [0.03, 0.00, 0.04],
            [0.00, 0.05, -0.01],
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "p1_mgxs.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 3
                h5.attrs["legendre_order"] = 1
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0, 1.0e3, 1.0e7])
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = False
                fuel.attrs["scatter_axes"] = "G_in,G_out,moment"
                fuel.create_dataset("total", data=[0.5, 0.6, 0.7])
                fuel.create_dataset("absorption", data=[0.05, 0.06, 0.07])
                fuel.create_dataset("fission", data=[0.0, 0.0, 0.0])
                fuel.create_dataset("nu_fission", data=[0.0, 0.0, 0.0])
                fuel.create_dataset("chi", data=[0.0, 0.0, 0.0])
                fuel.create_dataset("scatter_matrix", data=raw_scatter)

            mixtures, _ = read_mgxs_hdf5(path)

        self.assertEqual(mixtures[0].nmoments, 2)
        np.testing.assert_allclose(mixtures[0].scatter_matrix[0], raw_scatter[:, :, 0])
        np.testing.assert_allclose(mixtures[0].scatter_matrix[1], raw_scatter[:, :, 1])
        np.testing.assert_allclose(
            mixtures[0].transport_total,
            np.array([0.5, 0.6, 0.7]) - raw_scatter[:, :, 1].sum(axis=1),
        )

    def test_read_mgxs_hdf5_prefers_transport_total_dataset(self) -> None:
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "p1_mgxs_with_strd.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 1
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0, 1.0e7])
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = False
                fuel.attrs["scatter_axes"] = "moment,G_in,G_out"
                fuel.create_dataset("total", data=[0.5, 0.6])
                fuel.create_dataset("transport_total", data=[0.4, 0.45])
                fuel.create_dataset("absorption", data=[0.05, 0.06])
                fuel.create_dataset("fission", data=[0.0, 0.0])
                fuel.create_dataset("nu_fission", data=[0.0, 0.0])
                fuel.create_dataset("chi", data=[0.0, 0.0])
                fuel.create_dataset(
                    "scatter_matrix",
                    data=np.array(
                        [
                            [[0.1, 0.2], [0.0, 0.3]],
                            [[0.01, 0.02], [0.03, 0.04]],
                        ]
                    ),
                )

            mixtures, _ = read_mgxs_hdf5(path)

        np.testing.assert_allclose(mixtures[0].transport_total, [0.4, 0.45])

    def test_read_mgxs_hdf5_reads_adf_group(self) -> None:
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs_with_adf.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0, 1.0e7])
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = False
                fuel.create_dataset("total", data=[0.5, 0.6])
                fuel.create_dataset("absorption", data=[0.05, 0.06])
                fuel.create_dataset("fission", data=[0.0, 0.0])
                fuel.create_dataset("nu_fission", data=[0.0, 0.0])
                fuel.create_dataset("chi", data=[0.0, 0.0])
                fuel.create_dataset("scatter_matrix", data=np.array([[0.1, 0.2], [0.0, 0.3]]))
                adf = fuel.create_group("adf")
                adf.create_dataset("FD_XMIN", data=[1.01, 0.99])
                adf.create_dataset("FD_XMAX", data=[1.02, 0.98])

            mixtures, _ = read_mgxs_hdf5(path)

        self.assertEqual(set(mixtures[0].adf or {}), {"FD_XMIN", "FD_XMAX"})
        np.testing.assert_allclose(mixtures[0].adf["FD_XMIN"], [1.01, 0.99])
        np.testing.assert_allclose(mixtures[0].adf["FD_XMAX"], [1.02, 0.98])

    def test_read_mgxs_hdf5_reads_h_factor_or_default(self) -> None:
        import h5py

        with tempfile.TemporaryDirectory() as tmpdir:
            with_data = Path(tmpdir) / "mgxs_with_h_factor.h5"
            with h5py.File(with_data, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0, 1.0e7])
                mixtures = h5.create_group("mixtures")
                fuel = mixtures.create_group("fuel")
                fuel.attrs["fissionable"] = False
                fuel.create_dataset("total", data=[0.5, 0.6])
                fuel.create_dataset("absorption", data=[0.05, 0.06])
                fuel.create_dataset("fission", data=[0.0, 0.0])
                fuel.create_dataset("nu_fission", data=[0.0, 0.0])
                fuel.create_dataset("chi", data=[0.0, 0.0])
                fuel.create_dataset("scatter_matrix", data=np.array([[0.1, 0.2], [0.0, 0.3]]))
                fuel.create_dataset("H-FACTOR", data=[11.0, 22.0])

            mixtures, _ = read_mgxs_hdf5(with_data, h_factor_default=99.0)

        np.testing.assert_allclose(mixtures[0].h_factor, [11.0, 22.0])

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mgxs_without_h_factor.h5"
            with h5py.File(path, "w") as h5:
                h5.attrs["energy_groups"] = 2
                h5.attrs["legendre_order"] = 0
                h5.create_dataset("energy_bounds", data=[1.0e-5, 1.0, 1.0e7])
                mixtures_group = h5.create_group("mixtures")
                fuel = mixtures_group.create_group("fuel")
                fuel.attrs["fissionable"] = False
                fuel.create_dataset("total", data=[0.5, 0.6])
                fuel.create_dataset("absorption", data=[0.05, 0.06])
                fuel.create_dataset("fission", data=[0.0, 0.0])
                fuel.create_dataset("nu_fission", data=[0.0, 0.0])
                fuel.create_dataset("chi", data=[0.0, 0.0])
                fuel.create_dataset("scatter_matrix", data=np.array([[0.1, 0.2], [0.0, 0.3]]))

            defaulted, _ = read_mgxs_hdf5(path, h_factor_default=99.0)

        np.testing.assert_allclose(defaulted[0].h_factor, [99.0, 99.0])


if __name__ == "__main__":
    unittest.main()
