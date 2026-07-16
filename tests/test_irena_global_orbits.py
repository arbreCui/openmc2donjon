from __future__ import annotations

from collections import Counter
import importlib.util
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ORBITS = _load(
    "_irena30_global_orbits",
    "examples/irena30_native_fullcore/global_orbits.py",
)
TOPOLOGY = _load(
    "_irena30_local_topology_for_orbit_test",
    "examples/irena30_native_fullcore/topology.py",
)


def test_stable_21_orbit_numbering_and_ring_counts() -> None:
    assert len(ORBITS.ORBITS) == 21
    assert [orbit.number for orbit in ORBITS.ORBITS] == list(range(1, 22))
    assert [orbit.id for orbit in ORBITS.ORBITS] == [
        f"O{number:02d}" for number in range(1, 22)
    ]
    assert Counter(orbit.ring for orbit in ORBITS.ORBITS) == {
        0: 1,
        1: 2,
        2: 3,
        3: 4,
        4: 5,
        5: 6,
    }


def test_stable_members_and_material_labels_are_pinned_explicitly() -> None:
    expected = (
        (1, 0, 0, "INT", (0,)),
        (2, 1, 0, "DSDF", (0, 2, 4)),
        (3, 1, 1, "INT", (1, 3, 5)),
        (4, 2, 0, "INT", (0, 4, 8)),
        (5, 2, 1, "INT", (1, 3, 5, 7, 9, 11)),
        (6, 2, 2, "INT", (2, 6, 10)),
        (7, 3, 0, "CSD", (0, 6, 12)),
        (8, 3, 1, "INT", (1, 5, 7, 11, 13, 17)),
        (9, 3, 2, "INT", (2, 4, 8, 10, 14, 16)),
        (10, 3, 3, "CSD", (3, 9, 15)),
        (11, 4, 0, "EXT", (0, 8, 16)),
        (12, 4, 1, "EXT", (1, 7, 9, 15, 17, 23)),
        (13, 4, 2, "EXT", (2, 6, 10, 14, 18, 22)),
        (14, 4, 3, "EXT", (3, 5, 11, 13, 19, 21)),
        (15, 4, 4, "EXT", (4, 12, 20)),
        (16, 5, 0, "PNL", (0, 10, 20)),
        (17, 5, 1, "PNL", (1, 9, 11, 19, 21, 29)),
        (18, 5, 2, "PNL", (2, 8, 12, 18, 22, 28)),
        (19, 5, 3, "PNL", (3, 7, 13, 17, 23, 27)),
        (20, 5, 4, "PNL", (4, 6, 14, 16, 24, 26)),
        (21, 5, 5, "PNL", (5, 15, 25)),
    )
    assert tuple(
        (
            orbit.number,
            orbit.ring,
            orbit.representative,
            orbit.material,
            orbit.positions,
        )
        for orbit in ORBITS.ORBITS
    ) == expected


def test_members_follow_d3_formula_and_cover_91_positions_once() -> None:
    expected_positions = {
        (ring, position)
        for ring, count in enumerate(ORBITS.RING_POSITION_COUNTS)
        for position in range(count)
    }
    members = [member for orbit in ORBITS.ORBITS for member in orbit.members]
    assert len(members) == 91
    assert len(set(members)) == 91
    assert set(members) == expected_positions

    for orbit in ORBITS.ORBITS:
        assert orbit.positions == ORBITS.generated_members(
            orbit.ring, orbit.representative
        )
        for ring, position in orbit.members:
            assert ring == orbit.ring
            assert ORBITS.canonical_residue(ring, position) == orbit.representative
            assert ORBITS.orbit_for_position(ring, position) is orbit


def test_orbits_do_not_cross_materials_and_restore_declared_counts() -> None:
    assert {orbit.material for orbit in ORBITS.ORBITS} == ORBITS.MATERIALS
    weighted_counts = Counter()
    for orbit in ORBITS.ORBITS:
        assert {
            ORBITS.material_for_position(orbit.ring, position)
            for position in orbit.positions
        } == {orbit.material}
        weighted_counts[orbit.material] += orbit.multiplicity
    assert weighted_counts == {
        "INT": 28,
        "EXT": 24,
        "CSD": 6,
        "DSDF": 3,
        "PNL": 30,
    }


def test_91_entry_mixture_map_and_volume_helpers() -> None:
    assert len(ORBITS.POSITION_ORDER) == 91
    assert len(ORBITS.MIXTURE_MAP) == 91
    assert set(ORBITS.MIXTURE_MAP) == set(range(1, 22))
    assert ORBITS.MIXTURE_MAP == tuple(
        ORBITS.orbit_for_position(ring, position).number
        for ring, position in ORBITS.POSITION_ORDER
    )
    assert sum(ORBITS.orbit_multiplicities()) == 91
    assert ORBITS.uniform_orbit_volumes(2.5) == tuple(
        2.5 * orbit.multiplicity for orbit in ORBITS.ORBITS
    )
    assert ORBITS.aggregate_position_volumes([2.5] * 91) == (
        ORBITS.uniform_orbit_volumes(2.5)
    )
    with pytest.raises(ValueError, match="expected 91"):
        ORBITS.aggregate_position_volumes([1.0] * 90)


def test_13_local_signatures_are_a_coarser_partition_than_global_orbits() -> None:
    signature_by_position = {
        (ring, position): TOPOLOGY.signature_for_position(ring, position).id
        for ring, count in enumerate(ORBITS.RING_POSITION_COUNTS)
        for position in range(count)
    }

    # Each strict global D3 orbit has one local environment, but several local
    # signatures combine distinct global orbits.  Thus 13 local signatures are
    # not interchangeable with the 21 full-core symmetry orbits.
    orbit_signature = {}
    for orbit in ORBITS.ORBITS:
        signatures = {signature_by_position[member] for member in orbit.members}
        assert len(signatures) == 1
        orbit_signature[orbit.number] = signatures.pop()

    global_orbits_per_local_signature = Counter(orbit_signature.values())
    assert global_orbits_per_local_signature == {
        "intr0_s1": 1,
        "dsdfr1_s1": 1,
        "intr1_s1": 1,
        "intr2_s1": 1,
        "intr2_s2": 1,
        "intr2_s3": 1,
        "csdr3_s1": 2,
        "intr3_s1": 2,
        "extr4_s1": 2,
        "extr4_s2": 2,
        "extr4_s3": 1,
        "pnlr5_s1": 4,
        "pnlr5_s2": 2,
    }
    assert len(global_orbits_per_local_signature) == 13
    assert sum(global_orbits_per_local_signature.values()) == 21
