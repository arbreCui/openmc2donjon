"""FastAPI application factory for the openmc2donjon web UI.

Endpoints (M1 scope):

- ``GET /api/health`` - backend liveness + mock flag + package version.
- ``GET /api/inspect?path=...`` - file-level summary of an MGXS HDF5
  handoff, plus standard energy-mesh ID match when present.
- ``GET /api/inspect/mixture?path=...&mixture=...&moment=0`` - per-mixture
  cross sections and one scatter moment.

The ``create_app`` factory keeps the mock flag out of module globals so
the CLI ``serve`` command can pass it in explicitly. Mock mode returns
bundled fixture JSONs from ``src/openmc2donjon/web/fixtures/`` so the
frontend can be exercised without a real HDF5 on disk.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

import numpy as np

from .. import __version__
from .._logging import get_logger
from ..energy_groups import identify_mesh
from ..mgxs_inspect import _report_payload, inspect_file
from ..mgxs_physics_checks import scatter_moment_matrix


logger = get_logger("web.server")

DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

INSPECT_SCHEMA = "openmc2donjon.mgxs-inspect.v1"
MIXTURE_SCHEMA = "openmc2donjon.mgxs-mixture.v1"

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


def create_app(
    *,
    mock_mode: bool = False,
    extra_origins: tuple[str, ...] = (),
) -> Any:
    """Build a configured FastAPI application instance.

    The CORS allow-list always includes ``DEFAULT_CORS_ORIGINS`` (the
    Next.js dev server). Any ``extra_origins`` are appended and the
    resulting list is order-preserving deduplicated, so callers can
    grow the list without losing the defaults.

    Importing FastAPI lazily lets the package work without the ``web``
    extra installed for users who only need the CLI.
    """

    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as exc:  # pragma: no cover - exercised via CLI handler
        raise RuntimeError(
            "openmc2donjon web extras are not installed. "
            'Install with: pip install -e ".[web]"',
        ) from exc

    app = FastAPI(
        title="openmc2donjon",
        description="Web interface for the OpenMC -> DRAGON/DONJON handoff pipeline.",
        version=__version__,
    )

    allow_origins = list(dict.fromkeys((*DEFAULT_CORS_ORIGINS, *extra_origins)))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mock_mode": mock_mode,
            "version": __version__,
        }

    @app.get("/api/inspect")
    def api_inspect(path: str = Query(..., min_length=1)) -> dict[str, Any]:
        if mock_mode:
            return _load_fixture("inspect_handoff.json")
        real_path = _validate_hdf5_path(path, HTTPException)
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
        return payload

    @app.get("/api/inspect/mixture")
    def api_inspect_mixture(
        path: str = Query(..., min_length=1),
        mixture: str = Query(..., min_length=1),
        moment: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        if mock_mode:
            return _mock_mixture(mixture, moment, HTTPException)
        real_path = _validate_hdf5_path(path, HTTPException)
        try:
            return _read_mixture_detail(real_path, mixture, moment, HTTPException)
        except (OSError, ValueError) as exc:
            raise HTTPException(
                status_code=422, detail=f"mixture read failed: {exc}"
            ) from exc

    if mock_mode:
        logger.info("openmc2donjon web server starting in MOCK mode")
    else:
        logger.info("openmc2donjon web server starting in LIVE mode")

    return app


def _validate_hdf5_path(raw: str, http_exception: Any) -> Path:
    """Resolve a user-supplied path and confirm it is a readable HDF5 file."""

    import h5py

    real = Path(raw).expanduser().resolve()
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


def _read_bounds_and_mesh(
    real_path: Path,
) -> tuple[list[float] | None, dict[str, Any] | None]:
    """Read ``/energy_bounds`` once and reuse it for mesh ID detection.

    Returns ``(bounds_list, mesh_dict)``. Either side can be ``None``: no
    ``energy_bounds`` dataset means no bounds and no mesh match; bounds
    present but no catalog hit means bounds list with ``mesh_dict=None``.
    """

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
            mix_group, ngroups=ngroups, legendre_order=legendre_order, moment=moment
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


def _load_fixture(filename: str) -> dict[str, Any]:
    """Read a bundled fixture JSON from ``openmc2donjon.web.fixtures``."""

    text = resources.files("openmc2donjon.web.fixtures").joinpath(filename).read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def _mock_mixture_names() -> set[str]:
    handoff = _load_fixture("inspect_handoff.json")
    return {mix["name"] for mix in handoff.get("mixtures", [])}


def _mock_non_fissionable_mixtures() -> set[str]:
    handoff = _load_fixture("inspect_handoff.json")
    return {
        mix["name"]
        for mix in handoff.get("mixtures", [])
        if mix.get("fissionable") is False
    }


def _mock_mixture(mixture: str, moment: int, http_exception: Any) -> dict[str, Any]:
    """Serve the bundled per-mixture fixture for any mixture in the handoff.

    Mock mode previously ignored ``mixture`` / ``moment``. That made it
    impossible to develop the frontend selectors against the mock, and
    let regressions like "moment slider does nothing" slip through. The
    handoff fixture declares 9 mixtures and P1 scattering, so we accept
    those mixture names and moments 0 and 1, and synthesize a plausible
    P1 by scaling the bundled P0 values by 0.1 - enough non-zero
    structure for the frontend selectors and plot wiring to be exercised
    without us needing to ship a second hand-crafted fixture per moment.
    """

    if mixture not in _mock_mixture_names():
        raise http_exception(
            status_code=404, detail=f"mixture not found: {mixture}"
        )
    if moment >= 2:
        raise http_exception(
            status_code=404,
            detail=f"scatter moment {moment} not available for mixture {mixture}",
        )

    payload = _load_fixture("inspect_mixture.json")
    payload = dict(payload)
    payload["mixture"] = mixture
    if mixture in _mock_non_fissionable_mixtures():
        # Strip the fission family so the frontend exercises the
        # null-series guards in both the spectrum and the (M2-A)
        # heatmap. ``total`` / ``absorption`` / ``scatter`` stay
        # present - moderator / guide-tube mixtures absolutely still
        # have those.
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
