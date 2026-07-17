"""MGXS HDF5 inspection routes for the localhost web UI."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from ..constants import MGXS_DONJON_GROUP_ORDER
from ..energy_groups import identify_mesh
from ..hdf5_names import decode_hdf5_names, read_mixture_names
from ..mgxs_input_contract import scatter_axes as contract_scatter_axes
from ..mgxs_input_contract import sorted_state_names, validate_production_input
from ..mgxs_input_report import input_report_payload
from ..mgxs_inspect import _report_payload, inspect_file
from ..mgxs_physics_checks import scatter_moment_matrix
from ..openmc_provenance import read_openmc_provenance
from .filesystem import FilesystemScope
from .fixtures import load_fixture


INSPECT_SCHEMA = "openmc2donjon.mgxs-inspect.v1"
MIXTURE_SCHEMA = "openmc2donjon.mgxs-mixture.v1"

# Hard caps on the ``/api/inspect`` peek panel so a pathological HDF5
# (hundreds of root attrs, thousands of top-level datasets) can't blow
# up the response payload or the frontend layout. The totals stay
# accurate so the UI can honestly say "showing 200 of 1432 entries".
_PEEK_MAX_ROOT_ATTRS = 50
_PEEK_MAX_TOP_LEVEL_KEYS = 200

# Canonical names shown by Inspect and their accepted HDF5 spellings.  The
# H-factor aliases deliberately use the same preference order as conversion,
# so Inspect shows the data Converter will consume when a legacy file happens
# to carry more than one spelling.
_MIXTURE_XS_DATASET_ALIASES: dict[str, tuple[str, ...]] = {
    "total": ("total",),
    "transport_total": ("transport_total",),
    "absorption": ("absorption",),
    "fission": ("fission",),
    "nu_fission": ("nu_fission",),
    "chi": ("chi",),
    "kappa_fission": (
        "h_factor",
        "H-FACTOR",
        "H_FACTOR",
        "kappa_fission",
        "kappa_fission_xs",
        "kappa_fission_cross_section",
    ),
    "inverse_velocity": (
        "inverse_velocity",
        "inverse-velocity",
        "OVERV",
        "overv",
    ),
    "flux_weight": ("flux_weight", "flux", "flux_integral"),
    "sph": ("sph", "SPH", "NSPH"),
}


def register_inspect_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope,
) -> None:
    """Register MGXS inspection endpoints."""

    from fastapi import HTTPException, Query

    @app.get("/api/inspect")
    def api_inspect(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            payload = load_fixture("inspect_handoff.json")
            # Echo the requested path (live mode echoes the resolved
            # real path below) so the result header names the file the
            # user actually asked for.
            payload["path"] = path
            # The requested path is deliberately not read in mock mode.  Carry
            # that fact in the result itself so a screenshot or exported UI
            # state cannot be mistaken for evidence from the named file.
            payload["mock_mode"] = True
            payload.setdefault("production_audit", None)
            return payload
        real_path = _validate_hdf5_path(path, HTTPException, filesystem_scope)
        try:
            report = inspect_file(real_path)
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(
                status_code=422, detail=f"inspect failed: {exc}"
            ) from exc
        payload = _report_payload(report)
        payload["schema"] = INSPECT_SCHEMA
        payload["mock_mode"] = False
        bounds, mesh_match = _read_bounds_and_mesh(real_path)
        payload["energy_bounds"] = bounds
        payload["mesh_match"] = mesh_match
        # Generic HDF5 peek (root attrs + top-level entries) makes the
        # response useful even for files that don't match the MGXS
        # contract (boundary currents, ADF sidecars, etc.): the user
        # at least sees what KIND of HDF5 they pointed at instead of
        # a bare "0 mixtures, FAIL".
        payload.update(_read_top_level_peek(real_path))
        payload["openmc_provenance"] = read_openmc_provenance(real_path)
        payload["production_audit"] = input_report_payload(
            validate_production_input(real_path)
        )
        return payload

    @app.get("/api/inspect/mixture")
    def api_inspect_mixture(
        path: str = Query(..., min_length=1),
        mixture: str = Query(..., min_length=1),
        moment: int = Query(0, ge=0),
        state: str | None = Query(None, min_length=1),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_mixture(mixture, moment, state, HTTPException)
        real_path = _validate_hdf5_path(path, HTTPException, filesystem_scope)
        try:
            return _read_mixture_detail(
                real_path,
                mixture,
                moment,
                state,
                HTTPException,
            )
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"mixture read failed: {exc}"
            ) from exc


def _validate_hdf5_path(
    raw: str,
    http_exception: Any,
    filesystem_scope: FilesystemScope,
) -> Path:
    """Resolve a user-supplied path and confirm it is a readable HDF5 file."""

    import h5py

    real = filesystem_scope.resolve(raw, http_exception)
    if not real.exists():
        raise http_exception(status_code=404, detail=f"path not found: {raw}")
    if not real.is_file():
        raise http_exception(status_code=400, detail=f"path is not a file: {raw}")
    try:
        is_hdf5 = h5py.is_hdf5(str(real))
    except OSError as exc:
        raise http_exception(
            status_code=403, detail=f"cannot read path: {exc}"
        ) from exc
    if not is_hdf5:
        raise http_exception(status_code=400, detail=f"not an HDF5 file: {raw}")
    return real


def _read_top_level_peek(real_path: Path) -> dict[str, Any]:
    """Read root attrs and one-level group/dataset names for a peek panel.

    Returns empty lists / zero totals if the file can't be opened.
    """

    import h5py

    empty = {
        "root_attrs": [],
        "top_level_keys": [],
        "root_attrs_total": 0,
        "top_level_keys_total": 0,
        "peek_truncated": False,
    }
    try:
        with h5py.File(real_path, "r") as h5:
            attr_names = list(h5.attrs.keys())
            root_attrs: list[dict[str, Any]] = []
            for name in attr_names:
                if len(root_attrs) >= _PEEK_MAX_ROOT_ATTRS:
                    break
                value = _attr_to_jsonable(h5.attrs[name])
                if value is None:
                    continue
                root_attrs.append({"name": str(name), "value": value})

            all_top_names = sorted(h5)
            top_level_keys: list[dict[str, Any]] = []
            for name in all_top_names[:_PEEK_MAX_TOP_LEVEL_KEYS]:
                node = h5[name]
                if isinstance(node, h5py.Group):
                    top_level_keys.append(
                        {
                            "name": str(name),
                            "kind": "group",
                            "shape": None,
                            "dtype": None,
                        }
                    )
                else:
                    dataset = node
                    try:
                        shape = list(dataset.shape)
                        dtype = str(dataset.dtype)
                    except (AttributeError, OSError):
                        shape = None
                        dtype = None
                    top_level_keys.append(
                        {
                            "name": str(name),
                            "kind": "dataset",
                            "shape": shape,
                            "dtype": dtype,
                        }
                    )
            root_attrs_total = len(attr_names)
            top_level_keys_total = len(all_top_names)
    except (OSError, ValueError, KeyError):
        return empty
    return {
        "root_attrs": root_attrs,
        "top_level_keys": top_level_keys,
        "root_attrs_total": root_attrs_total,
        "top_level_keys_total": top_level_keys_total,
        "peek_truncated": (
            len(root_attrs) < root_attrs_total
            or len(top_level_keys) < top_level_keys_total
        ),
    }


def _attr_to_jsonable(value: Any) -> Any:
    """Convert an HDF5 attribute value to a JSON-friendly scalar.

    Returns ``None`` for blobs we don't want to ship (large arrays,
    unsupported dtypes), the caller will skip them. Bytes / numpy
    strings are decoded; numpy scalars are unwrapped via ``.item()``.
    """

    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, str):
        return value
    if hasattr(value, "item") and not hasattr(value, "shape"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            return None
    if hasattr(value, "shape"):
        shape = value.shape
        if shape == ():
            try:
                return _attr_to_jsonable(value.item())
            except (AttributeError, ValueError):
                return None
        if len(shape) == 1 and shape[0] <= 8:
            # Short 1D vectors render nicely as a list (energy bounds,
            # small enumerations, etc.); anything bigger gets dropped
            # to keep the peek payload bounded.
            try:
                return [_attr_to_jsonable(v) for v in value.tolist()]
            except (AttributeError, ValueError):
                return None
        return None
    if isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, (list, tuple)) and len(value) <= 8:
        return [_attr_to_jsonable(v) for v in value]
    return None


def _read_bounds_and_mesh(
    real_path: Path,
) -> tuple[list[float] | None, dict[str, Any] | None]:
    """Read ``/energy_bounds`` once and reuse it for mesh ID detection."""

    import h5py

    try:
        with h5py.File(real_path, "r") as h5:
            if "energy_bounds" not in h5 or not isinstance(
                h5["energy_bounds"], h5py.Dataset
            ):
                return None, None
            bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    except (OSError, KeyError, TypeError, ValueError):
        return None, None
    bounds_list = bounds.tolist()
    mesh = identify_mesh(bounds)
    if mesh is None:
        return bounds_list, None
    return bounds_list, {
        "id": mesh.mesh_id,
        "name": mesh.name,
        "short": mesh.short,
        "n_groups": mesh.n_groups,
        "purpose": mesh.purpose,
        "description": mesh.description,
    }


def _read_mixture_detail(
    real_path: Path,
    mixture_name: str,
    moment: int,
    state: str | None,
    http_exception: Any,
) -> dict[str, Any]:
    """Pull per-mixture cross sections and one scatter moment out of HDF5."""

    import h5py

    with h5py.File(real_path, "r") as h5:
        mixtures = h5.get("mixtures")
        if mixtures is None:
            raise http_exception(
                status_code=422, detail="HDF5 has no /mixtures group"
            )
        mix_group = mixtures.get(mixture_name)
        if mix_group is None:
            raise http_exception(
                status_code=404,
                detail=f"mixture not found: {mixture_name}",
            )

        available_states, selected_state, calculation_group = (
            _select_calculation_group(
                mix_group,
                mixture_name=mixture_name,
                requested_state=state,
                http_exception=http_exception,
            )
        )

        ngroups_attr = h5.attrs.get("energy_groups")
        try:
            ngroups = int(ngroups_attr) if ngroups_attr is not None else None
        except (TypeError, ValueError):
            ngroups = None

        legendre_attr = h5.attrs.get("legendre_order")
        try:
            legendre_order = int(legendre_attr) if legendre_attr is not None else None
        except (TypeError, ValueError):
            legendre_order = None

        cross_sections, cross_section_std_dev = _read_cross_sections(
            calculation_group,
            ngroups=ngroups,
        )

        parent_attrs = (
            mix_group.attrs if calculation_group is not mix_group else None
        )
        volume = _float_attr(calculation_group.attrs, "volume", parent_attrs)
        temperature = _float_attr(
            calculation_group.attrs,
            "temperature",
            parent_attrs,
        )
        fissionable = _bool_attr(
            calculation_group.attrs,
            "fissionable",
            parent_attrs,
        )

        scatter_payload = _scatter_moment_payload(
            calculation_group,
            h5=h5,
            parent_group=(
                mix_group if calculation_group is not mix_group else None
            ),
            ngroups=ngroups,
            legendre_order=legendre_order,
            moment=moment,
        )
        if scatter_payload is not None and not scatter_payload.get("values"):
            # Requested moment out of range; surface it as a 404 so the
            # frontend can fall back to moment=0 rather than render an
            # empty heatmap.
            raise http_exception(
                status_code=404,
                detail=(
                    f"scatter moment {moment} not available for "
                    f"mixture {mixture_name}"
                ),
            )

        volume_flux, volume_flux_std_dev = _read_openmc_volume_flux_row(
            h5,
            mixture_name=mixture_name,
            ngroups=ngroups,
        )

        return {
            "schema": MIXTURE_SCHEMA,
            "path": str(real_path),
            "mixture": mixture_name,
            "available_states": available_states,
            "selected_state": selected_state,
            "energy_groups": ngroups,
            "legendre_order": legendre_order,
            "volume": volume,
            "temperature": temperature,
            "fissionable": fissionable,
            "cross_sections": cross_sections,
            "cross_section_std_dev": cross_section_std_dev,
            "openmc_volume_flux": volume_flux,
            "openmc_volume_flux_std_dev": volume_flux_std_dev,
            "openmc_volume_flux_scope": (
                "file-global" if volume_flux is not None else None
            ),
            "scatter": scatter_payload,
        }


def _select_calculation_group(
    mix_group: Any,
    *,
    mixture_name: str,
    requested_state: str | None,
    http_exception: Any,
) -> tuple[list[str], str | None, Any]:
    """Resolve a direct-mixture or ``states/<state>`` calculation group."""

    import h5py

    if "states" not in mix_group:
        if requested_state is not None:
            raise http_exception(
                status_code=404,
                detail=(
                    f"state not found for direct mixture {mixture_name}: "
                    f"{requested_state}"
                ),
            )
        return [], None, mix_group

    states = mix_group["states"]
    if not isinstance(states, h5py.Group):
        raise ValueError(f"mixture {mixture_name}: states is not an HDF5 group")
    available = sorted_state_names(states)
    if not available:
        raise ValueError(f"mixture {mixture_name}: states group is empty")
    selected = requested_state if requested_state is not None else available[0]
    if selected not in states:
        raise http_exception(
            status_code=404,
            detail=f"state not found for mixture {mixture_name}: {selected}",
        )
    calculation = states[selected]
    if not isinstance(calculation, h5py.Group):
        raise ValueError(
            f"mixture {mixture_name}: state {selected} is not an HDF5 group"
        )
    return available, selected, calculation


def _read_cross_sections(
    calculation_group: Any,
    *,
    ngroups: int | None,
) -> tuple[dict[str, list[float] | None], dict[str, list[float] | None]]:
    """Read canonical mixture vectors and their matching uncertainties."""

    import h5py

    means: dict[str, list[float] | None] = {}
    std_devs: dict[str, list[float] | None] = {}
    for canonical, aliases in _MIXTURE_XS_DATASET_ALIASES.items():
        source_name = next(
            (name for name in aliases if name in calculation_group),
            None,
        )
        if source_name is None:
            means[canonical] = None
            std_devs[canonical] = None
            continue
        source = calculation_group[source_name]
        if not isinstance(source, h5py.Dataset):
            raise ValueError(
                f"{calculation_group.name}/{source_name} is not an HDF5 dataset"
            )
        means[canonical] = _float_vector(
            source,
            expected_length=ngroups,
            label=f"{calculation_group.name}/{source_name}",
        )

        std_name = next(
            (
                name
                for name in dict.fromkeys(
                    (f"{source_name}_std_dev", f"{canonical}_std_dev")
                )
                if name in calculation_group
            ),
            None,
        )
        if std_name is None:
            std_devs[canonical] = None
            continue
        std_dataset = calculation_group[std_name]
        if not isinstance(std_dataset, h5py.Dataset):
            raise ValueError(
                f"{calculation_group.name}/{std_name} is not an HDF5 dataset"
            )
        if std_dataset.shape != source.shape:
            raise ValueError(
                f"{calculation_group.name}/{std_name}: shape "
                f"{std_dataset.shape} must match {source_name} shape {source.shape}"
            )
        std_devs[canonical] = _float_vector(
            std_dataset,
            expected_length=ngroups,
            label=f"{calculation_group.name}/{std_name}",
            nonnegative=True,
        )
    return means, std_devs


def _float_vector(
    dataset: Any,
    *,
    expected_length: int | None,
    label: str,
    nonnegative: bool = False,
) -> list[float]:
    """Read one physical group vector without repairing an invalid shape."""

    values = np.asarray(dataset[:], dtype=float)
    expected_shape = (
        (expected_length,) if expected_length is not None else None
    )
    if values.ndim != 1 or (
        expected_shape is not None and values.shape != expected_shape
    ):
        expected = (
            "a one-dimensional group vector"
            if expected_shape is None
            else f"shape {expected_shape}"
        )
        raise ValueError(f"{label}: expected {expected}, got {values.shape}")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label}: group vector contains non-finite values")
    if nonnegative and np.any(values < 0.0):
        raise ValueError(f"{label}: standard deviation contains negative values")
    return values.tolist()


def _read_openmc_volume_flux_row(
    h5: Any,
    *,
    mixture_name: str,
    ngroups: int | None,
) -> tuple[list[float] | None, list[float] | None]:
    """Return the selected mixture's canonical root reference-flux row.

    A row is surfaced only when the matrix shape and any dataset-level name
    declaration agree with the canonical ``/mixture_names`` ordering.  This
    prevents a scientifically dangerous display of another mixture's flux.
    """

    import h5py

    mean = h5.get("openmc_volume_flux")
    if not isinstance(mean, h5py.Dataset):
        return None, None
    try:
        names = read_mixture_names(h5)
    except ValueError:
        return None, None
    if "mixture_names" not in mean.attrs:
        return None, None
    declared = decode_hdf5_names(mean.attrs["mixture_names"])
    if declared != names:
        return None, None
    if _text_attr(mean.attrs, "group_order") != MGXS_DONJON_GROUP_ORDER:
        return None, None
    if (
        mean.ndim != 2
        or mean.shape[0] != len(names)
        or (ngroups is not None and mean.shape[1] != ngroups)
        or mixture_name not in names
    ):
        return None, None

    row_index = names.index(mixture_name)
    mean_values = np.asarray(mean[row_index, :], dtype=float).reshape(-1)
    if not np.all(np.isfinite(mean_values)) or np.any(mean_values <= 0.0):
        raise ValueError(
            "/openmc_volume_flux reference row must contain positive finite values"
        )
    mean_row = mean_values.tolist()

    std_dev = h5.get("openmc_volume_flux_std_dev")
    if not isinstance(std_dev, h5py.Dataset) or std_dev.shape != mean.shape:
        return mean_row, None
    if "mixture_names" not in std_dev.attrs:
        return mean_row, None
    declared_std = decode_hdf5_names(std_dev.attrs["mixture_names"])
    if declared_std != names:
        return mean_row, None
    if _text_attr(std_dev.attrs, "group_order") != MGXS_DONJON_GROUP_ORDER:
        return mean_row, None
    std_values = np.asarray(std_dev[row_index, :], dtype=float).reshape(-1)
    if not np.all(np.isfinite(std_values)) or np.any(std_values < 0.0):
        raise ValueError(
            "/openmc_volume_flux_std_dev row must contain finite non-negative values"
        )
    std_row = std_values.tolist()
    return mean_row, std_row


def _text_attr(attrs: Any, name: str) -> str | None:
    if name not in attrs:
        return None
    value = attrs[name]
    if isinstance(value, (bytes, np.bytes_)):
        return bytes(value).decode("utf-8")
    return str(value)


def _scatter_moment_payload(
    mix_group: Any,
    *,
    h5: Any,
    parent_group: Any | None,
    ngroups: int | None,
    legendre_order: int | None,
    moment: int,
) -> dict[str, Any] | None:
    """Return ``{axes, shape, moment_index, values}`` for one scatter moment.

    Returns ``None`` if the mixture has no scatter dataset at all so the
    endpoint can tell the difference between "no scatter" (None) and
    "moment out of range" (dict with empty ``values``, surfaced as 404).
    """

    import h5py

    if "scatter_matrix" not in mix_group:
        return None
    dataset = mix_group["scatter_matrix"]
    if not isinstance(dataset, h5py.Dataset):
        raise ValueError(f"{mix_group.name}/scatter_matrix is not an HDF5 dataset")
    # Match Converter exactly: calculation → parent mixture → root attrs.
    # Dataset-local ``axes`` metadata is outside the MGXS handoff contract and
    # must not silently make Inspect slice a different moment than Converter.
    axes = contract_scatter_axes(mix_group, h5, parent_group)
    arr = np.asarray(dataset[:], dtype=float)
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{dataset.name}: scatter matrix contains non-finite values")
    shape = list(arr.shape)
    if ngroups is None:
        # Best-effort fall back to whichever symmetric dimension matches.
        candidates = [s for s in shape if s > 0]
        ngroups = candidates[0] if candidates else 0
    effective_order = (
        legendre_order if legendre_order is not None else max(0, shape[0] - 1)
    )
    matrix = _scatter_moment(arr, axes, ngroups, effective_order, moment)
    if matrix is None and moment <= effective_order:
        raise ValueError(
            f"{dataset.name}: shape {arr.shape} is incompatible with "
            f"scatter_axes={axes!r}, {ngroups} groups, and P{effective_order}"
        )
    std_dev_matrix = None
    std_dev_shape = None
    std_dev = mix_group.get("scatter_matrix_std_dev")
    if std_dev is not None:
        if not isinstance(std_dev, h5py.Dataset):
            raise ValueError(
                f"{mix_group.name}/scatter_matrix_std_dev is not an HDF5 dataset"
            )
        std_dev_arr = np.asarray(std_dev[:], dtype=float)
        if std_dev_arr.shape != arr.shape:
            raise ValueError(
                f"{std_dev.name}: shape {std_dev_arr.shape} must match "
                f"scatter_matrix shape {arr.shape}"
            )
        if not np.all(np.isfinite(std_dev_arr)):
            raise ValueError(
                f"{std_dev.name}: standard deviation contains non-finite values"
            )
        if np.any(std_dev_arr < 0.0):
            raise ValueError(
                f"{std_dev.name}: standard deviation contains negative values"
            )
        std_dev_shape = list(std_dev_arr.shape)
        std_dev_matrix = _scatter_moment(
            std_dev_arr,
            axes,
            ngroups,
            effective_order,
            moment,
        )
        if std_dev_matrix is None and moment <= effective_order:
            raise ValueError(
                f"{std_dev.name}: shape/axes do not match scatter_matrix"
            )
    return {
        "axes": axes,
        "shape": shape,
        "moment_index": moment,
        "values": matrix.tolist() if matrix is not None else [],
        "std_dev_shape": std_dev_shape,
        "std_dev_values": (
            std_dev_matrix.tolist() if std_dev_matrix is not None else None
        ),
    }


def _scatter_moment(
    values: np.ndarray,
    axes: str | None,
    ngroups: int,
    legendre_order: int,
    moment: int,
) -> np.ndarray | None:
    """Extract P0 from legacy 2-D scatter or delegate normal 3-D layouts."""

    if values.ndim == 2:
        if moment == 0 and values.shape == (ngroups, ngroups):
            return np.asarray(values)
        return None
    return scatter_moment_matrix(
        values,
        axes,
        ngroups,
        legendre_order,
        moment=moment,
    )


def _float_attr(
    attrs: Any,
    name: str,
    parent_attrs: Any | None = None,
) -> float | None:
    source = attrs if name in attrs else parent_attrs
    if source is None or name not in source:
        return None
    try:
        value = float(source[name])
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"attribute {name!r} must be a finite number") from exc
    if not np.isfinite(value):
        raise ValueError(f"attribute {name!r} must be finite")
    return value


def _bool_attr(
    attrs: Any,
    name: str,
    parent_attrs: Any | None = None,
) -> bool | None:
    source = attrs if name in attrs else parent_attrs
    if source is None or name not in source:
        return None
    value = source[name]
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and int(value) in (0, 1):
        return bool(value)
    return None


@lru_cache(maxsize=1)
def _mock_mixture_rows() -> dict[str, dict[str, Any]]:
    """Cached mixture rows from the bundled handoff fixture, by name."""

    handoff = load_fixture("inspect_handoff.json")
    return {mix["name"]: mix for mix in handoff.get("mixtures", [])}


def _mock_mixture(
    mixture: str,
    moment: int,
    state: str | None,
    http_exception: Any,
) -> dict[str, Any]:
    """Serve the bundled per-mixture fixture for any mixture in the handoff.

    Mock mode accepts the 9 mixture names and P0/P1 moments declared in
    the bundled handoff fixture. P1 is synthesized by scaling P0 values
    by 0.1 so the frontend selectors and plot wiring stay exercised
    without shipping a second hand-crafted matrix fixture.
    """

    row = _mock_mixture_rows().get(mixture)
    if row is None:
        raise http_exception(
            status_code=404, detail=f"mixture not found: {mixture}"
        )
    if state is not None:
        raise http_exception(
            status_code=404,
            detail=f"state not found for direct mixture {mixture}: {state}",
        )
    if moment >= 2:
        raise http_exception(
            status_code=404,
            detail=f"scatter moment {moment} not available for mixture {mixture}",
        )

    payload = load_fixture("inspect_mixture.json")
    payload = dict(payload)
    payload["mixture"] = mixture
    payload["available_states"] = []
    payload["selected_state"] = None
    payload["fissionable"] = row.get("fissionable")
    payload["cross_section_std_dev"] = {
        name: None for name in _MIXTURE_XS_DATASET_ALIASES
    }
    payload["openmc_volume_flux"] = None
    payload["openmc_volume_flux_std_dev"] = None
    payload["openmc_volume_flux_scope"] = None
    payload["cross_sections"] = dict(payload["cross_sections"])
    for name in _MIXTURE_XS_DATASET_ALIASES:
        payload["cross_sections"].setdefault(name, None)
    payload["scatter"] = dict(payload["scatter"])
    payload["scatter"].setdefault("std_dev_shape", None)
    payload["scatter"].setdefault("std_dev_values", None)
    # The per-mixture meta must agree with the roster row the user
    # clicked, not the canned M3_MOX_70 values.
    payload["volume"] = row.get("volume", payload["volume"])
    if row.get("fissionable") is False:
        # Strip the fission family so the frontend exercises the
        # null-series guards in both the spectrum and heatmap.
        xs = dict(payload["cross_sections"])
        xs["fission"] = None
        xs["nu_fission"] = None
        xs["chi"] = None
        payload["cross_sections"] = xs
    if moment != 0:
        scatter = dict(payload["scatter"])
        scaled = [[float(v) * 0.1 for v in row] for row in scatter["values"]]
        scatter["values"] = scaled
        scatter["moment_index"] = moment
        payload["scatter"] = scatter
    return payload
