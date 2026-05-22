from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon import lcm_ascii
from openmc2donjon.macrolib import (
    convert_mgxs_hdf5_to_macrolib,
    read_macrolib_ascii,
)
from openmc2donjon.mgxs_input_contract import validate_input
from openmc2donjon.multicompo import convert_mgxs_hdf5, read_mgxs_hdf5


class ManyMixtureScaleTests(unittest.TestCase):
    def test_many_spatial_domains_convert_and_read_back(self) -> None:
        nmixtures = 128
        ngroups = 4

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            hdf5 = root / "many_domains.h5"
            mcompo = root / "many_domains.mcompo.txt"
            macrolib_path = root / "many_domains.macrolib.txt"

            _write_many_mixture_fixture(hdf5, nmixtures=nmixtures, ngroups=ngroups)

            report = validate_input(
                hdf5,
                require_transport_dataset=True,
                require_volume=True,
                require_h_factor=True,
                expected_energy_group_structure="OPENMC2DONJON-MANY-MIXTURE-4G",
                scatter_row_balance_fail=1.0e-12,
            )
            self.assertTrue(report.ok, report.issues)
            self.assertEqual(report.mixtures, nmixtures)
            self.assertEqual(report.fissionable_mixtures, nmixtures - nmixtures // 5)
            self.assertEqual(report.volume_attributes, nmixtures)
            self.assertEqual(report.volume_defaulted, 0)
            self.assertEqual(report.transport_total_datasets, nmixtures)
            self.assertEqual(report.h_factor_datasets, nmixtures)

            mixtures, energy_bounds = read_mgxs_hdf5(hdf5)
            self.assertEqual(len(mixtures), nmixtures)
            self.assertEqual([mixtures[0].name, mixtures[-1].name], ["M0001", "M0128"])
            self.assertEqual(mixtures[0].scatter_matrix.shape, (2, ngroups, ngroups))
            np.testing.assert_allclose(energy_bounds, _energy_bounds(ngroups))

            convert_mgxs_hdf5(hdf5, mcompo)
            blocks = lcm_ascii.read_lcm_ascii(mcompo)
            state = _first_block(blocks, "STATE-VECTOR", level=2).data
            mixtures_block = _first_block(blocks, "MIXTURES", level=2)
            self.assertEqual(state[:4], (nmixtures, ngroups, 1, 1))
            self.assertEqual(mixtures_block.count, nmixtures)
            self.assertEqual(len([block for block in blocks if block.name == "NTOT0"]), nmixtures)
            self.assertGreater(mcompo.stat().st_size, 100_000)

            convert_mgxs_hdf5_to_macrolib(hdf5, macrolib_path)
            macrolib = read_macrolib_ascii(macrolib_path)
            self.assertEqual(macrolib.nmixtures, nmixtures)
            self.assertEqual(macrolib.ngroups, ngroups)
            self.assertEqual(macrolib.ntot0.shape, (nmixtures, ngroups))
            self.assertEqual(macrolib.h_factor.shape, (nmixtures, ngroups))
            self.assertEqual(macrolib.scatter[0].shape, (nmixtures, ngroups, ngroups))
            np.testing.assert_allclose(macrolib.volume[[0, 63, 127]], [10.01, 10.64, 11.28])
            np.testing.assert_allclose(
                macrolib.ntot0[[0, 63, 127]],
                np.stack(
                    [
                        _expected_total(1, ngroups),
                        _expected_total(64, ngroups),
                        _expected_total(128, ngroups),
                    ]
                ),
            )
            np.testing.assert_allclose(macrolib.h_factor[4], np.zeros(ngroups))
            self.assertTrue(np.all(macrolib.h_factor[5] > 0.0))


def _write_many_mixture_fixture(path: Path, *, nmixtures: int, ngroups: int) -> None:
    with h5py.File(path, "w") as h5:
        h5.attrs["energy_groups"] = ngroups
        h5.attrs["legendre_order"] = 1
        h5.attrs["energy_group_structure"] = "OPENMC2DONJON-MANY-MIXTURE-4G"
        h5.attrs["domain_mode"] = "full_core_spatial_stress"
        h5.attrs["spatial_mapping"] = "one synthetic spatial domain -> one DONJON mixture"
        h5.create_dataset("energy_bounds", data=_energy_bounds(ngroups))

        mixtures = h5.create_group("mixtures")
        for index in range(1, nmixtures + 1):
            name = f"M{index:04d}"
            group = mixtures.create_group(name)
            group.attrs["fissionable"] = index % 5 != 0
            group.attrs["scatter_axes"] = "moment,from,to"
            group.attrs["volume"] = 10.0 + 0.01 * index
            group.attrs["source_domain_id"] = index
            group.attrs["source_domain_type"] = "cell"
            group.attrs["assembly_x"] = (index - 1) % 16 + 1
            group.attrs["assembly_y"] = (index - 1) // 16 + 1

            p0, p1 = _scatter(index, ngroups)
            absorption = _absorption(index, ngroups)
            total = absorption + p0.sum(axis=1)
            fissionable = bool(group.attrs["fissionable"])
            fission = (
                0.004 + 0.0001 * index + 0.00005 * np.arange(ngroups)
                if fissionable
                else np.zeros(ngroups)
            )
            nu_fission = 2.43 * fission
            chi = np.zeros(ngroups)
            if fissionable:
                chi[0] = 1.0
            h_factor = (
                1.0e7 + 1000.0 * index + 10.0 * np.arange(ngroups)
                if fissionable
                else np.zeros(ngroups)
            )

            group.create_dataset("total", data=total)
            group.create_dataset("absorption", data=absorption)
            group.create_dataset("fission", data=fission)
            group.create_dataset("nu_fission", data=nu_fission)
            group.create_dataset("chi", data=chi)
            group.create_dataset("scatter_matrix", data=np.stack([p0, p1]))
            group.create_dataset("transport_total", data=total + 0.05)
            group.create_dataset("kappa_fission", data=h_factor)


def _energy_bounds(ngroups: int) -> np.ndarray:
    return np.geomspace(1.0e-5, 2.0e7, ngroups + 1)


def _absorption(index: int, ngroups: int) -> np.ndarray:
    return 0.020 + 0.00002 * index + 0.001 * np.arange(ngroups)


def _scatter(index: int, ngroups: int) -> tuple[np.ndarray, np.ndarray]:
    p0 = np.zeros((ngroups, ngroups), dtype=float)
    for group in range(ngroups):
        p0[group, group] = 0.10 + 0.002 * group + 0.00001 * index
        if group + 1 < ngroups:
            p0[group, group + 1] = 0.015 + 0.0002 * group
        if group + 2 < ngroups:
            p0[group, group + 2] = 0.002
    p1 = 0.01 * p0
    return p0, p1


def _expected_total(index: int, ngroups: int) -> np.ndarray:
    p0, _p1 = _scatter(index, ngroups)
    return _absorption(index, ngroups) + p0.sum(axis=1)


def _first_block(blocks: list[lcm_ascii.LcmBlock], name: str, *, level: int):
    for block in blocks:
        if block.name == name and block.level == level:
            return block
    raise AssertionError(f"missing block {name!r} at level {level}")


if __name__ == "__main__":
    unittest.main()
