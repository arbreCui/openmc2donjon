from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from openmc2donjon.physical_sph_contract import (
    physical_colorset_sph_issues,
    physical_sph_issues,
)


class PhysicalColorsetSphContractTests(unittest.TestCase):
    def test_generic_contract_accepts_one_or_many_declared_domains(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for domains in (1, 17, 91):
                path = root / f"physical_{domains}.h5"
                _write_colorset(path, domains=domains)
                self.assertEqual(physical_sph_issues(path), [])

    def test_accepts_seven_domain_applied_rate_sph_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colorset.h5"
            _write_colorset(path)
            self.assertEqual(physical_colorset_sph_issues(path), [])

    def test_rejects_global_or_unconverged_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colorset.h5"
            _write_colorset(path, kind="openmc-ce-mg-global", residual=0.08)
            issues = physical_colorset_sph_issues(path)
            self.assertTrue(any("global" in issue for issue in issues))
            self.assertTrue(any("not converged" in issue for issue in issues))

    def test_rejects_a_non_colorset_domain_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fullcore.h5"
            _write_colorset(path, domains=91)
            issues = physical_colorset_sph_issues(path)
            self.assertTrue(any("exactly 7 domains" in issue for issue in issues))
            self.assertEqual(physical_sph_issues(path), [])

    def test_rejects_numerical_exemptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colorset.h5"
            _write_colorset(path)
            with h5py.File(path, "r+") as h5:
                h5.attrs["sph_zero_flux_policy"] = "identity"
                h5.attrs["sph_identity_bin_count"] = 1
                h5.attrs["sph_floored_bin_count"] = 2
                h5.attrs["sph_frozen_group_bin_count"] = 3
                h5.attrs["sph_clipped_count"] = 4
            issues = physical_colorset_sph_issues(path)
            self.assertTrue(any("identity is forbidden" in issue for issue in issues))
            self.assertTrue(any("identity-substituted" in issue for issue in issues))
            self.assertTrue(any("flux-floored" in issue for issue in issues))
            self.assertTrue(any("frozen-group" in issue for issue in issues))
            self.assertTrue(any("clipped" in issue for issue in issues))

    def test_rejects_macrolib_filled_cross_section_bins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "colorset.h5"
            _write_colorset(path)
            with h5py.File(path, "r+") as h5:
                h5["mixtures"]["domain_1"].attrs["zero_flux_filled_groups"] = [31, 32]
            issues = physical_colorset_sph_issues(path)
            self.assertTrue(any("macrolib-filled XS bins" in issue for issue in issues))


def _write_colorset(
    path: Path,
    *,
    domains: int = 7,
    kind: str = "openmc-ce-mg-rate",
    residual: float = 0.01,
) -> None:
    names = [f"domain_{index + 1}" for index in range(domains)]
    with h5py.File(path, "w") as h5:
        h5.create_dataset("mixture_names", data=np.asarray(names, dtype="S"))
        mixtures = h5.create_group("mixtures")
        for index, name in enumerate(names, start=1):
            group = mixtures.create_group(name)
            group.attrs["source_domain_index"] = index
        h5.attrs["sph_applied"] = True
        h5.attrs["sph_applied_source"] = "/runs/colorset/openmc_sph.h5"
        h5.attrs["sph_apply_operator"] = "divide-xs-by-nsph"
        h5.attrs["sph_kind"] = kind
        h5.attrs["sph_real"] = True
        h5.attrs["sph_derivation"] = "rate-preserving-ce-mg-fixed-point"
        h5.attrs["sph_target"] = "rate"
        h5.attrs["sph_flux_normalization"] = "power"
        h5.attrs["sph_zero_flux_policy"] = "reject"
        h5.attrs["sph_identity_bin_count"] = 0
        h5.attrs["sph_floored_bin_count"] = 0
        h5.attrs["sph_frozen_group_bin_count"] = 0
        h5.attrs["sph_clipped_count"] = 0
        h5.attrs["sph_max_update_residual"] = residual


if __name__ == "__main__":
    unittest.main()
