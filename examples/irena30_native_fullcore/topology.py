"""IRENA-specific local-environment signatures for its declared 91-node core.

The product does not assume thirteen signatures.  These records are the exact
dihedrally canonical (rotation plus reflection) center-and-six-neighbor classes
of this one benchmark.  Neighbor order follows the explicit-seven OpenMC
model.  Reflection is permitted here only because every declared IRENA
component has the corresponding mirror symmetry and the final library consumes
the center mixture.  A directional or chiral component must instead preserve
the reflection permutation or use the fifteen rotation-only classes.
"""

from __future__ import annotations

from dataclasses import dataclass


MATERIALS = frozenset({"INT", "EXT", "CSD", "DSDF", "PNL", "OUT"})
SIGNATURE_EQUIVALENCE = "dihedral-rotation-and-reflection"


@dataclass(frozen=True)
class LocalSignature:
    id: str
    center: str
    neighbors: tuple[str, str, str, str, str, str]
    ring: int

    def __post_init__(self) -> None:
        if self.center not in MATERIALS - {"OUT"}:
            raise ValueError(f"invalid center material for {self.id}: {self.center}")
        if len(self.neighbors) != 6 or any(
            material not in MATERIALS for material in self.neighbors
        ):
            raise ValueError(f"invalid six-neighbor signature: {self.id}")

    @property
    def active_count(self) -> int:
        return 1 + sum(material != "OUT" for material in self.neighbors)

    @property
    def mix_map(self) -> tuple[int, ...]:
        """Return seven HEX mixture ids, using zero for physical OUT slots."""

        result = [1]
        next_mix = 2
        for material in self.neighbors:
            if material == "OUT":
                result.append(0)
            else:
                result.append(next_mix)
                next_mix += 1
        return tuple(result)


SIGNATURES = (
    LocalSignature("intr0_s1", "INT", ("DSDF", "INT", "DSDF", "INT", "DSDF", "INT"), 0),
    LocalSignature("dsdfr1_s1", "DSDF", ("INT", "INT", "INT", "INT", "INT", "INT"), 1),
    LocalSignature("intr1_s1", "INT", ("DSDF", "INT", "DSDF", "INT", "INT", "INT"), 1),
    LocalSignature("intr2_s1", "INT", ("CSD", "INT", "INT", "DSDF", "INT", "INT"), 2),
    LocalSignature("intr2_s2", "INT", ("CSD", "INT", "INT", "INT", "INT", "INT"), 2),
    LocalSignature("intr2_s3", "INT", ("DSDF", "INT", "INT", "INT", "INT", "INT"), 2),
    LocalSignature("csdr3_s1", "CSD", ("EXT", "EXT", "EXT", "INT", "INT", "INT"), 3),
    LocalSignature("intr3_s1", "INT", ("CSD", "EXT", "EXT", "INT", "INT", "INT"), 3),
    LocalSignature("extr4_s1", "EXT", ("CSD", "EXT", "PNL", "PNL", "EXT", "INT"), 4),
    LocalSignature("extr4_s2", "EXT", ("CSD", "EXT", "PNL", "PNL", "PNL", "EXT"), 4),
    LocalSignature("extr4_s3", "EXT", ("EXT", "INT", "INT", "EXT", "PNL", "PNL"), 4),
    LocalSignature("pnlr5_s1", "PNL", ("EXT", "EXT", "PNL", "OUT", "OUT", "PNL"), 5),
    LocalSignature("pnlr5_s2", "PNL", ("EXT", "PNL", "OUT", "OUT", "OUT", "PNL"), 5),
)

BY_ID = {signature.id: signature for signature in SIGNATURES}
if len(BY_ID) != len(SIGNATURES):
    raise RuntimeError("IRENA local signature ids must be unique")


def signature_for_position(ring: int, position: int) -> LocalSignature:
    if ring == 0 and position == 0:
        return BY_ID["intr0_s1"]
    if ring == 1 and 0 <= position < 6:
        return BY_ID["dsdfr1_s1" if position % 2 == 0 else "intr1_s1"]
    if ring == 2 and 0 <= position < 12:
        if position % 4 == 0:
            return BY_ID["intr2_s1"]
        if position % 4 == 2:
            return BY_ID["intr2_s2"]
        return BY_ID["intr2_s3"]
    if ring == 3 and 0 <= position < 18:
        return BY_ID["csdr3_s1" if position % 3 == 0 else "intr3_s1"]
    if ring == 4 and 0 <= position < 24:
        if position % 2 == 1:
            return BY_ID["extr4_s1"]
        if position % 4 == 0:
            return BY_ID["extr4_s2"]
        return BY_ID["extr4_s3"]
    if ring == 5 and 0 <= position < 30:
        return BY_ID["pnlr5_s2" if position % 5 == 0 else "pnlr5_s1"]
    raise ValueError(f"invalid IRENA ring position: r{ring}p{position}")


def declared_signature_positions() -> tuple[tuple[str, str], ...]:
    positions = []
    for ring, count in enumerate((1, 6, 12, 18, 24, 30)):
        for position in range(count):
            signature = signature_for_position(ring, position)
            positions.append(
                (f"R{ring}P{position:02d}_{signature.center}", signature.id)
            )
    if len(positions) != 91:
        raise RuntimeError("IRENA signature map must contain 91 positions")
    return tuple(positions)
