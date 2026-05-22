from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np

from openmc2donjon.mgxs_input_equivalence import (
    adf_names_for_group,
    sph_present_for_group,
    validate_sph_layout,
)
from openmc2donjon.mgxs_input_report import InputReport


class MgxsInputEquivalenceTests(unittest.TestCase):
    def test_adf_group_reports_invalid_face_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "adf.h5"
            with h5py.File(path, "w") as h5:
                group = h5.create_group("mix")
                adf = group.create_group("adf")
                adf.create_dataset("FD_XMIN", data=np.array([1.0, -0.5]))

                report = InputReport(path=str(path))
                names = adf_names_for_group(group, 2, report, "mix")

        self.assertEqual(names, ["FD_XMIN"])
        self.assertIn("mixture mix: ADF FD_XMIN must be positive", report.issues)

    def test_sph_presence_requires_positive_single_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "sph.h5"
            with h5py.File(path, "w") as h5:
                group = h5.create_group("mix")
                group.create_dataset("NSPH", data=np.array([1.0, 0.0]))

                report = InputReport(path=str(path))
                present = sph_present_for_group(group, 2, report, "mix")

        self.assertTrue(present)
        self.assertIn("mixture mix: NSPH must be positive", report.issues)

    def test_sph_layout_rejects_partial_coverage(self) -> None:
        report = InputReport(path="memory")

        validate_sph_layout(report, [True, False], require_sph=False)

        self.assertIn(
            "SPH data must be present for either all calculations or none",
            report.issues,
        )


if __name__ == "__main__":
    unittest.main()
