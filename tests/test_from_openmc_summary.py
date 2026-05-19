from __future__ import annotations

import unittest

from openmc2donjon.from_openmc_summary import (
    FROM_OPENMC_SUMMARY_SCHEMA,
    validate_from_openmc_summary_v1,
)


def valid_summary() -> dict[str, object]:
    return {
        "burnup_axis": {"present": False},
        "energy_groups": 7,
        "format": "multicompo",
        "h_factor_default": None,
        "hdf5": "mgxs_library.h5",
        "hdf5_kept": True,
        "legendre_order": 1,
        "loaded_statepoint": True,
        "mixture_count": 2,
        "mixture_names": ["A", "B"],
        "output": "out.mcompo.txt",
        "package_version": "0.1.2",
        "recipe": "/case/export_recipe.py",
        "root_name": "CPO",
        "schema": FROM_OPENMC_SUMMARY_SCHEMA,
        "selected_mixtures": None,
        "single_point_burnup": None,
        "state_points": 1,
        "statepoint": "/case/statepoint.120.h5",
    }


class FromOpenMCSummaryTests(unittest.TestCase):
    def test_valid_summary(self) -> None:
        self.assertEqual(validate_from_openmc_summary_v1(valid_summary()), [])

    def test_rejects_missing_extra_and_inconsistent_count(self) -> None:
        payload = valid_summary()
        payload.pop("output")
        payload["unexpected"] = "value"
        payload["mixture_count"] = 3

        errors = validate_from_openmc_summary_v1(payload)

        self.assertIn("missing keys: output", errors)
        self.assertIn("unexpected keys: unexpected", errors)
        self.assertIn("mixture_count: expected len(mixture_names)", errors)

    def test_rejects_invalid_burnup_axis(self) -> None:
        payload = valid_summary()
        payload["burnup_axis"] = {"count": 2, "present": True, "values": [0.0]}

        self.assertIn(
            "burnup_axis.count: expected len(values)",
            validate_from_openmc_summary_v1(payload),
        )


if __name__ == "__main__":
    unittest.main()
