from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile


def _layout_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "irena30_native_fullcore"
        / "layout.py"
    )
    spec = importlib.util.spec_from_file_location("_irena_native_fullcore_layout", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _native_deck_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "irena30_sph_stage2_csd"
        / "write_native_sph_deck.py"
    )
    spec = importlib.util.spec_from_file_location("_irena_native_sph_deck", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _topology_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "irena30_native_fullcore"
        / "topology.py"
    )
    spec = importlib.util.spec_from_file_location("_irena_native_topology", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_irena_map_is_example_specific_91_position_declaration() -> None:
    positions = _layout_module().declared_positions()
    assert len(positions) == 91
    assert positions[0] == ("R0P00_INT", "INT")
    assert positions[1:7] == (
        ("R1P00_DSDF", "DSDF"),
        ("R1P01_INT", "INT"),
        ("R1P02_DSDF", "DSDF"),
        ("R1P03_INT", "INT"),
        ("R1P04_DSDF", "DSDF"),
        ("R1P05_INT", "INT"),
    )
    counts = {
        name: sum(component == name for _position, component in positions)
        for name in ("INT", "EXT", "CSD", "DSDF", "PNL")
    }
    assert counts == {"INT": 28, "EXT": 24, "CSD": 6, "DSDF": 3, "PNL": 30}


def test_decks_use_component_positions_without_fullcore_sph_or_adf() -> None:
    text = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "irena30_native_fullcore"
        / "write_donjon_decks.py"
    ).read_text(encoding="utf-8")
    assert "HEXZ 91 1" in text
    assert "MERG MIX COND SAVE" in text
    assert "MODULE GEO: SNT:" in text
    assert "MODULE GEO: TRIVAT:" in text
    assert "SPH:" not in text
    assert "ADF" not in text


def test_native_sph_deck_defaults_to_sn_p1_transport_equivalence() -> None:
    module = _native_deck_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "native.x2m"
        assert module.main(
            [
                "--case",
                "int_ext",
                "--reference",
                str(root / "reference.txt"),
                "--sph-output",
                str(root / "sph.txt"),
                "--verify-output",
                str(root / "verify.txt"),
                "--output",
                str(output),
                "--side",
                "10.1036",
            ]
        ) == 0
        text = output.read_text(encoding="utf-8")
        assert "TRACK := SNT: GEOM" in text
        assert "SN 8 SCAT 2" in text
        assert "LIVO 3 3 MAXI 1000 EPSI 1.0E-08" in text
        assert "GMRES" not in text
        assert "MACRO SN STD" in text
        assert "SYSTEM := ASM:" in text


def test_native_sph_deck_can_use_hexagonal_dsa_without_relaxing_tolerances() -> None:
    module = _native_deck_module()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        output = root / "native_dsa.x2m"
        assert module.main(
            [
                "--case",
                "csd_int",
                "--reference",
                str(root / "reference.txt"),
                "--sph-output",
                str(root / "sph.txt"),
                "--verify-output",
                str(root / "verify.txt"),
                "--output",
                str(output),
                "--side",
                "10.1036",
                "--sn-acceleration",
                "dsa",
            ]
        ) == 0
        text = output.read_text(encoding="utf-8")
        assert "DSA 5 0 2 MAXI 1000 EPSI 1.0E-08" in text
        assert "GMRES" not in text
        assert "EDIT 4 MACRO SN STD ITER 300 1.0E-06 MAXNB 20" in text
        assert (
            "EDIT 0 TYPE K EXTE 500 1.0E-7 THER 1000 1.0E-8 "
            "UNKT 1.0E-8"
        ) in text


def test_irena_topology_has_thirteen_example_specific_signatures() -> None:
    topology = _topology_module()
    assert topology.SIGNATURE_EQUIVALENCE == "dihedral-rotation-and-reflection"
    assert len(topology.SIGNATURES) == 13
    assert len(topology.declared_signature_positions()) == 91
    counts = {
        signature.id: sum(
            selected == signature.id
            for _position, selected in topology.declared_signature_positions()
        )
        for signature in topology.SIGNATURES
    }
    assert counts == {
        "intr0_s1": 1,
        "dsdfr1_s1": 3,
        "intr1_s1": 3,
        "intr2_s1": 3,
        "intr2_s2": 3,
        "intr2_s3": 6,
        "csdr3_s1": 6,
        "intr3_s1": 12,
        "extr4_s1": 12,
        "extr4_s2": 6,
        "extr4_s3": 6,
        "pnlr5_s1": 24,
        "pnlr5_s2": 6,
    }
    assert topology.BY_ID["pnlr5_s2"].mix_map == (1, 2, 3, 0, 0, 0, 4)
