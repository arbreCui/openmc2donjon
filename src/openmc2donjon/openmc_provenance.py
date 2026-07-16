"""Build and verify provenance for an OpenMC fine-model MGXS reference.

The provenance record is intentionally independent of native DRAGON SPH.  A
native SPH calculation consumes an immutable MGXS reference; it must not need
to rerun OpenMC.  This module makes that reference traceable to the OpenMC
recipe, statepoint, model inputs, run settings, and nuclear-data files that
produced it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import struct
from typing import Any
import xml.etree.ElementTree as ET


OPENMC_PROVENANCE_SCHEMA = "openmc2donjon.openmc-provenance.v1"
OPENMC_PROVENANCE_GROUP = "provenance/openmc"
OPENMC_PROVENANCE_DATASET = "record_json"
HANDOFF_PAYLOAD_ALGORITHM = "openmc2donjon-hdf5-payload-sha256-v1"

_PROVENANCE_ROOT_ATTRS = {
    "openmc_provenance_schema",
    "openmc_provenance_status",
    "openmc_provenance_sha256",
    "openmc2donjon_version",
}

_MODEL_FILENAMES = {
    "geometry": "geometry.xml",
    "materials": "materials.xml",
    "settings": "settings.xml",
    "tallies": "tallies.xml",
    "summary": "summary.h5",
}
_SIMULATION_FIELDS = (
    "run_mode",
    "particles",
    "batches",
    "inactive",
    "generations_per_batch",
    "seed",
    "stride",
    "threads",
    "mpi_ranks",
)


def collect_openmc_provenance(
    *,
    recipe_path: str | Path,
    statepoint_path: str | Path | None,
    statepoint_loaded: bool,
    declared_files: Mapping[str, Any] | Sequence[Any] | None = None,
    declared_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a canonical, hash-bound OpenMC source-provenance record.

    ``declared_files`` is the result of an optional recipe
    ``provenance_files()`` hook.  It may map stable roles to paths or be a list
    of paths.  ``declared_metadata`` is the optional result of a recipe
    ``provenance_metadata()`` hook and can fill values that an OpenMC
    statepoint does not store, such as a scheduler-provided thread count.
    Unknown metadata is retained under ``user_metadata`` instead of being
    interpreted as a verified standard field.
    """

    recipe = Path(recipe_path).expanduser().resolve()
    statepoint = (
        None
        if statepoint_path is None
        else Path(statepoint_path).expanduser().resolve()
    )
    metadata = dict(declared_metadata or {})
    input_closure = {
        "attested_complete": metadata.get("input_closure_complete") is True,
        "method": (
            "recipe-provenance-files"
            if metadata.get("input_closure_complete") is True
            else None
        ),
    }

    file_map = _normalize_declared_files(declared_files, recipe.parent)
    search_dirs = _unique_paths(
        [statepoint.parent if statepoint is not None else None, recipe.parent]
    )
    for role, filename in _MODEL_FILENAMES.items():
        if role in file_map:
            continue
        candidate = _first_existing(search_dirs, filename)
        if candidate is not None:
            file_map[role] = candidate

    artifacts = [_artifact("recipe", recipe)]
    if statepoint is not None:
        artifacts.append(_artifact("statepoint", statepoint))
    artifacts.extend(
        _artifact(role, path)
        for role, path in sorted(file_map.items())
        if role not in {"recipe", "statepoint", "cross_sections"}
    )

    statepoint_metadata = _read_statepoint_metadata(statepoint)
    settings_path = file_map.get("settings")
    settings_metadata, temperature = _read_settings_xml(settings_path)
    simulation, simulation_conflicts, simulation_sources = _simulation_metadata(
        statepoint_metadata,
        settings_metadata,
        metadata,
    )

    cross_sections_path, cross_sections_source = _cross_sections_path(
        metadata,
        file_map,
        materials_path=file_map.get("materials"),
        base_dir=recipe.parent,
    )
    used_materials = _materials_names(file_map.get("materials"))
    nuclear_data = _nuclear_data_identity(
        cross_sections_path,
        cross_sections_source=cross_sections_source,
        used_materials=used_materials,
    )

    openmc_version = _first_text(
        statepoint_metadata.get("openmc_version"),
        metadata.get("openmc_version"),
    )
    openmc_git_sha1 = _first_text(
        metadata.get("openmc_git_sha1"),
        statepoint_metadata.get("openmc_git_sha1"),
    )
    openmc_statepoint_version = _first_text(
        statepoint_metadata.get("statepoint_version")
    )
    producer_version = _package_version()
    openmc_version_sources = {
        "statepoint": _jsonable(statepoint_metadata.get("openmc_version")),
        "recipe": _jsonable(metadata.get("openmc_version")),
    }

    missing = _missing_reproducibility_fields(
        artifacts=artifacts,
        statepoint_loaded=statepoint_loaded,
        openmc_version=openmc_version,
        producer_version=producer_version,
        simulation=simulation,
        nuclear_data=nuclear_data,
        input_closure=input_closure,
    )
    version_conflict = _values_conflict(
        statepoint_metadata.get("openmc_version"),
        metadata.get("openmc_version"),
    )
    if version_conflict:
        missing.append("conflict.openmc.version")
    missing.extend(f"conflict.simulation.{field}" for field in simulation_conflicts)
    missing = list(dict.fromkeys(missing))
    issues = [_missing_issue(name) for name in missing]
    if statepoint is not None and not statepoint_metadata.get(
        "is_openmc_statepoint", False
    ):
        issues.append("statepoint is not a verified OpenMC statepoint HDF5 file")
        if "statepoint.openmc_hdf5" not in missing:
            missing.append("statepoint.openmc_hdf5")
    capabilities = _provenance_capabilities(missing)
    fingerprints = _content_fingerprints(
        artifacts=artifacts,
        simulation=simulation,
        nuclear_data=nuclear_data,
    )

    record: dict[str, Any] = {
        "schema": OPENMC_PROVENANCE_SCHEMA,
        "status": "complete" if not missing else "incomplete",
        "issues": issues,
        "missing": missing,
        "capabilities": capabilities,
        "fingerprints": fingerprints,
        "producer": {
            "name": "openmc2donjon",
            "version": producer_version,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "openmc": {
            "version": openmc_version,
            "git_sha1": openmc_git_sha1,
            "statepoint_format_version": openmc_statepoint_version,
        },
        "statepoint": {
            "filetype": statepoint_metadata.get("filetype"),
            "is_openmc_statepoint": bool(
                statepoint_metadata.get("is_openmc_statepoint", False)
            ),
            "date_and_time": statepoint_metadata.get("date_and_time"),
        },
        "source_mode": "recipe-statepoint" if statepoint_loaded else "recipe-only",
        "statepoint_loaded": bool(statepoint_loaded),
        "evidence": {
            "simulation_sources": simulation_sources,
            "openmc_version_sources": openmc_version_sources,
        },
        "input_closure": input_closure,
        "handoff": {
            "algorithm": HANDOFF_PAYLOAD_ALGORITHM,
            "payload_sha256": None,
        },
        "artifacts": artifacts,
        "simulation": simulation,
        "temperature": temperature,
        "nuclear_data": nuclear_data,
        "user_metadata": _user_metadata(metadata),
    }
    record["digest_sha256"] = provenance_digest(record)
    return record


def write_openmc_provenance(
    path: str | Path,
    record: Mapping[str, Any],
) -> dict[str, Any]:
    """Embed and verify one canonical provenance record in an MGXS handoff.

    The embedded record includes a semantic SHA256 over every HDF5 attribute
    and dataset outside its own provenance envelope.  This closes the
    otherwise circular problem of binding a file to a digest stored inside
    that same file.
    """

    import h5py

    with h5py.File(Path(path), "r+") as h5:
        payload = _canonical_record(record)
        payload.pop("integrity", None)
        payload["handoff"] = {
            "algorithm": HANDOFF_PAYLOAD_ALGORITHM,
            "payload_sha256": hdf5_payload_sha256_h5(h5),
        }
        digest = provenance_digest(payload)
        payload["digest_sha256"] = digest
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        provenance = h5.require_group("provenance")
        if "openmc" in provenance:
            del provenance["openmc"]
        group = provenance.create_group("openmc")
        group.attrs["schema"] = OPENMC_PROVENANCE_SCHEMA
        group.attrs["status"] = str(payload.get("status", "incomplete"))
        group.attrs["sha256"] = digest
        string_dtype = h5py.string_dtype(encoding="utf-8")
        group.create_dataset(
            OPENMC_PROVENANCE_DATASET,
            data=encoded,
            dtype=string_dtype,
        )
        h5.attrs["openmc_provenance_schema"] = OPENMC_PROVENANCE_SCHEMA
        h5.attrs["openmc_provenance_status"] = str(
            payload.get("status", "incomplete")
        )
        h5.attrs["openmc_provenance_sha256"] = digest
        h5.attrs["openmc2donjon_version"] = str(
            payload.get("producer", {}).get("version", "unknown")
        )
        verified = read_openmc_provenance_h5(h5)
    if verified is None:  # pragma: no cover - write above guarantees a record
        raise RuntimeError("failed to read back embedded OpenMC provenance")
    if not verified.get("integrity", {}).get("ok", False):
        issues = "; ".join(verified.get("integrity", {}).get("issues", []))
        raise ValueError(f"embedded OpenMC provenance failed read-back: {issues}")
    if isinstance(record, dict):
        record.clear()
        record.update(verified)
    return verified


def read_openmc_provenance(path: str | Path) -> dict[str, Any] | None:
    """Read and integrity-check embedded OpenMC provenance from HDF5."""

    import h5py

    with h5py.File(Path(path), "r") as h5:
        return read_openmc_provenance_h5(h5)


def provenance_before_hdf5_mutation(
    path: str | Path,
) -> dict[str, Any] | None:
    """Capture an intact record before an authorized handoff mutation.

    Legacy or non-OpenMC files have nothing to refresh. A damaged modern
    record is rejected so a postprocessor cannot accidentally bless existing
    tampering by computing a new payload digest over it.
    """

    record = read_openmc_provenance(path)
    if record is None or record.get("status") == "legacy":
        return None
    integrity = record.get("integrity")
    if not isinstance(integrity, Mapping) or integrity.get("ok") is not True:
        issues = integrity.get("issues", []) if isinstance(integrity, Mapping) else []
        detail = "; ".join(str(item) for item in issues)
        raise ValueError(
            "cannot mutate HDF5 with invalid OpenMC provenance"
            + (f": {detail}" if detail else "")
        )
    return record


def refresh_openmc_provenance_after_hdf5_mutation(
    path: str | Path,
    record: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Rebind a previously verified record to an intentionally changed HDF5."""

    if record is None:
        return None
    return write_openmc_provenance(path, record)


def read_openmc_provenance_h5(h5: Any) -> dict[str, Any] | None:
    """Read provenance from an already-open h5py file."""

    if OPENMC_PROVENANCE_GROUP not in h5:
        source = _decode_scalar(h5.attrs.get("source"))
        if source is None or "openmc" not in str(source).lower():
            return None
        return legacy_openmc_provenance(
            "OpenMC source file has no embedded fine-model provenance record"
        )
    group = h5[OPENMC_PROVENANCE_GROUP]
    if OPENMC_PROVENANCE_DATASET not in group:
        return legacy_openmc_provenance(
            "embedded OpenMC provenance group has no record_json dataset"
        )
    raw = _decode_scalar(group[OPENMC_PROVENANCE_DATASET][()])
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return legacy_openmc_provenance(
            "embedded OpenMC provenance record is not valid JSON"
        )
    if not isinstance(payload, dict):
        return legacy_openmc_provenance(
            "embedded OpenMC provenance record must be a JSON object"
        )
    result = _canonical_record(payload)
    verification_issues: list[str] = []
    stored_digest = _text_or_none(result.get("digest_sha256"))
    expected_digest = provenance_digest(result)
    group_digest = _text_or_none(group.attrs.get("sha256"))
    root_digest = _text_or_none(h5.attrs.get("openmc_provenance_sha256"))
    group_schema = _text_or_none(group.attrs.get("schema"))
    root_schema = _text_or_none(h5.attrs.get("openmc_provenance_schema"))
    group_status = _text_or_none(group.attrs.get("status"))
    root_status = _text_or_none(h5.attrs.get("openmc_provenance_status"))
    if stored_digest != expected_digest:
        verification_issues.append(
            "embedded provenance digest does not match record content"
        )
    if group_digest != expected_digest or root_digest != expected_digest:
        verification_issues.append(
            "HDF5 provenance binding digest does not match record content"
        )
    if group_schema != result.get("schema") or root_schema != result.get("schema"):
        verification_issues.append(
            "HDF5 provenance schema mirrors do not match record content"
        )
    if group_status != result.get("status") or root_status != result.get("status"):
        verification_issues.append(
            "HDF5 provenance status mirrors do not match record content"
        )
    if result.get("schema") != OPENMC_PROVENANCE_SCHEMA:
        verification_issues.append(
            f"unsupported provenance schema: {result.get('schema')!r}"
        )
    verification_issues.extend(_record_shape_issues(result))
    verification_issues.extend(_derived_record_issues(result))
    handoff = result.get("handoff")
    recorded_payload_digest = (
        _text_or_none(handoff.get("payload_sha256"))
        if isinstance(handoff, Mapping)
        else None
    )
    actual_payload_digest = hdf5_payload_sha256_h5(h5)
    if recorded_payload_digest != actual_payload_digest:
        verification_issues.append(
            "HDF5 MGXS payload digest does not match the embedded provenance record"
        )
    result["integrity"] = {
        "ok": not verification_issues,
        "issues": list(
            dict.fromkeys(str(item) for item in verification_issues)
        ),
    }
    result["digest_sha256"] = expected_digest
    return result


def legacy_openmc_provenance(issue: str) -> dict[str, Any]:
    """Return the stable UI/API shape for an older unbound OpenMC file."""

    return {
        "schema": None,
        "status": "legacy",
        "issues": [issue],
        "missing": ["embedded_provenance"],
        "capabilities": {
            "reference_bound": False,
            "export_replayable": False,
            "transport_reproducible": False,
        },
        "fingerprints": {
            "model_sha256": None,
            "transport_sha256": None,
        },
        "digest_sha256": None,
        "integrity": {"ok": False, "issues": [issue]},
        "producer": {
            "name": None,
            "version": None,
            "python_version": None,
            "platform": None,
        },
        "openmc": {
            "version": None,
            "git_sha1": None,
            "statepoint_format_version": None,
        },
        "statepoint": {
            "filetype": None,
            "is_openmc_statepoint": False,
            "date_and_time": None,
        },
        "source_mode": "legacy",
        "statepoint_loaded": None,
        "evidence": {
            "simulation_sources": {},
            "openmc_version_sources": {},
        },
        "input_closure": {"attested_complete": False, "method": None},
        "handoff": {
            "algorithm": HANDOFF_PAYLOAD_ALGORITHM,
            "payload_sha256": None,
        },
        "artifacts": [],
        "simulation": {field: None for field in _SIMULATION_FIELDS},
        "temperature": None,
        "nuclear_data": {
            "cross_sections": None,
            "cross_sections_source": None,
            "selection": "unavailable",
            "library_count": 0,
            "total_size_bytes": 0,
            "libraries_manifest_sha256": None,
            "libraries": [],
        },
        "user_metadata": {},
    }


def provenance_digest(record: Mapping[str, Any]) -> str:
    """Return the SHA256 of a canonical record, excluding its own digest."""

    payload = _canonical_record(record)
    payload.pop("digest_sha256", None)
    payload.pop("integrity", None)
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_openmc_provenance_record(record: Mapping[str, Any]) -> list[str]:
    """Validate a standalone record without trusting its self-reported claims."""

    issues: list[str] = []
    stored_digest = _text_or_none(record.get("digest_sha256"))
    if stored_digest != provenance_digest(record):
        issues.append("provenance digest does not match record content")
    issues.extend(_record_shape_issues(record))
    issues.extend(_derived_record_issues(record))
    return list(dict.fromkeys(issues))


def _record_shape_issues(record: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    if record.get("status") not in {"complete", "incomplete"}:
        issues.append("provenance status must be complete or incomplete")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list):
        return issues + ["provenance artifacts must be a list"]
    roles: set[str] = set()
    for index, item in enumerate(artifacts):
        if not isinstance(item, Mapping):
            issues.append(f"provenance artifact {index} must be an object")
            continue
        role = item.get("role")
        if not isinstance(role, str) or not role:
            issues.append(f"provenance artifact {index} has no role")
        elif role in roles:
            issues.append(f"duplicate provenance artifact role: {role}")
        else:
            roles.add(role)
        if not isinstance(item.get("path"), str) or not item.get("path"):
            issues.append(f"provenance artifact {index} has no path")
        if not isinstance(item.get("present"), bool):
            issues.append(f"provenance artifact {index} present must be boolean")
        if not isinstance(item.get("required"), bool):
            issues.append(f"provenance artifact {index} required must be boolean")
        digest = item.get("sha256")
        if digest is not None and not _is_sha256(digest):
            issues.append(f"provenance artifact {index} has invalid SHA256")
        if item.get("present") is True and digest is None:
            issues.append(f"provenance artifact {index} is present without SHA256")
    capabilities = record.get("capabilities")
    expected_capabilities = {
        "reference_bound",
        "export_replayable",
        "transport_reproducible",
    }
    if not isinstance(capabilities, Mapping):
        issues.append("provenance capabilities must be an object")
    else:
        for name in expected_capabilities:
            if not isinstance(capabilities.get(name), bool):
                issues.append(f"provenance capability {name} must be boolean")
        if record.get("status") == "complete" and not capabilities.get(
            "transport_reproducible"
        ):
            issues.append(
                "complete provenance must declare transport_reproducible=true"
            )
    missing = record.get("missing")
    if not isinstance(missing, list) or not all(
        isinstance(item, str) for item in missing
    ):
        issues.append("provenance missing must be a list of strings")
    elif record.get("status") == "complete" and missing:
        issues.append("complete provenance must not list missing fields")
    handoff = record.get("handoff")
    if not isinstance(handoff, Mapping):
        issues.append("provenance handoff binding must be an object")
    else:
        if handoff.get("algorithm") != HANDOFF_PAYLOAD_ALGORITHM:
            issues.append("unsupported HDF5 handoff payload digest algorithm")
        if not _is_sha256(handoff.get("payload_sha256")):
            issues.append("HDF5 handoff payload digest must be a SHA256")
    input_closure = record.get("input_closure")
    if not isinstance(input_closure, Mapping) or not isinstance(
        input_closure.get("attested_complete"), bool
    ):
        issues.append("input closure attestation must be boolean")
    if not isinstance(record.get("evidence"), Mapping):
        issues.append("provenance source evidence must be an object")
    return issues


def _derived_record_issues(record: Mapping[str, Any]) -> list[str]:
    """Recompute every claimed completeness field from bound record content."""

    artifacts_value = record.get("artifacts")
    artifacts = (
        [item for item in artifacts_value if isinstance(item, Mapping)]
        if isinstance(artifacts_value, list)
        else []
    )
    openmc = record.get("openmc")
    simulation = record.get("simulation")
    nuclear_data = record.get("nuclear_data")
    statepoint = record.get("statepoint")
    input_closure = record.get("input_closure")
    evidence = record.get("evidence")
    producer = record.get("producer")
    if not isinstance(openmc, Mapping):
        openmc = {}
    if not isinstance(simulation, Mapping):
        simulation = {}
    if not isinstance(nuclear_data, Mapping):
        nuclear_data = {}
    if not isinstance(statepoint, Mapping):
        statepoint = {}
    if not isinstance(input_closure, Mapping):
        input_closure = {}
    if not isinstance(evidence, Mapping):
        evidence = {}
    if not isinstance(producer, Mapping):
        producer = {}

    derived_missing = _missing_reproducibility_fields(
        artifacts=artifacts,
        statepoint_loaded=record.get("statepoint_loaded") is True,
        openmc_version=_text_or_none(openmc.get("version")),
        producer_version=_text_or_none(producer.get("version")),
        simulation=simulation,
        nuclear_data=nuclear_data,
        input_closure=input_closure,
    )
    simulation_sources = evidence.get("simulation_sources")
    if isinstance(simulation_sources, Mapping):
        for field, sources in simulation_sources.items():
            if isinstance(sources, Mapping) and _mapping_values_conflict(sources):
                derived_missing.append(f"conflict.simulation.{field}")
    version_sources = evidence.get("openmc_version_sources")
    if isinstance(version_sources, Mapping) and _mapping_values_conflict(
        version_sources
    ):
        derived_missing.append("conflict.openmc.version")
    if not statepoint.get("is_openmc_statepoint", False):
        derived_missing.append("statepoint.openmc_hdf5")
    derived_missing = list(dict.fromkeys(derived_missing))
    issues: list[str] = []
    recorded_missing = record.get("missing")
    if not isinstance(recorded_missing, list) or set(recorded_missing) != set(
        derived_missing
    ):
        issues.append("recorded missing fields do not match provenance content")
    derived_capabilities = _provenance_capabilities(derived_missing)
    if record.get("capabilities") != derived_capabilities:
        issues.append("recorded capabilities do not match provenance content")
    derived_status = "complete" if not derived_missing else "incomplete"
    if record.get("status") != derived_status:
        issues.append("recorded status does not match provenance content")
    derived_fingerprints = _content_fingerprints(
        artifacts=artifacts,
        simulation=simulation,
        nuclear_data=nuclear_data,
    )
    if record.get("fingerprints") != derived_fingerprints:
        issues.append("recorded content fingerprints do not match provenance content")
    return issues


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hdf5_payload_sha256(path: str | Path) -> str:
    """Hash the scientific HDF5 payload, excluding this provenance envelope."""

    import h5py

    with h5py.File(Path(path), "r") as h5:
        return hdf5_payload_sha256_h5(h5)


def hdf5_payload_sha256_h5(h5: Any) -> str:
    """Return a layout-independent digest of HDF5 paths, attrs, and values.

    Dataset chunking/compression and absolute filesystem location are excluded;
    scientific paths, dtypes, shapes, attributes, links, and values are bound.
    ``/provenance/openmc`` plus its root mirrors are excluded to avoid a
    self-referential digest.
    """

    import h5py

    digest = hashlib.sha256()
    _hash_token(digest, b"algorithm", HANDOFF_PAYLOAD_ALGORITHM.encode("ascii"))
    _hash_h5_attrs(
        digest,
        h5.attrs,
        excluded=_PROVENANCE_ROOT_ATTRS,
    )
    visited_groups = {_h5_object_address(h5): "/"}

    def walk(group: Any, parent_path: str) -> None:
        for name in sorted(group.keys()):
            path = f"{parent_path}/{name}" if parent_path else f"/{name}"
            if path == "/provenance/openmc" or path.startswith(
                "/provenance/openmc/"
            ):
                continue
            link = group.get(name, getlink=True)
            if isinstance(link, h5py.SoftLink):
                _hash_token(digest, b"soft-link-path", path.encode("utf-8"))
                _hash_token(digest, b"soft-link-target", link.path.encode("utf-8"))
                continue
            if isinstance(link, h5py.ExternalLink):
                _hash_token(digest, b"external-link-path", path.encode("utf-8"))
                _hash_token(
                    digest,
                    b"external-link-target",
                    f"{link.filename}\0{link.path}".encode("utf-8"),
                )
                continue
            item = group[name]
            if isinstance(item, h5py.Group):
                # The parent group may have been created solely to contain the
                # excluded OpenMC record. Other children remain independently
                # traversed and therefore bound.
                if path != "/provenance":
                    _hash_token(digest, b"group", path.encode("utf-8"))
                    _hash_h5_attrs(digest, item.attrs)
                address = _h5_object_address(item)
                first_path = visited_groups.get(address)
                if first_path is not None:
                    _hash_token(
                        digest,
                        b"hard-link-target",
                        first_path.encode("utf-8"),
                    )
                    continue
                visited_groups[address] = path
                walk(item, path)
                continue
            if isinstance(item, h5py.Dataset):
                _hash_token(digest, b"dataset", path.encode("utf-8"))
                _hash_token(
                    digest,
                    b"dtype",
                    _h5_dtype_identity(item.dtype).encode("utf-8"),
                )
                _hash_token(
                    digest,
                    b"shape",
                    json.dumps(list(item.shape), separators=(",", ":")).encode(
                        "ascii"
                    ),
                )
                _hash_h5_attrs(digest, item.attrs)
                _hash_h5_dataset_values(digest, item)

    walk(h5, "")
    return digest.hexdigest()


def _hash_token(digest: Any, label: bytes, value: bytes) -> None:
    digest.update(struct.pack(">Q", len(label)))
    digest.update(label)
    digest.update(struct.pack(">Q", len(value)))
    digest.update(value)


def _hash_h5_attrs(
    digest: Any,
    attrs: Any,
    *,
    excluded: set[str] | None = None,
) -> None:
    excluded_names = excluded or set()
    for name in sorted(str(item) for item in attrs.keys()):
        if name in excluded_names:
            continue
        _hash_token(digest, b"attr-name", name.encode("utf-8"))
        _hash_h5_value(digest, attrs[name])


def _hash_h5_dataset_values(digest: Any, dataset: Any) -> None:
    import numpy as np

    if dataset.shape == ():
        _hash_h5_value(digest, dataset[()])
        return
    if dataset.size == 0:
        _hash_token(digest, b"data", b"")
        return
    trailing_values = int(np.prod(dataset.shape[1:], dtype=np.int64)) or 1
    bytes_per_row = max(1, trailing_values * max(1, int(dataset.dtype.itemsize)))
    rows_per_block = max(1, (4 * 1024 * 1024) // bytes_per_row)
    digest.update(b"data-stream\0")
    for start in range(0, dataset.shape[0], rows_per_block):
        stop = min(dataset.shape[0], start + rows_per_block)
        block = np.asarray(dataset[start:stop])
        if block.dtype.hasobject:
            for value in block.reshape(-1, order="C"):
                _hash_h5_value(digest, value)
        else:
            digest.update(np.ascontiguousarray(block).tobytes(order="C"))


def _hash_h5_value(digest: Any, value: Any) -> None:
    import numpy as np

    if isinstance(value, np.ndarray):
        _hash_token(digest, b"value-dtype", _h5_dtype_identity(value.dtype).encode())
        _hash_token(
            digest,
            b"value-shape",
            json.dumps(list(value.shape), separators=(",", ":")).encode("ascii"),
        )
        if value.dtype.hasobject:
            for item in value.reshape(-1, order="C"):
                _hash_h5_value(digest, item)
        else:
            _hash_token(
                digest,
                b"value-bytes",
                np.ascontiguousarray(value).tobytes(order="C"),
            )
        return
    if isinstance(value, np.generic):
        array = np.asarray(value)
        _hash_token(digest, b"scalar-dtype", _h5_dtype_identity(array.dtype).encode())
        if array.dtype.hasobject:
            _hash_h5_value(digest, value.item())
        else:
            _hash_token(digest, b"scalar-bytes", array.tobytes())
        return
    if isinstance(value, bytes):
        _hash_token(digest, b"bytes", value)
        return
    if isinstance(value, str):
        _hash_token(digest, b"text", value.encode("utf-8"))
        return
    _hash_token(
        digest,
        b"json",
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8"),
    )


def _h5_dtype_identity(dtype: Any) -> str:
    descriptor = dtype.descr if getattr(dtype, "fields", None) else dtype.str
    return json.dumps(_jsonable(descriptor), separators=(",", ":"), ensure_ascii=False)


def _h5_object_address(item: Any) -> int:
    import h5py

    return int(h5py.h5o.get_info(item.id).addr)


def _artifact(
    role: str,
    path: str | Path,
    *,
    required: bool | None = None,
    hash_cache: dict[Path, tuple[int, str]] | None = None,
) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    present = resolved.is_file()
    size_bytes = None
    digest = None
    if present:
        cached = hash_cache.get(resolved) if hash_cache is not None else None
        if cached is None:
            cached = (resolved.stat().st_size, file_sha256(resolved))
            if hash_cache is not None:
                hash_cache[resolved] = cached
        size_bytes, digest = cached
    return {
        "role": str(role),
        "required": (
            role in {"recipe", "statepoint", "settings", "cross_sections"}
            or role.startswith("library_")
            if required is None
            else bool(required)
        ),
        "path": str(resolved),
        "present": present,
        "size_bytes": size_bytes,
        "sha256": digest,
    }


def _normalize_declared_files(
    value: Mapping[str, Any] | Sequence[Any] | None,
    base_dir: Path,
) -> dict[str, Path]:
    if value is None:
        return {}
    result: dict[str, Path] = {}
    if isinstance(value, Mapping):
        items = value.items()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = ((_role_from_path(item), item) for item in value)
    else:
        raise TypeError("recipe provenance_files() must return a mapping or list")
    for raw_role, raw_path in items:
        if raw_path is None:
            continue
        role = str(raw_role).strip().lower().replace(" ", "_")
        if not role:
            raise ValueError("recipe provenance file role must not be empty")
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        candidate = path.resolve()
        if role in result and result[role] != candidate:
            raise ValueError(f"duplicate provenance file role: {role}")
        result[role] = candidate
    return result


def _role_from_path(value: Any) -> str:
    name = Path(value).name.lower()
    for role, filename in _MODEL_FILENAMES.items():
        if name == filename:
            return role
    return Path(value).stem.lower().replace("-", "_") or "model_input"


def _read_statepoint_metadata(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"is_hdf5": False, "is_openmc_statepoint": False}
    try:
        import h5py

        if not h5py.is_hdf5(path):
            return {"is_hdf5": False, "is_openmc_statepoint": False}
        with h5py.File(path, "r") as h5:
            filetype = _h5_value(h5, "filetype", attrs=("filetype",))
            normalized_filetype = str(filetype or "").strip().lower()
            return {
                "is_hdf5": True,
                "is_openmc_statepoint": normalized_filetype == "statepoint",
                "filetype": filetype,
                "date_and_time": _h5_value(
                    h5, "date_and_time", attrs=("date_and_time",)
                ),
                "openmc_version": _render_version(
                    _h5_value(h5, "openmc_version", attrs=("openmc_version",))
                ),
                "openmc_git_sha1": _h5_value(
                    h5, "git_sha1", attrs=("git_sha1", "openmc_git_sha1")
                ),
                "statepoint_version": _render_version(
                    _h5_value(h5, "version", attrs=("version",))
                ),
                "run_mode": _h5_value(h5, "run_mode"),
                "particles": _h5_value(h5, "n_particles", "particles"),
                "batches": _h5_value(h5, "n_batches", "batches"),
                "inactive": _h5_value(h5, "n_inactive", "inactive"),
                "generations_per_batch": _h5_value(
                    h5, "generations_per_batch", "gen_per_batch"
                ),
                "seed": _h5_value(h5, "seed"),
                "stride": _h5_value(h5, "stride"),
            }
    except (OSError, ValueError, TypeError):
        return {"is_hdf5": False, "is_openmc_statepoint": False}


def _h5_value(h5: Any, *datasets: str, attrs: Sequence[str] = ()) -> Any:
    for name in attrs:
        if name in h5.attrs:
            return _json_scalar(h5.attrs[name])
    for name in datasets:
        if name not in h5:
            continue
        try:
            value = h5[name][()]
        except (OSError, TypeError, ValueError):
            continue
        return _json_scalar(value)
    return None


def _read_settings_xml(path: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if path is None or not path.is_file():
        return {}, None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}, None
    settings: dict[str, Any] = {}
    for field in (
        "run_mode",
        "particles",
        "batches",
        "inactive",
        "generations_per_batch",
        "seed",
    ):
        text = root.findtext(field)
        if text is not None and text.strip():
            settings[field] = _number_or_text(text)
    temperature_node = root.find("temperature")
    temperature = None
    if temperature_node is not None:
        temperature = {
            child.tag: _number_or_text(child.text or "")
            for child in temperature_node
            if (child.text or "").strip()
        }
        if temperature_node.attrib:
            temperature["attributes"] = dict(sorted(temperature_node.attrib.items()))
    return settings, temperature


def _simulation_metadata(
    statepoint: Mapping[str, Any],
    settings: Mapping[str, Any],
    declared: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str], dict[str, dict[str, Any]]]:
    aliases = {
        "particles": ("particles", "n_particles"),
        "batches": ("batches", "n_batches"),
        "inactive": ("inactive", "n_inactive"),
        "generations_per_batch": ("generations_per_batch", "gen_per_batch"),
        "run_mode": ("run_mode",),
        "seed": ("seed",),
        "stride": ("stride",),
        "threads": ("threads", "omp_num_threads"),
        "mpi_ranks": ("mpi_ranks", "ranks"),
    }
    result: dict[str, Any] = {}
    conflicts: list[str] = []
    evidence: dict[str, dict[str, Any]] = {}
    for field, names in aliases.items():
        value = None
        field_evidence: dict[str, Any] = {}
        for source_name, source in (
            ("statepoint", statepoint),
            ("settings", settings),
            ("recipe", declared),
        ):
            for name in names:
                if source.get(name) is not None:
                    source_value = _json_scalar(source[name])
                    field_evidence[source_name] = source_value
                    if value is None:
                        value = source_value
                    break
        result[field] = value
        evidence[field] = field_evidence
        if _mapping_values_conflict(field_evidence):
            conflicts.append(field)
    return result, conflicts, evidence


def _cross_sections_path(
    metadata: Mapping[str, Any],
    file_map: Mapping[str, Path],
    *,
    materials_path: Path | None,
    base_dir: Path,
) -> tuple[Path | None, str | None]:
    explicit = (
        metadata.get("cross_sections")
        or metadata.get("cross_sections_path")
        or file_map.get("cross_sections")
    )
    if explicit is not None:
        path = Path(explicit).expanduser()
        if not path.is_absolute():
            path = base_dir / path
        return path.resolve(), "recipe-declared"
    materials_value = _materials_cross_sections(materials_path)
    if materials_value is not None:
        return materials_value, "materials.xml"
    # The current process environment is not historical evidence of what a
    # saved statepoint used. Recipes must declare the path or materials.xml
    # must record it; otherwise provenance remains explicitly incomplete.
    return None, None


def _materials_cross_sections(path: Path | None) -> Path | None:
    if path is None or not path.is_file():
        return None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    value = root.findtext("cross_sections")
    if not value or not value.strip():
        return None
    candidate = Path(value.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = path.parent / candidate
    return candidate.resolve()


def _materials_names(path: Path | None) -> set[str]:
    if path is None or not path.is_file():
        return set()
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return set()
    names: set[str] = set()
    for tag in ("nuclide", "sab", "macroscopic"):
        for node in root.iter(tag):
            name = node.attrib.get("name")
            if name:
                names.add(name)
    return names


def _nuclear_data_identity(
    cross_sections_path: Path | None,
    *,
    cross_sections_source: str | None,
    used_materials: set[str],
) -> dict[str, Any]:
    hash_cache: dict[Path, tuple[int, str]] = {}
    cross_sections = (
        None
        if cross_sections_path is None
        else _artifact(
            "cross_sections",
            cross_sections_path,
            hash_cache=hash_cache,
        )
    )
    libraries: list[dict[str, Any]] = []
    selection = "unavailable"
    if cross_sections_path is not None and cross_sections_path.is_file():
        if cross_sections_path.suffix.lower() in {".h5", ".hdf5"}:
            libraries = [
                _artifact(
                    "library_1",
                    cross_sections_path,
                    hash_cache=hash_cache,
                )
            ]
            libraries[0]["materials"] = sorted(used_materials)
            libraries[0]["type"] = "mgxs"
            selection = "single-mg-library"
        elif used_materials:
            try:
                root = ET.parse(cross_sections_path).getroot()
            except (OSError, ET.ParseError):
                root = None
            selection = "used-materials" if root is not None else "invalid-cross-sections-xml"
        else:
            # Hashing every entry in a large evaluated-data catalog can read
            # hundreds of gigabytes and still would not prove which nuclides
            # the model used. Stay incomplete until materials are known.
            root = None
            selection = "unknown-used-materials"
        if root is not None:
            candidates = []
            for index, node in enumerate(root.findall(".//library"), start=1):
                raw_path = node.attrib.get("path")
                if not raw_path:
                    continue
                materials = set(node.attrib.get("materials", "").split())
                if used_materials and materials and used_materials.isdisjoint(materials):
                    continue
                path = Path(raw_path).expanduser()
                if not path.is_absolute():
                    path = cross_sections_path.parent / path
                artifact = _artifact(
                    f"library_{index}", path, hash_cache=hash_cache
                )
                artifact["materials"] = sorted(materials)
                artifact["type"] = node.attrib.get("type")
                candidates.append(artifact)
            libraries = candidates
    hashed_libraries = [item for item in libraries if item.get("sha256")]
    manifest_digest = None
    if libraries and len(hashed_libraries) == len(libraries):
        identity = [
            {
                "materials": item.get("materials") or [],
                "type": item.get("type"),
                "size_bytes": item.get("size_bytes"),
                "sha256": item.get("sha256"),
            }
            for item in libraries
        ]
        manifest_digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    return {
        "cross_sections": cross_sections,
        "cross_sections_source": cross_sections_source,
        "selection": selection,
        "library_count": len(libraries),
        "total_size_bytes": sum(int(item.get("size_bytes") or 0) for item in libraries),
        "libraries_manifest_sha256": manifest_digest,
        "libraries": libraries,
    }


def _missing_reproducibility_fields(
    *,
    artifacts: Sequence[Mapping[str, Any]],
    statepoint_loaded: bool,
    openmc_version: str | None,
    producer_version: str | None,
    simulation: Mapping[str, Any],
    nuclear_data: Mapping[str, Any],
    input_closure: Mapping[str, Any],
) -> list[str]:
    by_role = {str(item.get("role")): item for item in artifacts}
    missing: list[str] = []
    for role in ("recipe", "statepoint"):
        if role == "statepoint" and not statepoint_loaded:
            missing.append("statepoint.loaded")
            continue
        artifact = by_role.get(role)
        if not artifact or not artifact.get("sha256"):
            missing.append(f"artifact.{role}.sha256")
    if not openmc_version:
        missing.append("openmc.version")
    if not producer_version or producer_version == "unknown":
        missing.append("openmc2donjon.version")
    has_summary = bool(by_role.get("summary", {}).get("sha256"))
    has_xml_model = all(
        bool(by_role.get(role, {}).get("sha256"))
        for role in ("geometry", "materials")
    )
    if not (has_summary or has_xml_model):
        missing.append("model.geometry_materials_or_summary")
    if not by_role.get("settings", {}).get("sha256"):
        missing.append("artifact.settings.sha256")
    if input_closure.get("attested_complete") is not True:
        missing.append("model.input_closure_attested")
    required_simulation = ["run_mode", "particles", "batches", "seed", "stride"]
    run_mode = str(simulation.get("run_mode") or "").lower()
    if "eigenvalue" in run_mode:
        required_simulation.extend(("inactive", "generations_per_batch"))
    for field in required_simulation:
        if simulation.get(field) is None:
            missing.append(f"simulation.{field}")
    cross_sections = nuclear_data.get("cross_sections")
    if not isinstance(cross_sections, Mapping) or not cross_sections.get("sha256"):
        missing.append("nuclear_data.cross_sections.sha256")
    if not nuclear_data.get("libraries_manifest_sha256"):
        missing.append("nuclear_data.libraries_manifest_sha256")
    return missing


def _missing_issue(name: str) -> str:
    labels = {
        "statepoint.loaded": "OpenMC statepoint was not loaded",
        "openmc.version": "OpenMC version is not recorded",
        "openmc2donjon.version": "openmc2donjon version is not recorded",
        "model.geometry_materials_or_summary": (
            "model identity needs geometry.xml + materials.xml or summary.h5"
        ),
        "model.input_closure_attested": (
            "recipe has not attested that provenance_files() lists every model input"
        ),
        "artifact.settings.sha256": "settings.xml is missing or unreadable",
        "nuclear_data.cross_sections.sha256": (
            "cross_sections.xml is missing or unreadable"
        ),
        "nuclear_data.libraries_manifest_sha256": (
            "nuclear-data library content hashes are incomplete"
        ),
    }
    if name in labels:
        return labels[name]
    if name.startswith("simulation."):
        return f"OpenMC run setting is not recorded: {name.split('.', 1)[1]}"
    if name.startswith("conflict."):
        return f"provenance sources disagree: {name.split('.', 1)[1]}"
    if name.startswith("artifact."):
        return f"source artifact is missing or unreadable: {name.split('.')[1]}"
    return f"missing provenance field: {name}"


def _provenance_capabilities(missing: Sequence[str]) -> dict[str, bool]:
    missing_set = set(missing)
    reference_requirements = {
        "statepoint.loaded",
        "statepoint.openmc_hdf5",
        "artifact.recipe.sha256",
        "artifact.statepoint.sha256",
    }
    export_requirements = reference_requirements | {
        "openmc.version",
        "openmc2donjon.version",
        "model.geometry_materials_or_summary",
        "model.input_closure_attested",
        "artifact.settings.sha256",
    }
    conflicts = any(str(item).startswith("conflict.") for item in missing_set)
    return {
        "reference_bound": missing_set.isdisjoint(reference_requirements),
        "export_replayable": (
            missing_set.isdisjoint(export_requirements) and not conflicts
        ),
        "transport_reproducible": not missing_set,
    }


def _content_fingerprints(
    *,
    artifacts: Sequence[Mapping[str, Any]],
    simulation: Mapping[str, Any],
    nuclear_data: Mapping[str, Any],
) -> dict[str, str | None]:
    """Return relocation-stable fingerprints that exclude absolute paths."""

    model_items = sorted(
        (
            str(item.get("role")),
            str(item.get("sha256")),
            int(item.get("size_bytes") or 0),
        )
        for item in artifacts
        if item.get("role") != "statepoint" and item.get("sha256")
    )
    model_sha256 = _canonical_sha256(model_items) if model_items else None
    statepoint = next(
        (item for item in artifacts if item.get("role") == "statepoint"),
        None,
    )
    transport_identity = {
        "model_sha256": model_sha256,
        "statepoint_sha256": (
            statepoint.get("sha256") if isinstance(statepoint, Mapping) else None
        ),
        "simulation": _jsonable(dict(simulation)),
        "nuclear_data_libraries_manifest_sha256": nuclear_data.get(
            "libraries_manifest_sha256"
        ),
    }
    transport_sha256 = (
        _canonical_sha256(transport_identity)
        if model_sha256 and transport_identity["statepoint_sha256"]
        else None
    )
    return {
        "model_sha256": model_sha256,
        "transport_sha256": transport_sha256,
    }


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _jsonable(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def _user_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    interpreted = {
        "input_closure_complete",
        "openmc_version",
        "openmc_git_sha1",
        "cross_sections",
        "cross_sections_path",
        "run_mode",
        "particles",
        "n_particles",
        "batches",
        "n_batches",
        "inactive",
        "n_inactive",
        "generations_per_batch",
        "gen_per_batch",
        "seed",
        "stride",
        "threads",
        "omp_num_threads",
        "mpi_ranks",
        "ranks",
    }
    return {
        str(key): _jsonable(value)
        for key, value in metadata.items()
        if key not in interpreted
    }


def _package_version() -> str:
    try:
        return importlib.metadata.version("openmc2donjon")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _canonical_record(value: Mapping[str, Any]) -> dict[str, Any]:
    converted = _jsonable(dict(value))
    if not isinstance(converted, dict):
        raise TypeError("OpenMC provenance record must be a JSON object")
    return converted


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if hasattr(value, "tolist"):
        try:
            return _jsonable(value.tolist())
        except (TypeError, ValueError):
            pass
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except (TypeError, ValueError):
            pass
    return str(value)


def _json_scalar(value: Any) -> Any:
    converted = _jsonable(value)
    if isinstance(converted, list) and len(converted) == 1:
        return converted[0]
    return converted


def _decode_scalar(value: Any) -> Any:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        try:
            return _decode_scalar(value.item())
        except (TypeError, ValueError):
            return value
    return value


def _render_version(value: Any) -> str | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return ".".join(str(item) for item in value)
    return _text_or_none(value)


def _values_conflict(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return False
    return _normalized_evidence_value(left) != _normalized_evidence_value(right)


def _mapping_values_conflict(values: Mapping[str, Any]) -> bool:
    normalized = {
        _normalized_evidence_value(value)
        for value in values.values()
        if value is not None
    }
    return len(normalized) > 1


def _normalized_evidence_value(value: Any) -> str:
    rendered = _jsonable(value)
    return json.dumps(
        rendered,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).strip().lower()


def _text_or_none(value: Any) -> str | None:
    value = _decode_scalar(value)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _text_or_none(value)
        if text:
            return text
    return None


def _number_or_text(value: str) -> int | float | str | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _unique_paths(values: Sequence[Path | None]) -> list[Path]:
    result: list[Path] = []
    for value in values:
        if value is not None and value not in result:
            result.append(value)
    return result


def _first_existing(directories: Sequence[Path], filename: str) -> Path | None:
    for directory in directories:
        candidate = directory / filename
        if candidate.is_file():
            return candidate.resolve()
    return None
