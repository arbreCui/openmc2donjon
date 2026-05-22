from __future__ import annotations

import unittest

import numpy as np

from openmc2donjon.scatter import (
    dense_moments_to_triplets,
    dense_to_triplet,
    triplet_to_dense,
    triplets_to_dense_moments,
)


class ScatterTripletTests(unittest.TestCase):
    def test_all_zero_columns_store_zero_self_spans(self) -> None:
        dense = np.zeros((4, 4), dtype=float)

        triplet = dense_to_triplet(dense)

        np.testing.assert_array_equal(triplet.njjs, np.array([1, 1, 1, 1]))
        np.testing.assert_array_equal(triplet.ijjs, np.array([1, 2, 3, 4]))
        np.testing.assert_allclose(triplet.scat, np.zeros(4))
        np.testing.assert_allclose(
            triplet_to_dense(triplet.njjs, triplet.ijjs, triplet.scat),
            dense,
        )

    def test_contiguous_span_keeps_internal_zeroes(self) -> None:
        dense = np.array(
            [
                [1.0, 0.0, 4.0],
                [0.0, 0.0, 5.0],
                [2.0, 3.0, 6.0],
            ]
        )

        triplet = dense_to_triplet(dense)

        np.testing.assert_array_equal(triplet.njjs, np.array([3, 1, 3]))
        np.testing.assert_array_equal(triplet.ijjs, np.array([3, 3, 3]))
        np.testing.assert_allclose(
            triplet.scat,
            np.array(
                [
                    2.0,
                    0.0,
                    1.0,
                    3.0,
                    6.0,
                    5.0,
                    4.0,
                ]
            ),
        )
        np.testing.assert_allclose(
            triplet_to_dense(triplet.njjs, triplet.ijjs, triplet.scat),
            dense,
        )

    def test_single_off_diagonal_scatter_uses_one_value_span(self) -> None:
        dense = np.zeros((4, 4), dtype=float)
        dense[0, 3] = 0.125
        dense[3, 0] = 0.875

        triplet = dense_to_triplet(dense)

        np.testing.assert_array_equal(triplet.njjs, np.array([1, 1, 1, 1]))
        np.testing.assert_array_equal(triplet.ijjs, np.array([4, 2, 3, 1]))
        np.testing.assert_allclose(
            triplet.scat,
            np.array([0.875, 0.0, 0.0, 0.125]),
        )
        np.testing.assert_allclose(
            triplet_to_dense(triplet.njjs, triplet.ijjs, triplet.scat),
            dense,
        )

    def test_multiple_legendre_moments_round_trip_independently(self) -> None:
        p0 = np.array(
            [
                [0.5, 0.1, 0.0, 0.0],
                [0.0, 0.4, 0.2, 0.0],
                [0.0, 0.0, 0.3, 0.1],
                [0.0, 0.0, 0.0, 0.2],
            ]
        )
        p1 = np.array(
            [
                [0.05, 0.0, 0.0, 0.0],
                [0.01, 0.04, 0.0, 0.0],
                [0.0, 0.02, 0.03, 0.0],
                [0.0, 0.0, 0.01, 0.02],
            ]
        )
        dense = np.stack([p0, p1])

        triplets = dense_moments_to_triplets(dense)
        restored = triplets_to_dense_moments(triplets, ngroups=4)

        self.assertEqual(len(triplets), 2)
        np.testing.assert_allclose(restored, dense)

    def test_atol_ignores_near_zero_edges_when_building_span(self) -> None:
        dense = np.zeros((3, 3), dtype=float)
        dense[0, 1] = 1.0e-12
        dense[1, 1] = 0.25

        triplet = dense_to_triplet(dense, atol=1.0e-10)

        np.testing.assert_array_equal(triplet.njjs, np.array([1, 1, 1]))
        np.testing.assert_array_equal(triplet.ijjs, np.array([1, 2, 3]))
        np.testing.assert_allclose(triplet.scat, np.array([0.0, 0.25, 0.0]))
        restored = triplet_to_dense(triplet.njjs, triplet.ijjs, triplet.scat)
        self.assertEqual(restored[0, 1], 0.0)
        self.assertEqual(restored[1, 1], 0.25)

    def test_rejects_invalid_dense_shapes(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be square"):
            dense_to_triplet(np.zeros((2, 3)))
        with self.assertRaisesRegex(ValueError, "must be square"):
            dense_to_triplet(np.zeros(3))
        with self.assertRaisesRegex(ValueError, "dense moments"):
            dense_moments_to_triplets(np.zeros((3, 3)))

    def test_rejects_invalid_triplet_payloads(self) -> None:
        with self.assertRaisesRegex(ValueError, "same shape"):
            triplet_to_dense([1, 1], [1], [0.0, 0.0])
        with self.assertRaisesRegex(ValueError, "length must equal ngroups"):
            triplet_to_dense([1, 1], [1, 2], [0.0, 0.0], ngroups=3)
        with self.assertRaisesRegex(ValueError, "invalid scattering span"):
            triplet_to_dense([2], [1], [0.0, 0.0])
        with self.assertRaisesRegex(ValueError, "ended before"):
            triplet_to_dense([2, 0], [2, 0], [0.0])
        with self.assertRaisesRegex(ValueError, "unused values"):
            triplet_to_dense([1], [1], [0.0, 1.0])
        with self.assertRaisesRegex(ValueError, "at least one"):
            triplets_to_dense_moments([], ngroups=2)


if __name__ == "__main__":
    unittest.main()
