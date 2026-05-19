from __future__ import annotations

import unittest

import numpy as np

from openmc2donjon.scatter import dense_to_triplet, triplet_to_dense


class ScatterTripletTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
