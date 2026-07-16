from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import sys
import tempfile

import pytest


def _deck_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "irena30_native_fullcore"
        / "write_fullcore_native_sph_deck.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_irena_fullcore_native_sph_deck", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _global_orbits_module():
    path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "irena30_native_fullcore"
        / "global_orbits.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_irena_global_orbits_for_deck_test", path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments(output: Path) -> list[str]:
    return [
        "--reference",
        "inputs/o2d_fc_ref.txt",
        "--sph-output",
        "outputs/o2d_fc_sph.txt",
        "--verify-output",
        "outputs/o2d_fc_verify.txt",
        "--region-verify-output",
        "outputs/o2d_fc_region.txt",
        "--edi-output",
        "outputs/o2d_fc_power.edi",
        "--output",
        str(output),
    ]


def test_writes_strict_91_position_fullcore_native_sph_deck() -> None:
    module = _deck_module()
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "nested" / "fullcore_native_sph.x2m"
        assert module.main(_arguments(output)) == 0
        text = output.read_text(encoding="utf-8")

    assert "GEOM := GEO: :: HEXZ 91 1 EDIT 1" in text
    assert "Z- REFL Z+ REFL" in text
    assert "HBC COMPLETE VOID" in text
    assert "SIDE 10.103629710818451 SPLITL 2" in text
    assert "MESHZ 0.0 10.0" in text
    assert "91 independent position mixtures" in text

    geometry = re.search(
        r"GEOM := GEO: :: HEXZ 91 1 EDIT 1\n(?P<body>.*?)\n;",
        text,
        flags=re.DOTALL,
    )
    assert geometry is not None
    mixture_text = geometry.group("body").split("\n  MIX\n", 1)[1]
    assert [int(value) for value in mixture_text.split()] == list(range(1, 92))

    assert "TRACK := SNT: GEOM" in text
    assert "EDIT 1 DIAM 1 SN 8 SCAT 2" in text
    assert "LIVO 3 3 MAXI 1000 EPSI 1.0E-08" in text
    assert "GMRES" not in text
    assert "EDIT 4 MACRO SN STD ITER 300 1.0E-06 MAXNB 20" in text
    assert "SYSTEM := ASM: MACROSPH TRACK :: ARM" in text
    assert (
        "EDIT 0 TYPE K EXTE 500 1.0E-07 THER 1000 1.0E-08 "
        "UNKT 1.0E-08"
    ) in text

    assert "VERIFY := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG MIX" in text
    assert "REGVERIFY := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG IN" in text
    assert "EDIRES := EDI: MACROSPH TRACK FLUX :: EDIT 2 MERG MIX COND SAVE" in text
    assert "91 physical HEXZ positions for power validation" in text
    assert "21-orbit aggregate in d3-orbits mode and is balance-only" in text
    assert "never be expanded and used as a 91-position power" in text
    assert "SPH_ASC := MACROSPH" in text
    assert "VERIFY_ASC := VERIFY" in text
    assert "REGION_ASC := REGVERIFY" in text
    assert "EDI_ASC := EDIRES" in text
    assert "TRIVAT:" not in text
    assert " SPN " not in text
    assert "ADF" not in text


def test_d3_mapping_repeats_exact_21_global_orbits_over_91_regions() -> None:
    module = _deck_module()
    orbits = _global_orbits_module()
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "fullcore_d3_native_sph.x2m"
        args = _arguments(output)
        args.extend(("--mapping", "d3-orbits"))
        assert module.main(args) == 0
        text = output.read_text(encoding="utf-8")

    geometry = re.search(
        r"GEOM := GEO: :: HEXZ 91 1 EDIT 1\n(?P<body>.*?)\n;",
        text,
        flags=re.DOTALL,
    )
    assert geometry is not None
    mixture_text = geometry.group("body").split("\n  MIX\n", 1)[1]
    assert tuple(int(value) for value in mixture_text.split()) == orbits.MIXTURE_MAP
    assert len(orbits.MIXTURE_MAP) == 91
    assert set(orbits.MIXTURE_MAP) == set(range(1, 22))
    assert "21 global D3 symmetry-orbit mixtures" in text
    assert "91 independent position mixtures" not in text
    assert "VERIFY := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG MIX" in text
    assert "REGVERIFY := OUT: FLUX GEOM MACROSPH TRACK :: EDIT 0 INTG IN" in text


@pytest.mark.parametrize(
    "option",
    (
        "--reference",
        "--sph-output",
        "--verify-output",
        "--region-verify-output",
        "--edi-output",
    ),
)
def test_rejects_absolute_seq_ascii_paths(option: str) -> None:
    module = _deck_module()
    with tempfile.TemporaryDirectory() as tmp:
        args = _arguments(Path(tmp) / "deck.x2m")
        args[args.index(option) + 1] = "/tmp/outside.txt"
        with pytest.raises(SystemExit) as exc:
            module.main(args)
    assert exc.value.code == 2


def test_rejects_seq_ascii_paths_over_conservative_limit() -> None:
    module = _deck_module()
    with tempfile.TemporaryDirectory() as tmp:
        args = _arguments(Path(tmp) / "deck.x2m")
        args[args.index("--verify-output") + 1] = "outputs/" + "v" * 60
        assert len(args[args.index("--verify-output") + 1]) > 64
        with pytest.raises(SystemExit) as exc:
            module.main(args)
    assert exc.value.code == 2


def test_rejects_parent_traversal_seq_ascii_path() -> None:
    module = _deck_module()
    with tempfile.TemporaryDirectory() as tmp:
        args = _arguments(Path(tmp) / "deck.x2m")
        args[args.index("--reference") + 1] = "../outside.txt"
        with pytest.raises(SystemExit) as exc:
            module.main(args)
    assert exc.value.code == 2
