"""MGXS HDF5 inspection routes for the localhost web UI."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from ..energy_groups import identify_mesh
from ..mgxs_inspect import _report_payload, inspect_file
from ..mgxs_physics_checks import scatter_moment_matrix
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

# Cross sections to extract when reading per-mixture detail. ``chi`` is
# included so the frontend can show source spectrum alongside reaction
# rates; it lives on a different axis than the absorption / fission
# group so the plot UI should treat it separately.
_MIXTURE_XS_DATASETS: tuple[str, ...] = (
    "total",
    "absorption",
    "fission",
    "nu_fission",
    "chi",
)


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
        bounds, mesh_match = _read_bounds_and_mesh(real_path)
        payload["energy_bounds"] = bounds
        payload["mesh_match"] = mesh_match
        # Generic HDF5 peek (root attrs + top-level entries) makes the
        # response useful even for files that don't match the MGXS
        # contract (boundary currents, ADF sidecars, etc.): the user
        # at least sees what KIND of HDF5 they pointed at instead of
        # a bare "0 mixtures, FAIL".
        payload.update(_read_top_level_peek(real_path))
        return payload

    @app.get("/api/inspect/mixture")
    def api_inspect_mixture(
        path: str = Query(..., min_length=1),
        mixture: str = Query(..., min_length=1),
        moment: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_mixture(mixture, moment, HTTPException)
        real_path = _validate_hdf5_path(path, HTTPException, filesystem_scope)
        try:
            return _read_mixture_detail(real_path, mixture, moment, HTTPException)
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
            if "energy_bounds" not in h5:
                return None, None
            bounds = np.asarray(h5["energy_bounds"][:], dtype=float)
    except (OSError, KeyError, ValueError):
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

        cross_sections: dict[str, list[float] | None] = {}
        for name in _MIXTURE_XS_DATASETS:
            if name in mix_group:
                cross_sections[name] = np.asarray(
                    mix_group[name][:], dtype=float
                ).reshape(-1).tolist()
            else:
                cross_sections[name] = None

        volume = _float_attr(mix_group.attrs, "volume")
        temperature = _float_attr(mix_group.attrs, "temperature")

        scatter_payload = _scatter_moment_payload(
            mix_group,
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

        return {
            "schema": MIXTURE_SCHEMA,
            "path": str(real_path),
            "mixture": mixture_name,
            "energy_groups": ngroups,
            "legendre_order": legendre_order,
            "volume": volume,
            "temperature": temperature,
            "cross_sections": cross_sections,
            "scatter": scatter_payload,
        }


def _scatter_moment_payload(
    mix_group: Any,
    *,
    ngroups: int | None,
    legendre_order: int | None,
    moment: int,
) -> dict[str, Any] | None:
    """Return ``{axes, shape, moment_index, values}`` for one scatter moment.

    Returns ``None`` if the mixture has no scatter dataset at all so the
    endpoint can tell the difference between "no scatter" (None) and
    "moment out of range" (dict with empty ``values``, surfaced as 404).
    """

    if "scatter_matrix" not in mix_group:
        return None
    dataset = mix_group["scatter_matrix"]
    axes_raw = dataset.attrs.get("axes")
    axes = (
        axes_raw.decode("utf-8")
        if isinstance(axes_raw, (bytes, bytearray))
        else axes_raw
        if isinstance(axes_raw, str)
        else None
    )
    arr = np.asarray(dataset[:], dtype=float)
    shape = list(arr.shape)
    if ngroups is None:
        # Best-effort fall back to whichever symmetric dimension matches.
        candidates = [s for s in shape if s > 0]
        ngroups = candidates[0] if candidates else 0
    matrix = scatter_moment_matrix(
        arr,
        axes,
        ngroups,
        legendre_order if legendre_order is not None else max(0, shape[0] - 1),
        moment=moment,
    )
    return {
        "axes": axes,
        "shape": shape,
        "moment_index": moment,
        "values": matrix.tolist() if matrix is not None else [],
    }


def _float_attr(attrs: Any, name: str) -> float | None:
    if name not in attrs:
        return None
    try:
        return float(attrs[name])
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _mock_mixture_rows() -> dict[str, dict[str, Any]]:
    """Cached mixture rows from the bundled handoff fixture, by name."""

    handoff = load_fixture("inspect_handoff.json")
    return {mix["name"]: mix for mix in handoff.get("mixtures", [])}


def _mock_mixture(mixture: str, moment: int, http_exception: Any) -> dict[str, Any]:
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
    if moment >= 2:
        raise http_exception(
            status_code=404,
            detail=f"scatter moment {moment} not available for mixture {mixture}",
        )

    payload = load_fixture("inspect_mixture.json")
    payload = dict(payload)
    payload["mixture"] = mixture
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
