from __future__ import annotations

from collections import Counter
import importlib.util
import os
from pathlib import Path
import sys
import warnings

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "irena30_native_fullcore"
MODEL_PATH = EXAMPLE / "irena_orbit_ce_model.py"
RECIPE_PATH = EXAMPLE / "export_orbit_recipe.py"
BUILDER_PATH = EXAMPLE / "build_orbit_ce_case.py"


def test_strict_orbit_ce_sources_compile_and_declare_physics_contract() -> None:
    model_text = MODEL_PATH.read_text(encoding="utf-8")
    recipe_text = RECIPE_PATH.read_text(encoding="utf-8")
    builder_text = BUILDER_PATH.read_text(encoding="utf-8")
    for path, text in (
        (MODEL_PATH, model_text),
        (RECIPE_PATH, recipe_text),
        (BUILDER_PATH, builder_text),
    ):
        compile(text, str(path), "exec")

    assert 'ENERGY_MESH_ID = "anl_24c_20mev"' in model_text
    assert "HANDOFF_LEGENDRE_ORDER = 1" in model_text
    assert '"consistent nu-scatter matrix"' in model_text
    assert "N_HEXES = 91" in model_text
    assert "N_ORBITS = 21" in model_text
    assert 'boundary = "vacuum" if edge_counts[key] == 1' in model_text
    assert 'boundary_type="reflective"' in model_text
    assert '"coarse_node_side_cm": SIDE_CM' in model_text
    assert "domain_cell.volume = orbit_volume_cm3(orbit)" in model_text
    assert "fill=wrappers[position.orbit_number]" in model_text
    assert "openmc_volume_flux" in model_text
    assert "POSITION_POWER_TALLY_NAME" in model_text
    assert "reference_position_power_count" in model_text
    assert "reference_finite_balance_keff" in model_text
    assert "reference_leakage" in model_text
    assert "post_hoc_cross_section_averaging" in model_text
    assert "_import_exact_ce_compare_module" in model_text
    assert "refusing cached" in model_text


def test_converter_recipe_exposes_strict_orbit_handoff_hooks() -> None:
    text = RECIPE_PATH.read_text(encoding="utf-8")
    assert "from openmc2donjon import DomainExportSpec" in text
    assert "def domain_specs(library):" in text
    assert "volume=_model.orbit_volume_cm3(orbit)" in text
    assert "def scatter_mgxs_type():" in text
    assert 'return "consistent nu-scatter matrix"' in text
    assert "def extra_tallies(library):" in text
    assert "def postprocess_hdf5(" in text
    assert "_model.postprocess_hdf5(" in text


def _load_model():
    spec = importlib.util.spec_from_file_location("_test_irena_orbit_ce_model", MODEL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_optional_openmc_structure_and_xml_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the real structure when the user's OpenMC/IRENA input exists.

    Ordinary CI intentionally has neither dependency; the source-level tests
    above still enforce the public recipe and physics declaration there.
    """

    openmc = pytest.importorskip("openmc")
    ce_compare_root = os.environ.get("IRENA_CE_COMPARE_DIR")
    if not ce_compare_root:
        pytest.skip("IRENA_CE_COMPARE_DIR is not configured")
    ce_compare = Path(ce_compare_root).expanduser().resolve() / "openmc_colorset.py"
    if not ce_compare.is_file():
        pytest.skip("local IRENA ce_compare fine-assembly input is unavailable")
    monkeypatch.setenv("IRENA_CE_COMPARE_DIR", str(ce_compare.parent))

    model = _load_model()
    materials, geometry = model.build_model_parts()
    settings = model.build_settings(
        model.RunSettings(batches=2, inactive=1, particles=10, seed=7)
    )
    assert len(settings.source) == 52
    assert all(source.constraints.get("fissionable") for source in settings.source)
    position_entries = model.core_position_cells(geometry)
    domain_entries = model.orbit_domain_cells(geometry)
    assert len(position_entries) == 91
    assert len(domain_entries) == 21

    wrapper_fill_ids = Counter(int(cell.fill.id) for *_, cell in position_entries)
    assert sorted(wrapper_fill_ids.values()) == sorted(
        orbit.multiplicity for orbit in model.ORBITS.ORBITS
    )
    assert len(wrapper_fill_ids) == 21

    geometry.determine_paths(instances_only=True)
    for orbit, domain in domain_entries:
        assert domain.num_instances == orbit.multiplicity
        assert domain.volume == pytest.approx(model.orbit_volume_cm3(orbit))

    core_surfaces = [
        surface
        for surface in geometry.get_all_surfaces().values()
        if (surface.name or "").startswith("irena_core_face_")
    ]
    assert Counter(surface.boundary_type for surface in core_surfaces) == {
        "transmission": 240,
        "vacuum": 66,
    }
    axial_surfaces = [
        surface
        for surface in geometry.get_all_surfaces().values()
        if (surface.name or "").startswith("irena_core_axial_")
    ]
    assert len(axial_surfaces) == 2
    assert {surface.boundary_type for surface in axial_surfaces} == {"reflective"}

    library = model.build_library(geometry)
    assert len(library.domains) == 21
    assert library.energy_groups.num_groups == 24
    assert library.legendre_order == 1
    assert "consistent nu-scatter matrix" in library.mgxs_types
    assert library.correction is None

    import h5py

    handoff = tmp_path / "provenance_only.h5"
    with h5py.File(handoff, "w"):
        pass
    mixture_names = [model.exported_orbit_name(orbit) for orbit in model.ORBITS.ORBITS]
    model.append_orbit_provenance_hdf5(handoff, library, mixture_names)
    with h5py.File(handoff, "r") as h5:
        provenance = h5["irena_orbit_provenance"]
        assert provenance["position_to_orbit"].shape == (91,)
        assert provenance["multiplicities"][:].sum() == 91
        assert provenance["domain_cell_ids"].shape == (21,)
        assert bool(h5.attrs["orbit_transport_pooling_verified"])
        assert not bool(h5.attrs["post_hoc_cross_section_averaging"])

    fake_position_mean = np.column_stack(
        (np.arange(1.0, 92.0), np.arange(1.0, 92.0) * 0.5)
    )
    fake_position_std = np.full((91, 2), 0.1)
    monkeypatch.setattr(
        model,
        "extract_position_power",
        lambda _statepoint: (fake_position_mean, fake_position_std),
    )
    model.append_position_power_hdf5(handoff, tmp_path / "not-read.h5")
    with h5py.File(handoff, "r") as h5:
        power = h5["openmc_position_power"]
        assert power["mean"].shape == (91, 2)
        assert power["std_dev"].shape == (91, 2)
        assert power["normalized_kappa_fission"].shape == (91,)
        assert np.sum(power["normalized_kappa_fission"][:]) == pytest.approx(1.0)
        assert power["position_orbit_number"].shape == (91,)
        assert power["position_material"].shape == (91,)
        assert not bool(power.attrs["orbit_aggregation_used"])

    reference_tallies = model.build_reference_tallies(geometry)
    names = {tally.name for tally in reference_tallies}
    assert names == {
        model.VOLUME_FLUX_TALLY_NAME,
        model.ENERGY_COVERAGE_TALLY_NAME,
        model.POSITION_POWER_TALLY_NAME,
        model.GLOBAL_BALANCE_TALLY_NAME,
    }
    position_power = next(
        tally for tally in reference_tallies if tally.name == model.POSITION_POWER_TALLY_NAME
    )
    assert len(position_power.filters) == 1
    assert len(position_power.filters[0].bins) == 91
    assert position_power.scores == ["kappa-fission", "fission"]

    # XML export rebuilds an independent model with stable ids.  OpenMC keeps
    # used ids in process-global registries, so reset them between the two
    # models to keep this structural test warning-free.
    openmc.reset_auto_ids()
    case_dir = tmp_path / "ce_case"
    with warnings.catch_warnings():
        # MGXS intentionally constructs repeated compatible filters before
        # OpenMC merges them into the exported Tallies collection.
        warnings.simplefilter("ignore", openmc.IDWarning)
        model.export_ce_xml(
            case_dir,
            model.RunSettings(batches=2, inactive=1, particles=10, seed=7),
        )
    assert {path.name for path in case_dir.iterdir()} == {
        "geometry.xml",
        "materials.xml",
        "settings.xml",
        "tallies.xml",
    }
    geometry_text = (case_dir / "geometry.xml").read_text(encoding="utf-8")
    assert geometry_text.count('name="irena_position_') == 91
    assert geometry_text.count("_domain\"") == 21
    tallies_text = (case_dir / "tallies.xml").read_text(encoding="utf-8")
    assert model.VOLUME_FLUX_TALLY_NAME in tallies_text
    assert model.ENERGY_COVERAGE_TALLY_NAME in tallies_text
    assert model.POSITION_POWER_TALLY_NAME in tallies_text
    assert model.GLOBAL_BALANCE_TALLY_NAME in tallies_text
