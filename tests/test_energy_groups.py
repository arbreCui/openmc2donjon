from __future__ import annotations

import unittest

import numpy as np

from openmc2donjon.energy_groups import (
    energy_bounds_order,
    energy_mesh_catalog,
    identify_mesh,
    load_energy_mesh,
    validate_energy_bounds_internal,
)


class EnergyGroupsTests(unittest.TestCase):
    def test_catalog_loads_bundled_meshes(self) -> None:
        catalog = energy_mesh_catalog()
        by_id = {mesh.mesh_id: mesh for mesh in catalog}

        self.assertGreaterEqual(len(catalog), 38)
        self.assertIn("casmo_70", by_id)
        self.assertEqual(by_id["casmo_70"].n_groups, 70)

    def test_identifies_known_mesh_from_ascending_or_descending_bounds(self) -> None:
        mesh = load_energy_mesh("casmo_70")
        ascending = mesh.boundaries_descending[::-1]

        self.assertEqual(identify_mesh(ascending).mesh_id, "casmo_70")
        self.assertEqual(identify_mesh(mesh.boundaries_descending).mesh_id, "casmo_70")

    def test_unknown_mesh_returns_none(self) -> None:
        self.assertIsNone(identify_mesh(np.array([1.0e-5, 0.7, 1.0e7])))

    def test_validates_openmc_ascending_bounds(self) -> None:
        issues = validate_energy_bounds_internal(
            np.array([1.0e-5, 1.0, 1.0e7]),
            expected_groups=2,
            expected_order="ascending",
        )

        self.assertEqual(issues, [])
        self.assertEqual(
            energy_bounds_order(np.array([1.0e-5, 1.0, 1.0e7])),
            "ascending",
        )

    def test_rejects_wrong_order_duplicates_and_nonfinite_values(self) -> None:
        descending = validate_energy_bounds_internal(
            np.array([1.0e7, 1.0, 1.0e-5]),
            expected_groups=2,
            expected_order="ascending",
        )
        repeated = validate_energy_bounds_internal(
            np.array([1.0e-5, 1.0, 1.0]),
            expected_groups=2,
            expected_order="ascending",
        )
        nonfinite = validate_energy_bounds_internal(
            np.array([1.0e-5, np.nan, 1.0e7]),
            expected_groups=2,
            expected_order="ascending",
        )

        self.assertIn("energy_bounds must be strictly ascending", descending)
        self.assertIn("energy_bounds must be strictly ascending", repeated)
        self.assertIn("energy_bounds contains non-finite values", nonfinite)

    def test_rejects_non_vector_bounds(self) -> None:
        issues = validate_energy_bounds_internal(
            np.array([[1.0e-5, 1.0], [10.0, 1.0e7]]),
            expected_groups=3,
            expected_order="ascending",
        )

        self.assertIn("energy_bounds must be a one-dimensional vector", issues)


if __name__ == "__main__":
    unittest.main()
