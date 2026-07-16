"""Declared IRENA-30 91-position component map.

This is benchmark-specific data, not a product default.  The generic product
operation is ``expand-component-library``; this module supplies only the
position order and component assignments for the IRENA example.
"""

from __future__ import annotations


COMPONENT_ORDER = ("INT", "EXT", "CSD", "DSDF", "PNL")


def ring_labels() -> tuple[tuple[str, ...], ...]:
    return (
        ("INT",),
        tuple("DSDF" if position % 2 == 0 else "INT" for position in range(6)),
        ("INT",) * 12,
        tuple("CSD" if position % 3 == 0 else "INT" for position in range(18)),
        ("EXT",) * 24,
        ("PNL",) * 30,
    )


def declared_positions() -> tuple[tuple[str, str], ...]:
    positions = tuple(
        (f"R{ring}P{position:02d}_{component}", component)
        for ring, labels in enumerate(ring_labels())
        for position, component in enumerate(labels)
    )
    if len(positions) != 91:
        raise RuntimeError(f"IRENA map must contain 91 positions, found {len(positions)}")
    counts = {component: 0 for component in COMPONENT_ORDER}
    for _name, component in positions:
        counts[component] += 1
    expected = {"INT": 28, "EXT": 24, "CSD": 6, "DSDF": 3, "PNL": 30}
    if counts != expected:
        raise RuntimeError(f"IRENA component counts differ: {counts} != {expected}")
    return positions
