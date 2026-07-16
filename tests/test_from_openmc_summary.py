from __future__ import annotations

import unittest

from openmc2donjon.from_openmc_summary import (
    FROM_OPENMC_SUMMARY_SCHEMA,
    FROM_OPENMC_SUMMARY_SCHEMA_V1,
    FROM_OPENMC_SUMMARY_SCHEMA_V2,
    FROM_OPENMC_SUMMARY_SCHEMA_V3,
    FROM_OPENMC_SUMMARY_SCHEMA_V4,
    validate_from_openmc_summary,
)
from openmc2donjon.openmc_provenance import (
    OPENMC_PROVENANCE_SCHEMA,
    provenance_digest,
)


def valid_summary() -> dict[str, object]:
    provenance: dict[str, object] = {
        "schema": OPENMC_PROVENANCE_SCHEMA,
        "status": "incomplete",
        "artifacts": [
            {
                "role": "recipe",
                "path": "/case/export_recipe.py",
                "sha256": "1" * 64,
            },
            {
                "role": "statepoint",
                "path": "/case/statepoint.120.h5",
                "sha256": "2" * 64,
            },
        ],
    }
    provenance["digest_sha256"] = provenance_digest(provenance)
    return {
        "burnup_axis": {"present": False},
        "check_passed": True,
        "check_summary_json": "check_summary.json",
        "checked": True,
        "energy_groups": 7,
        "format": "multicompo",
        "h_factor_default": None,
        "hdf5": "mgxs_library.h5",
        "hdf5_sha256": "3" * 64,
        "hdf5_kept": True,
        "legendre_order": 1,
        "loaded_statepoint": True,
        "mixture_count": 2,
        "mixture_names": ["A", "B"],
        "output": "out.mcompo.txt",
        "output_sha256": "4" * 64,
        "openmc_provenance": provenance,
        "package_version": "0.1.2",
        "recipe": "/case/export_recipe.py",
        "root_name": "CPO",
        "schema": FROM_OPENMC_SUMMARY_SCHEMA,
        "selected_mixtures": None,
        "single_point_burnup": None,
        "state_points": 1,
        "statepoint": "/case/statepoint.120.h5",
        "std_dev_dataset_count": 6,
        "std_dev_expected_dataset_count": 8,
        "zero_flux_fill_macrolib": None,
        "zero_flux_fill_total_bins": None,
    }


class FromOpenMCSummaryTests(unittest.TestCase):
    def test_valid_summary(self) -> None:
        self.assertEqual(validate_from_openmc_summary(valid_summary()), [])

    def test_accepts_legacy_v3_summary(self) -> None:
        payload = valid_summary()
        payload["schema"] = FROM_OPENMC_SUMMARY_SCHEMA_V3
        del payload["hdf5_sha256"]
        del payload["output_sha256"]
        del payload["openmc_provenance"]
        del payload["zero_flux_fill_macrolib"]
        del payload["zero_flux_fill_total_bins"]
        self.assertEqual(validate_from_openmc_summary(payload), [])

    def test_v4_fill_fields_validated(self) -> None:
        payload = valid_summary()
        payload["schema"] = FROM_OPENMC_SUMMARY_SCHEMA_V4
        del payload["hdf5_sha256"]
        del payload["output_sha256"]
        del payload["openmc_provenance"]
        payload["zero_flux_fill_macrolib"] = "/data/macrolib.h5"
        payload["zero_flux_fill_total_bins"] = 626
        self.assertEqual(validate_from_openmc_summary(payload), [])
        payload["zero_flux_fill_total_bins"] = "many"
        errors = validate_from_openmc_summary(payload)
        self.assertTrue(any("zero_flux_fill_total_bins" in e for e in errors))

    def test_accepts_legacy_v1_summary(self) -> None:
        payload = valid_summary()
        payload["schema"] = FROM_OPENMC_SUMMARY_SCHEMA_V1
        payload.pop("hdf5_sha256")
        payload.pop("output_sha256")
        payload.pop("openmc_provenance")
        payload.pop("zero_flux_fill_macrolib")
        payload.pop("zero_flux_fill_total_bins")
        payload.pop("checked")
        payload.pop("check_passed")
        payload.pop("check_summary_json")
        payload.pop("std_dev_dataset_count")
        payload.pop("std_dev_expected_dataset_count")

        self.assertEqual(validate_from_openmc_summary(payload), [])

    def test_accepts_legacy_v2_summary(self) -> None:
        payload = valid_summary()
        payload["schema"] = FROM_OPENMC_SUMMARY_SCHEMA_V2
        payload.pop("hdf5_sha256")
        payload.pop("output_sha256")
        payload.pop("openmc_provenance")
        payload.pop("zero_flux_fill_macrolib")
        payload.pop("zero_flux_fill_total_bins")
        payload.pop("std_dev_dataset_count")
        payload.pop("std_dev_expected_dataset_count")

        self.assertEqual(validate_from_openmc_summary(payload), [])

    def test_rejects_missing_extra_and_inconsistent_count(self) -> None:
        payload = valid_summary()
        payload.pop("output")
        payload["unexpected"] = "value"
        payload["mixture_count"] = 3

        errors = validate_from_openmc_summary(payload)

        self.assertIn("missing keys: output", errors)
        self.assertIn("unexpected keys: unexpected", errors)
        self.assertIn("mixture_count: expected len(mixture_names)", errors)

    def test_rejects_invalid_burnup_axis(self) -> None:
        payload = valid_summary()
        payload["burnup_axis"] = {"count": 2, "present": True, "values": [0.0]}

        self.assertIn(
            "burnup_axis.count: expected len(values)",
            validate_from_openmc_summary(payload),
        )

    def test_rejects_inconsistent_check_fields(self) -> None:
        payload = valid_summary()
        payload["checked"] = False
        payload["check_passed"] = True
        payload["check_summary_json"] = "check_summary.json"

        errors = validate_from_openmc_summary(payload)

        self.assertIn("check_passed: expected null when checked is false", errors)
        self.assertIn("check_summary_json: expected null when checked is false", errors)

    def test_rejects_inconsistent_std_dev_counts(self) -> None:
        payload = valid_summary()
        payload["std_dev_dataset_count"] = 9

        self.assertIn(
            "std_dev_dataset_count: expected <= std_dev_expected_dataset_count",
            validate_from_openmc_summary(payload),
        )


if __name__ == "__main__":
    unittest.main()
