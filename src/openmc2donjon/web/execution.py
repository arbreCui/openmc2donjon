"""Constrained execution routes for the localhost workflow UI.

These routes call named openmc2donjon library operations directly.  The only
subprocess is DONJON's fixed ``rdonjon`` launcher; arbitrary commands and
arbitrary environment injection are intentionally not exposed.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from threading import BoundedSemaphore, Event, Lock, Thread, current_thread
import time
from typing import Any
from uuid import uuid4

try:  # POSIX ownership locks are required by the native DONJON runner.
    import fcntl
except ImportError:  # pragma: no cover - native DONJON web execution is POSIX-only
    fcntl = None  # type: ignore[assignment]

from ..openmc_sph_sidecar import create_openmc_sph_sidecar
from ..openmc_statepoint import export_openmc_statepoint_recipe
from ..openmc_provenance import legacy_openmc_provenance
from ..sph_apply import (
    apply_sph_to_hdf5,
    apply_sph_to_openmc_mgxs_hdf5,
    write_summary as write_sph_apply_summary,
)
from .filesystem import FilesystemScope


OPENMC_EXPORT_EXECUTION_SCHEMA = "openmc2donjon.web-openmc-export.v3"
SPH_EXECUTION_SCHEMA = "openmc2donjon.web-sph-execution.v1"
DONJON_JOB_SCHEMA = "openmc2donjon.web-donjon-job.v1"
DONJON_JOB_LIST_SCHEMA = "openmc2donjon.web-donjon-job-list.v1"
DONJON_REQUEST_SCHEMA = "openmc2donjon.web-donjon-request.v1"
DONJON_STAGING_SCHEMA = "openmc2donjon.web-donjon-staging.v1"
DONJON_RUNTIME_OUTPUT_SCHEMA = "openmc2donjon.web-donjon-runtime-output.v1"
DONJON_ARTIFACT_MANIFEST_SCHEMA = "openmc2donjon.web-donjon-artifacts.v1"
DONJON_COMPLETION_SCHEMA = "openmc2donjon.web-donjon-completion.v1"
DONJON_OWNER_SCHEMA = "openmc2donjon.web-donjon-owner.v1"
SPH_MAX_UPDATE_RESIDUAL = 0.02
DONJON_MAX_TIMEOUT_SECONDS = 86_400
DONJON_MAX_STAGED_ENTRIES = 20_000
DONJON_MAX_STAGED_BYTES = 4 * 1024**3
DONJON_MAX_STAGED_DEPTH = 64
DONJON_MAX_STAGED_RELATIVE_PATH_BYTES = 1024
DONJON_MAX_DECLARED_INPUT_FILES = 64
DONJON_MAX_STAGING_MANIFEST_BYTES = 64 * 1024**2
DONJON_MAX_RUNTIME_OUTPUT_FILES = 20_000
DONJON_MAX_RUNTIME_OUTPUT_ENTRIES = 20_000
DONJON_MAX_RUNTIME_OUTPUT_BYTES = 4 * 1024**3
DONJON_MAX_RESULT_BYTES = 1024**3


def _mock_openmc_provenance() -> dict[str, Any]:
    record = legacy_openmc_provenance(
        "Simulation mode does not execute OpenMC or produce a scientific artifact"
    )
    record["source_mode"] = "mock"
    record["producer"]["name"] = "openmc2donjon-web"
    record["producer"]["version"] = "mock"
    record["producer"]["python_version"] = platform.python_version()
    record["producer"]["platform"] = "mock"
    return record
DONJON_MAX_SINGLE_RUNTIME_FILE_BYTES = 4 * 1024**3
DONJON_RUNTIME_RESERVE_BYTES = 64 * 1024**2
DONJON_MAX_STDIO_STREAM_BYTES = 8 * 1024**2
DONJON_STDIO_TAIL_BYTES = 1024**2
DONJON_TERMINATION_GRACE_SECONDS = 5.0
DONJON_MAX_CONCURRENT_JOBS = 4
DONJON_MAX_LAUNCHER_BYTES = 4 * 1024**2
DONJON_MAX_SOLVER_BYTES = 256 * 1024**2
DONJON_MAX_LISTED_JOBS = 1_000
DONJON_MAX_CACHED_TERMINAL_JOBS = 256

_DECK_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.x2m$")
_JOB_ID = re.compile(r"^[a-f0-9]{16}$")
_COMPONENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_OWNER_TOKEN = re.compile(r"^[a-f0-9]{32}$")
_FILE_TOKEN = re.compile(r"\bFILE\b", re.IGNORECASE)
_KEFF = re.compile(
    r"(?:OPENMC2DONJON[^\r\n]*K-EFFECTIVE\s+|"
    r"(?:k-effective|k[- ]?eff(?:ective)?)\s*(?:=|:)\s*)"
    r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)",
    re.IGNORECASE,
)

# The stock rdonjon launcher allocates /tmp/rundirN with a non-atomic
# exists-then-mkdir loop.  Serializing launcher ownership prevents two web
# jobs from selecting the same runtime directory and corrupting one another.
_RDONJON_PROCESS_LOCK = Lock()
_ACTIVE_RDONJON_LOCK = Lock()
_ACTIVE_RDONJON_PROCESSES: dict[
    int, tuple[subprocess.Popen[bytes], Event | None]
] = {}
_RDONJON_SHUTDOWN = Event()


def _raise_if_execution_stopped(
    shutdown_event: Event | None, stage: str
) -> None:
    if shutdown_event is None:
        stopped = _RDONJON_SHUTDOWN.is_set()
    else:
        stopped = shutdown_event.is_set()
    if stopped:
        raise RuntimeError(f"the web service is shutting down {stage}")


def _create_job_owner_lock(
    path: Path,
    *,
    job_id: str,
    owner_token: str,
    owner_pid: int,
) -> int:
    """Create and retain the cross-process ownership lock for one job."""

    if fcntl is None:
        raise RuntimeError("native DONJON job ownership requires POSIX file locks")
    descriptor = os.open(
        path,
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0),
        0o600,
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        payload = (
            json.dumps(
                {
                    "schema": DONJON_OWNER_SCHEMA,
                    "job_id": job_id,
                    "owner_token": owner_token,
                    "owner_pid": owner_pid,
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _try_claim_job_owner_lock(job: dict[str, Any]) -> int | None:
    """Claim an orphaned job, or return ``None`` while another backend owns it."""

    if fcntl is None:
        raise RuntimeError("native DONJON job recovery requires POSIX file locks")
    raw_path = job.get("owner_path")
    if not isinstance(raw_path, str):
        raise RuntimeError("persisted DONJON job has no owner lock path")
    descriptor = os.open(
        raw_path,
        os.O_RDWR
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError("persisted DONJON owner lock is not a regular file")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = bytearray()
        while True:
            block = os.read(descriptor, 4096)
            if not block:
                break
            raw.extend(block)
            if len(raw) > 64 * 1024:
                raise RuntimeError("persisted DONJON owner receipt is oversized")
        receipt = json.loads(bytes(raw).decode("utf-8", errors="strict"))
        if (
            not isinstance(receipt, dict)
            or receipt.get("schema") != DONJON_OWNER_SCHEMA
            or receipt.get("job_id") != job.get("job_id")
            or receipt.get("owner_token") != job.get("owner_token")
            or receipt.get("owner_pid") != job.get("owner_pid")
        ):
            raise RuntimeError("persisted DONJON owner receipt does not match its job")
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _recent_job_directories(archive_root: Path) -> list[Path]:
    """Return only the newest bounded set without materialising all history."""

    if DONJON_MAX_LISTED_JOBS <= 0:
        return []
    recent: list[tuple[int, str, Path]] = []
    try:
        children = archive_root.iterdir()
    except OSError:
        return []
    for child in children:
        if not _JOB_ID.fullmatch(child.name):
            continue
        try:
            info = child.lstat()
        except OSError:
            continue
        if not stat.S_ISDIR(info.st_mode):
            continue
        item = (info.st_mtime_ns, child.name, child)
        if len(recent) < DONJON_MAX_LISTED_JOBS:
            heapq.heappush(recent, item)
        else:
            heapq.heappushpop(recent, item)
    return [item[2] for item in sorted(recent, reverse=True)]


class _JobStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._owner_descriptors: dict[str, int] = {}

    def create(
        self,
        *,
        operation: str,
        archive_root: Path | None = None,
        working_directory: Path | None = None,
        request: dict[str, Any] | None = None,
        donjon_root: Path | None = None,
    ) -> dict[str, Any]:
        job_id = self._new_job_id(archive_root)
        run_directory = archive_root / job_id if archive_root is not None else None
        if run_directory is not None:
            run_directory.mkdir(parents=True, exist_ok=False)
            run_directory.chmod(0o700)
        owner_token = uuid4().hex if run_directory is not None else None
        owner_pid = os.getpid() if run_directory is not None else None
        owner_path = run_directory / "owner.lock" if run_directory is not None else None
        owner_descriptor = (
            _create_job_owner_lock(
                owner_path,
                job_id=job_id,
                owner_token=str(owner_token),
                owner_pid=int(owner_pid),
            )
            if owner_path is not None
            else None
        )
        request_path = run_directory / "request.json" if run_directory is not None else None
        status_path = run_directory / "status.json" if run_directory is not None else None
        artifacts_path = run_directory / "artifacts.json" if run_directory is not None else None
        manifest_snapshot_bytes = (
            request.get("_project_manifest_bytes") if request is not None else None
        )
        if manifest_snapshot_bytes is not None and not isinstance(
            manifest_snapshot_bytes, bytes
        ):
            raise ValueError("project manifest snapshot must be exact bytes")
        manifest_snapshot_path = (
            run_directory / "project-manifest.snapshot.json"
            if run_directory is not None and manifest_snapshot_bytes is not None
            else None
        )
        if manifest_snapshot_path is not None:
            expected_manifest_sha256 = request.get("project_manifest_sha256")
            if hashlib.sha256(manifest_snapshot_bytes).hexdigest() != expected_manifest_sha256:
                raise ValueError("project manifest snapshot hash changed before archival")
            manifest_snapshot_path.write_bytes(manifest_snapshot_bytes)
            manifest_snapshot_path.chmod(0o600)
        job = {
            "schema": DONJON_JOB_SCHEMA,
            "job_id": job_id,
            "run_id": job_id,
            "operation": operation,
            "owner_path": str(owner_path) if owner_path is not None else None,
            "owner_token": owner_token,
            "owner_pid": owner_pid,
            "status": "queued",
            "artifacts_finalized": False,
            "created_at": time.time(),
            "started_at": None,
            "finished_at": None,
            "message": "Queued.",
            "result_path": None,
            "deck_path": None,
            "deck_sha256": (
                hashlib.sha256(request["deck_text"].encode("utf-8")).hexdigest()
                if request is not None
                else None
            ),
            "source_deck_path": (
                request.get("source_deck_path") or None if request is not None else None
            ),
            "source_deck_sha256": (
                request.get("source_deck_sha256") or None if request is not None else None
            ),
            "project_root": (
                request.get("project_root") or None if request is not None else None
            ),
            "component_id": (
                request.get("component_id") or None if request is not None else None
            ),
            "declaration_sha256": (
                request.get("declaration_sha256") if request is not None else None
            ),
            "project_manifest_path": (
                request.get("project_manifest_path") or None
                if request is not None
                else None
            ),
            "project_manifest_sha256": (
                request.get("project_manifest_sha256") or None
                if request is not None
                else None
            ),
            "project_manifest_snapshot_path": (
                str(manifest_snapshot_path)
                if manifest_snapshot_path is not None
                else None
            ),
            "request_binding_sha256": (
                request.get("request_binding_sha256") or None
                if request is not None
                else None
            ),
            "k_effective": None,
            "return_code": None,
            "log_tail": "",
            "working_directory": (
                str(working_directory) if working_directory is not None else None
            ),
            "archive_root": str(archive_root) if archive_root is not None else None,
            "run_directory": str(run_directory) if run_directory is not None else None,
            "request_path": str(request_path) if request_path is not None else None,
            "status_path": str(status_path) if status_path is not None else None,
            "artifacts_path": str(artifacts_path) if artifacts_path is not None else None,
            "completion_path": (
                str(run_directory / "completion.json")
                if run_directory is not None
                else None
            ),
            "completion_sha256": None,
            "log_path": (
                str(run_directory / "run.log") if run_directory is not None else None
            ),
            "staged_manifest_path": (
                str(run_directory / "staged-inputs.json")
                if run_directory is not None
                else None
            ),
            "runtime_output_directory": (
                str(run_directory / "runtime-output")
                if run_directory is not None
                else None
            ),
        }
        with self._lock:
            try:
                self._jobs[job_id] = job
                if owner_descriptor is not None:
                    self._owner_descriptors[job_id] = owner_descriptor
                if request_path is not None and request is not None:
                    _atomic_write_json(
                        request_path,
                        _request_receipt(
                            job_id=job_id,
                            request=request,
                            working_directory=working_directory,
                            archive_root=archive_root,
                            donjon_root=donjon_root,
                            owner_path=owner_path,
                            owner_token=owner_token,
                            owner_pid=owner_pid,
                        ),
                    )
                self._persist(job)
                self._write_artifact_manifest(job)
            except Exception:
                self._jobs.pop(job_id, None)
                descriptor = self._owner_descriptors.pop(job_id, None)
                if descriptor is not None:
                    os.close(descriptor)
                raise
        return dict(job)

    def update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            self._jobs[job_id].update(values)
            self._persist(self._jobs[job_id])
            self._prune_terminal_cache()

    def publish_terminal(self, job_id: str, **values: Any) -> None:
        """Seal artifacts before atomically publishing a terminal status."""

        if values.get("status") not in {"completed", "failed"}:
            raise ValueError("terminal publication requires completed or failed status")
        with self._lock:
            terminal_job = {**self._jobs[job_id], **values, "artifacts_finalized": True}
        terminal_job = self._seal_terminal_job(terminal_job)
        with self._lock:
            self._jobs[job_id] = terminal_job
            self._persist(terminal_job)
            self._release_owner(job_id)
            self._prune_terminal_cache()

    def fail_closed(self, job_id: str, *, message: str) -> None:
        """Best-effort terminal publication that never leaves a live-looking job."""

        try:
            self.publish_terminal(
                job_id,
                status="failed",
                finished_at=time.time(),
                message=message,
                result_path=None,
                k_effective=None,
            )
            return
        except BaseException as exc:
            fallback_message = (
                f"{message} Terminal evidence could not be sealed: "
                f"{type(exc).__name__}: {exc}"
            )
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None:
                job.update(
                    status="failed",
                    artifacts_finalized=False,
                    finished_at=time.time(),
                    message=fallback_message,
                    result_path=None,
                    k_effective=None,
                )
                try:
                    self._persist(job)
                except BaseException:
                    pass
            self._release_owner(job_id)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            snapshot = None if job is None else dict(job)
        if (
            snapshot is not None
            and snapshot.get("status") == "completed"
            and snapshot.get("run_directory")
        ):
            issue = _terminal_completed_evidence_issue(snapshot)
            if (
                issue is None
                and _completion_receipt_matches(snapshot)
                and _artifact_manifest_matches(snapshot)
            ):
                return snapshot
            self.fail_closed(
                job_id,
                message=(
                    "Completed DONJON evidence changed after publication; the run "
                    f"is no longer valid. {issue or 'The terminal manifest changed.'}"
                ),
            )
            with self._lock:
                failed = self._jobs.get(job_id)
                return None if failed is None else dict(failed)
        return snapshot

    def recover(self, job_id: str, archive_root: Path) -> dict[str, Any] | None:
        if not _JOB_ID.fullmatch(job_id):
            return None
        recovered = _read_persisted_job(archive_root, job_id)
        if recovered is None:
            return None
        if recovered.get("status") in {"queued", "running"}:
            owner_descriptor = _try_claim_job_owner_lock(recovered)
            if owner_descriptor is None:
                return dict(recovered)
            try:
                self._fail_closed_interrupted(recovered)
            finally:
                os.close(owner_descriptor)
        with self._lock:
            self._jobs[job_id] = recovered
        return dict(recovered)

    def list(self, archive_root: Path) -> list[dict[str, Any]]:
        recovered: dict[str, dict[str, Any]] = {}
        foreign_live: dict[str, dict[str, Any]] = {}
        with self._lock:
            live = {
                job_id: dict(job)
                for job_id, job in self._jobs.items()
                if job.get("archive_root") == str(archive_root)
            }
        if archive_root.is_dir():
            for child in _recent_job_directories(archive_root):
                if child.name in live:
                    recovered[child.name] = live[child.name]
                    continue
                job = _read_persisted_job(archive_root, child.name)
                if job is not None:
                    if job.get("status") in {"queued", "running"}:
                        owner_descriptor = _try_claim_job_owner_lock(job)
                        if owner_descriptor is None:
                            foreign_live[child.name] = job
                            continue
                        try:
                            self._fail_closed_interrupted(job)
                        finally:
                            os.close(owner_descriptor)
                    recovered[child.name] = job
        with self._lock:
            recovered.update(live)
            self._jobs.update(recovered)
            self._prune_terminal_cache()
        return sorted(
            (dict(job) for job in {**foreign_live, **recovered}.values()),
            key=lambda job: float(job.get("created_at") or 0.0),
            reverse=True,
        )

    def _new_job_id(self, archive_root: Path | None) -> str:
        for _ in range(100):
            job_id = uuid4().hex[:16]
            if job_id in self._jobs:
                continue
            if archive_root is not None and (archive_root / job_id).exists():
                continue
            return job_id
        raise RuntimeError("could not allocate a unique DONJON job id")

    def _prune_terminal_cache(self) -> None:
        terminal = sorted(
            (
                (float(job.get("created_at") or 0.0), job_id)
                for job_id, job in self._jobs.items()
                if job.get("status") in {"completed", "failed"}
                and job_id not in self._owner_descriptors
            ),
            reverse=True,
        )
        for _, job_id in terminal[DONJON_MAX_CACHED_TERMINAL_JOBS:]:
            self._jobs.pop(job_id, None)

    def release_owner(self, job_id: str) -> None:
        """Release a job owner after its worker exits unexpectedly."""

        with self._lock:
            self._release_owner(job_id)

    def _release_owner(self, job_id: str) -> None:
        descriptor = self._owner_descriptors.pop(job_id, None)
        if descriptor is not None:
            os.close(descriptor)

    def _fail_closed_interrupted(self, job: dict[str, Any]) -> None:
        if job.get("status") not in {"queued", "running"}:
            return
        message = (
            "Recovered a persisted queued/running record without a live owning "
            "backend job; the process is treated as interrupted, not running."
        )
        previous_tail = str(job.get("log_tail") or "")
        job.update(
            status="failed",
            artifacts_finalized=True,
            finished_at=time.time(),
            message=message,
            log_tail="\n".join(part for part in (previous_tail, message) if part)[-12000:],
        )
        sealed = self._seal_terminal_job(job)
        job.clear()
        job.update(sealed)
        self._persist(sealed)

    @classmethod
    def _seal_terminal_job(cls, job: dict[str, Any]) -> dict[str, Any]:
        sealed = dict(job)
        raw_deck = sealed.get("deck_path")
        if isinstance(raw_deck, str):
            try:
                deck_matches = _file_sha256(Path(raw_deck)) == sealed.get(
                    "deck_sha256"
                )
            except OSError:
                deck_matches = False
            if not deck_matches:
                sealed.update(
                    status="failed",
                    deck_path=None,
                    result_path=None,
                    k_effective=None,
                    message=(
                        "Archived deck changed before terminal evidence was sealed; "
                        "this run is not valid."
                    ),
                )
        semantic_issue = _terminal_completed_evidence_issue(sealed)
        if semantic_issue is not None:
            _downgrade_terminal_evidence(sealed, semantic_issue)
        cls._write_terminal_receipts(sealed)
        if sealed.get("status") == "completed":
            semantic_issue = _terminal_completed_evidence_issue(sealed)
            if semantic_issue is None and not _artifact_manifest_matches(sealed):
                semantic_issue = "The terminal artifact manifest is inconsistent."
            if semantic_issue is not None:
                _downgrade_terminal_evidence(sealed, semantic_issue)
                cls._write_terminal_receipts(sealed)
        return sealed

    @classmethod
    def _write_terminal_receipts(cls, sealed: dict[str, Any]) -> None:
        raw_completion = sealed.get("completion_path")
        if not isinstance(raw_completion, str):
            raise RuntimeError("terminal DONJON job has no completion receipt path")
        completion_path = Path(raw_completion)
        _atomic_write_json(
            completion_path,
            {
                "schema": DONJON_COMPLETION_SCHEMA,
                "job_id": sealed["job_id"],
                "run_id": sealed["job_id"],
                "status": _completion_projection(sealed),
            },
        )
        sealed["completion_sha256"] = _file_sha256(completion_path)
        cls._write_artifact_manifest(sealed)

    @staticmethod
    def _persist(job: dict[str, Any]) -> None:
        raw = job.get("status_path")
        if raw:
            _atomic_write_json(Path(str(raw)), job)

    @staticmethod
    def _write_artifact_manifest(job: dict[str, Any]) -> None:
        raw_run = job.get("run_directory")
        raw_manifest = job.get("artifacts_path")
        if not raw_run or not raw_manifest:
            return
        run_directory = Path(str(raw_run))
        manifest_path = Path(str(raw_manifest))
        if not run_directory.is_dir():
            return
        artifacts: list[dict[str, Any]] = []
        for path in _job_evidence_files(run_directory, manifest_path=manifest_path):
            artifacts.append(
                {
                    "path": str(path),
                    "relative_path": path.relative_to(run_directory).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _file_sha256(path),
                }
            )
        _atomic_write_json(
            manifest_path,
            {
                "schema": DONJON_ARTIFACT_MANIFEST_SCHEMA,
                "job_id": job["job_id"],
                "run_id": job["job_id"],
                "status": job["status"],
                "generated_at": time.time(),
                "artifacts": artifacts,
            },
        )


def register_execution_routes(
    app: Any,
    *,
    mock_mode: bool,
    filesystem_scope: FilesystemScope,
) -> None:
    """Register named, bounded execution operations."""

    from fastapi import Body, HTTPException

    jobs = _JobStore()
    execution_shutdown = Event()
    body = Body(...)
    job_slots = BoundedSemaphore(DONJON_MAX_CONCURRENT_JOBS)
    worker_lock = Lock()
    worker_threads: set[Thread] = set()
    stopping = False
    def run_donjon_worker(
        *,
        job_id: str,
        request: dict[str, Any],
        root: Path,
    ) -> None:
        try:
            _run_donjon_job(
                jobs=jobs,
                job_id=job_id,
                request=request,
                root=root,
                shutdown_event=execution_shutdown,
            )
        except BaseException as exc:
            jobs.fail_closed(
                job_id,
                message=(
                    "DONJON worker failed unexpectedly: "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        finally:
            jobs.release_owner(job_id)
            job_slots.release()
            with worker_lock:
                worker_threads.discard(current_thread())

    def shutdown_execution() -> None:
        nonlocal stopping
        with worker_lock:
            stopping = True
            pending = list(worker_threads)
        execution_shutdown.set()
        _terminate_active_rdonjon_processes(
            shutdown_event=execution_shutdown
        )
        deadline = time.monotonic() + 10.0
        for worker in pending:
            worker.join(timeout=max(0.0, deadline - time.monotonic()))

    app.router.add_event_handler("shutdown", shutdown_execution)

    @app.post("/api/execute/openmc-export")
    def execute_openmc_export(payload: dict[str, Any] = body) -> dict[str, Any]:
        request = _normalize_openmc_export(payload, HTTPException)
        if mock_mode:
            return {
                "schema": OPENMC_EXPORT_EXECUTION_SCHEMA,
                "ok": True,
                "mock_mode": True,
                "output_path": request["output_path"],
                "energy_groups": 33,
                "legendre_order": 1,
                "mixtures": 7,
                "std_dev_datasets": 56,
                "std_dev_expected": 56,
                "openmc_provenance": _mock_openmc_provenance(),
            }
        recipe = _input_file(
            request["recipe_path"], HTTPException, filesystem_scope, suffix=".py"
        )
        statepoint = None
        if request["load_statepoint"]:
            statepoint = _input_file(
                request["statepoint_path"],
                HTTPException,
                filesystem_scope,
                suffix=".h5",
            )
        output = _output_file(
            request["output_path"],
            HTTPException,
            filesystem_scope,
            overwrite=request["overwrite"],
        )
        try:
            summary = export_openmc_statepoint_recipe(
                recipe,
                output,
                statepoint_path=statepoint,
                load_statepoint=request["load_statepoint"],
                overwrite=request["overwrite"],
            )
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=f"OpenMC export failed: {exc}") from exc
        exported = summary.output
        return {
            "schema": OPENMC_EXPORT_EXECUTION_SCHEMA,
            "ok": True,
            "mock_mode": False,
            "output_path": str(exported.output_path),
            "energy_groups": exported.energy_groups,
            "legendre_order": exported.legendre_order,
            "mixtures": len(exported.domains),
            "std_dev_datasets": exported.std_dev_dataset_count,
            "std_dev_expected": exported.std_dev_expected_dataset_count,
            "openmc_provenance": dict(summary.provenance),
        }

    @app.post("/api/execute/sph-sidecar")
    def execute_sph_sidecar(payload: dict[str, Any] = body) -> dict[str, Any]:
        request = _normalize_sph_sidecar(payload, HTTPException)
        if mock_mode:
            return {
                "schema": SPH_EXECUTION_SCHEMA,
                "ok": True,
                "operation": "sph-sidecar",
                "output_path": request["output_path"],
                "table_path": request.get("table_output"),
                "summary_path": request.get("summary_json"),
                "mixtures": 7,
                "energy_groups": 33,
                "sph_min": 1.0,
                "sph_max": 1.0,
                "strategy": "ratio",
                "raw_update_minimum": 1.0,
                "raw_update_maximum": 1.0,
                "max_update_residual": 0.0,
                "converged": True,
            }
        input_h5 = _input_file(
            request["input_h5"], HTTPException, filesystem_scope, suffix=".h5"
        )
        output_h5 = _output_file(
            request["output_path"],
            HTTPException,
            filesystem_scope,
            overwrite=request["force"],
        )
        summary_path = _optional_json_output(
            request["summary_json"],
            HTTPException,
            filesystem_scope,
            overwrite=request["force"],
        )
        if summary_path == output_h5:
            raise HTTPException(
                status_code=422,
                detail="summary_json must be different from output_path",
            )
        try:
            reference_flux = _scoped_dataset_spec(
                request["reference_flux"], HTTPException, filesystem_scope
            )
            mg_flux = _scoped_dataset_spec(
                request["mg_flux"], HTTPException, filesystem_scope
            )
            table_output = _output_file(
                request["table_output"],
                HTTPException,
                filesystem_scope,
                overwrite=request["force"],
            )
            if summary_path == table_output:
                raise HTTPException(
                    status_code=422,
                    detail="summary_json must be different from table_output",
                )
            report = create_openmc_sph_sidecar(
                input_h5,
                output_h5,
                reference_flux=reference_flux,
                mg_flux=mg_flux,
                table_output=table_output,
                previous_sph=(
                    None
                    if not request["previous_sph"]
                    else _scoped_previous_sph(
                        request["previous_sph"], HTTPException, filesystem_scope
                    )
                ),
                damping=request["damping"],
                flux_normalization=request["flux_normalization"],
                sph_target=request["sph_target"],
                zero_flux_policy=request["zero_flux_policy"],
                flux_floor_rel=request["flux_floor_rel"],
                freeze_groups=request["freeze_groups"],
                clip_min=request["clip_min"],
                clip_max=request["clip_max"],
                require_reference_flux_std_dev=True,
                max_reference_flux_std_dev_rel=0.20,
                require_mg_flux_std_dev=True,
                max_mg_flux_std_dev_rel=0.20,
                force=request["force"],
                summary_json=summary_path,
            )
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"SPH sidecar failed: {exc}") from exc
        raw_minimum = float(report.update.raw_update_minimum)
        raw_maximum = float(report.update.raw_update_maximum)
        max_update_residual = max(abs(raw_minimum - 1.0), abs(raw_maximum - 1.0))
        return {
            "schema": SPH_EXECUTION_SCHEMA,
            "ok": True,
            "operation": "sph-sidecar",
            "strategy": "ratio",
            "output_path": str(report.output_h5),
            "table_path": str(report.output_table),
            "summary_path": None if summary_path is None else str(summary_path),
            "mixtures": len(report.sidecar.mixture_names),
            "energy_groups": report.sidecar.energy_groups,
            "sph_min": report.sidecar.sph_min,
            "sph_max": report.sidecar.sph_max,
            "raw_update_minimum": raw_minimum,
            "raw_update_maximum": raw_maximum,
            "max_update_residual": max_update_residual,
            "converged": max_update_residual <= SPH_MAX_UPDATE_RESIDUAL,
        }

    @app.post("/api/execute/apply-sph")
    def execute_apply_sph(payload: dict[str, Any] = body) -> dict[str, Any]:
        request = _normalize_apply_sph(payload, HTTPException)
        if mock_mode:
            return {
                "schema": SPH_EXECUTION_SCHEMA,
                "ok": True,
                "operation": "apply-sph",
                "output_path": request["output_path"],
                "summary_path": request.get("summary_json"),
                "mixtures": 7,
                "energy_groups": 33,
                "scaled_datasets": 56,
                "sph_min": 1.0,
                "sph_max": 1.0,
            }
        input_h5 = _input_file(
            request["input_h5"], HTTPException, filesystem_scope, suffix=".h5"
        )
        sph_source = _input_file(
            request["sph_source"], HTTPException, filesystem_scope, suffix=".h5"
        )
        _validate_physical_sph_source(sph_source, HTTPException)
        output_h5 = _output_file(
            request["output_path"],
            HTTPException,
            filesystem_scope,
            overwrite=request["force"],
        )
        summary_path = _optional_json_output(
            request["summary_json"],
            HTTPException,
            filesystem_scope,
            overwrite=request["force"],
        )
        if summary_path == output_h5:
            raise HTTPException(
                status_code=422,
                detail="summary_json must be different from output_path",
            )
        try:
            operation = (
                apply_sph_to_hdf5
                if request["input_format"] == "converter"
                else apply_sph_to_openmc_mgxs_hdf5
            )
            report = operation(
                input_h5,
                sph_source=sph_source,
                output_h5=output_h5,
                force=request["force"],
            )
            if summary_path is not None:
                write_sph_apply_summary(summary_path, report)
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
            raise HTTPException(status_code=422, detail=f"apply-sph failed: {exc}") from exc
        return {
            "schema": SPH_EXECUTION_SCHEMA,
            "ok": True,
            "operation": "apply-sph",
            "output_path": str(report.output_h5),
            "summary_path": None if summary_path is None else str(summary_path),
            "mixtures": len(report.mixture_names),
            "energy_groups": report.energy_groups,
            "scaled_datasets": report.scaled_dataset_count,
            "sph_min": report.sph_min,
            "sph_max": report.sph_max,
        }

    @app.post("/api/execute/donjon")
    def execute_donjon(payload: dict[str, Any] = body) -> dict[str, Any]:
        request = _normalize_donjon(payload, HTTPException)
        if mock_mode:
            mock_working_directory = (
                Path(request["working_directory"]).expanduser().resolve()
                if request["working_directory"]
                else None
            )
            _validate_deck_file_paths(
                request["deck_text"],
                working_directory=mock_working_directory,
                declared_input_paths={
                    item["relative_path"] for item in request["input_files"]
                },
                filesystem_scope=filesystem_scope,
                http_exception=HTTPException,
            )
            job = jobs.create(
                operation="donjon",
                working_directory=mock_working_directory,
                request=request,
            )
            jobs.update(
                job["job_id"],
                status="completed",
                started_at=time.time(),
                finished_at=time.time(),
                message="Mock DONJON solve completed.",
                k_effective=1.145655,
                return_code=0,
                log_tail="k-effective = 1.145655",
            )
            return jobs.get(job["job_id"]) or job
        root = _donjon_root(request["donjon_root"], HTTPException, filesystem_scope)
        donjon_dir = root / "Donjon"
        machine = f"{platform.system()}_{platform.machine()}"
        try:
            request["launcher_sha256"] = _file_sha256(donjon_dir / "rdonjon")
            request["solver_sha256"] = _file_sha256(
                donjon_dir / "bin" / machine / "Donjon"
            )
        except OSError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"could not bind the trusted DONJON installation: {exc}",
            ) from exc
        archive_root = filesystem_scope.resolve(
            request["artifact_directory"]
            or str(donjon_dir / "data" / ".openmc2donjon-web-runs"),
            HTTPException,
        )
        working_directory = None
        if request["working_directory"]:
            working_directory = filesystem_scope.resolve(
                request["working_directory"], HTTPException
            )
            if not working_directory.is_dir():
                raise HTTPException(
                    status_code=404,
                    detail=f"working_directory not found: {working_directory}",
                )
        request["input_files"] = _bind_declared_input_files(
            request["input_files"],
            filesystem_scope=filesystem_scope,
            http_exception=HTTPException,
        )
        source_deck_path = None
        if request["source_deck_path"]:
            source_deck_path = filesystem_scope.resolve(
                request["source_deck_path"], HTTPException
            )
            if not source_deck_path.is_file() or source_deck_path.suffix.lower() != ".x2m":
                raise HTTPException(
                    status_code=404,
                    detail=f"source_deck_path is not a .x2m file: {source_deck_path}",
                )
            actual_source_sha256 = _file_sha256(source_deck_path)
            submitted_sha256 = hashlib.sha256(
                request["deck_text"].encode("utf-8")
            ).hexdigest()
            if request["source_deck_sha256"] != actual_source_sha256:
                raise HTTPException(
                    status_code=409,
                    detail="source deck changed after it was loaded; reload it before running",
                )
            if submitted_sha256 != actual_source_sha256:
                raise HTTPException(
                    status_code=409,
                    detail="submitted deck text is not the exact source deck bytes",
                )
        project_root = None
        if request["project_root"]:
            project_root = filesystem_scope.resolve(request["project_root"], HTTPException)
            if not project_root.is_dir():
                raise HTTPException(
                    status_code=404,
                    detail=f"project_root not found: {project_root}",
                )
        if request["component_id"] and project_root is None:
            raise HTTPException(
                status_code=422,
                detail="component_id binding requires project_root",
            )
        if request["component_id"] and source_deck_path is not None and request["input_files"]:
            raise HTTPException(
                status_code=422,
                detail=(
                    "project-bound component runs must obtain FILE inputs from the "
                    "manifest-declared working_directory"
                ),
            )
        project_binding: dict[str, str] | None = None
        if request["component_id"]:
            assert project_root is not None
            if source_deck_path is not None:
                project_binding = _project_native_sph_binding(
                    project_root=project_root,
                    component_id=request["component_id"],
                    source_deck_path=source_deck_path,
                    working_directory=working_directory,
                    http_exception=HTTPException,
                )
            else:
                project_binding = _project_component_diagnostic_binding(
                    project_root=project_root,
                    component_id=request["component_id"],
                    input_files=request["input_files"],
                    http_exception=HTTPException,
                )
        _validate_deck_file_paths(
            request["deck_text"],
            working_directory=working_directory,
            declared_input_paths={
                item["relative_path"] for item in request["input_files"]
            },
            filesystem_scope=filesystem_scope,
            http_exception=HTTPException,
        )
        request["artifact_directory"] = str(archive_root)
        request["working_directory"] = (
            str(working_directory) if working_directory is not None else ""
        )
        request["source_deck_path"] = (
            str(source_deck_path) if source_deck_path is not None else ""
        )
        request["project_root"] = str(project_root) if project_root is not None else ""
        if project_binding is not None:
            request.update(project_binding)
        else:
            binding = {
                "deck_sha256": hashlib.sha256(
                    request["deck_text"].encode("utf-8")
                ).hexdigest(),
                "source_deck_sha256": request["source_deck_sha256"] or None,
                "project_root": request["project_root"],
                "source_deck_path": request["source_deck_path"],
                "working_directory": request["working_directory"],
                "input_files": request["input_files"],
            }
            request["request_binding_sha256"] = hashlib.sha256(
                json.dumps(binding, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        with worker_lock:
            if stopping:
                raise HTTPException(
                    status_code=503,
                    detail="the web service is shutting down; new DONJON jobs are closed",
                )
        if not job_slots.acquire(blocking=False):
            raise HTTPException(
                status_code=429,
                detail=(
                    "the bounded DONJON queue is full; wait for an active job "
                    "to finish before submitting another"
                ),
            )
        try:
            job = jobs.create(
                operation="donjon",
                archive_root=archive_root,
                working_directory=working_directory,
                request=request,
                donjon_root=root,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            job_slots.release()
            raise HTTPException(
                status_code=422,
                detail=f"could not create the DONJON job archive: {exc}",
            ) from exc
        request.pop("_project_manifest_bytes", None)
        try:
            thread = Thread(
                target=run_donjon_worker,
                kwargs={"job_id": job["job_id"], "request": request, "root": root},
                daemon=True,
            )
        except Exception as exc:
            job_slots.release()
            jobs.fail_closed(
                job["job_id"],
                message=f"DONJON worker could not be constructed: {exc}",
            )
            raise HTTPException(
                status_code=503,
                detail="the DONJON worker could not be constructed",
            ) from exc
        with worker_lock:
            if stopping:
                job_slots.release()
                jobs.fail_closed(
                    job["job_id"],
                    message="DONJON job cancelled because the web service is shutting down.",
                )
                raise HTTPException(
                    status_code=503,
                    detail="the web service is shutting down; DONJON job was cancelled",
                )
            worker_threads.add(thread)
            try:
                thread.start()
            except RuntimeError as exc:
                worker_threads.discard(thread)
                job_slots.release()
                jobs.fail_closed(
                    job["job_id"],
                    message=f"DONJON worker could not start: {exc}",
                )
                raise HTTPException(
                    status_code=503,
                    detail="the DONJON worker could not be started",
                ) from exc
        return job

    @app.get("/api/execution/jobs")
    def execution_jobs(artifact_directory: str) -> dict[str, Any]:
        archive_root = filesystem_scope.resolve(artifact_directory, HTTPException)
        return {
            "schema": DONJON_JOB_LIST_SCHEMA,
            "artifact_directory": str(archive_root),
            "jobs": jobs.list(archive_root),
        }

    @app.get("/api/execution/jobs/{job_id}")
    def execution_job(job_id: str, artifact_directory: str = "") -> dict[str, Any]:
        if not _JOB_ID.fullmatch(job_id):
            raise HTTPException(status_code=404, detail=f"execution job not found: {job_id}")
        job = jobs.get(job_id)
        if job is None and artifact_directory:
            archive_root = filesystem_scope.resolve(artifact_directory, HTTPException)
            job = jobs.recover(job_id, archive_root)
        if job is None:
            raise HTTPException(status_code=404, detail=f"execution job not found: {job_id}")
        return job


def _normalize_openmc_export(payload: Any, http_exception: Any) -> dict[str, Any]:
    data = _object(payload, http_exception)
    return {
        "recipe_path": _required_text(data, "recipe_path", http_exception),
        "statepoint_path": _text(data.get("statepoint_path")),
        "load_statepoint": _boolean(data.get("load_statepoint", True), "load_statepoint", http_exception),
        "output_path": _required_text(data, "output_path", http_exception),
        "overwrite": _boolean(data.get("overwrite", False), "overwrite", http_exception),
    }


def _normalize_sph_sidecar(payload: Any, http_exception: Any) -> dict[str, Any]:
    data = _object(payload, http_exception)
    strategy = _choice(data.get("strategy", "ratio"), {"ratio"}, "strategy", http_exception)
    freeze = _integer_list(data.get("freeze_groups", []), "freeze_groups", http_exception)
    flux_floor_rel = _optional_number(data.get("flux_floor_rel"), "flux_floor_rel", http_exception)
    clip_min = _optional_number(data.get("clip_min"), "clip_min", http_exception)
    clip_max = _optional_number(data.get("clip_max"), "clip_max", http_exception)
    damping = _number(data.get("damping", 1.0), "damping", http_exception)
    if damping < 0.0 or damping > 1.0:
        raise http_exception(
            status_code=422,
            detail="damping must be finite and within 0..1",
        )
    if freeze or flux_floor_rel is not None or clip_min is not None or clip_max is not None:
        raise http_exception(
            status_code=422,
            detail=(
                "production SPH forbids frozen groups, flux floors, and clipping; "
                "increase tally statistics instead"
            ),
        )
    return {
        "strategy": strategy,
        "input_h5": _required_text(data, "input_h5", http_exception),
        "output_path": _required_text(data, "output_path", http_exception),
        "reference_flux": _required_text(data, "reference_flux", http_exception),
        "mg_flux": _required_text(data, "mg_flux", http_exception),
        "previous_sph": _text(data.get("previous_sph")),
        "table_output": _text(data.get("table_output"))
        or str(
            Path(_required_text(data, "output_path", http_exception)).with_suffix(
                ".csv"
            )
        ),
        "summary_json": _text(data.get("summary_json")),
        "damping": damping,
        "flux_normalization": _choice(
            data.get("flux_normalization", "auto"),
            {"auto"},
            "flux_normalization",
            http_exception,
        ),
        "sph_target": _choice(data.get("sph_target", "rate"), {"rate"}, "sph_target", http_exception),
        "zero_flux_policy": _choice(
            data.get("zero_flux_policy", "reject"),
            {"reject"},
            "zero_flux_policy",
            http_exception,
        ),
        "flux_floor_rel": flux_floor_rel,
        "freeze_groups": tuple(freeze) if freeze else None,
        "clip_min": clip_min,
        "clip_max": clip_max,
        "force": _boolean(data.get("force", False), "force", http_exception),
    }


def _normalize_apply_sph(payload: Any, http_exception: Any) -> dict[str, Any]:
    data = _object(payload, http_exception)
    return {
        "input_h5": _required_text(data, "input_h5", http_exception),
        "sph_source": _required_text(data, "sph_source", http_exception),
        "output_path": _required_text(data, "output_path", http_exception),
        "input_format": _choice(
            data.get("input_format", "converter"),
            {"converter", "openmc-mgxs"},
            "input_format",
            http_exception,
        ),
        "summary_json": _text(data.get("summary_json")),
        "force": _boolean(data.get("force", False), "force", http_exception),
    }


def _normalize_donjon(payload: Any, http_exception: Any) -> dict[str, Any]:
    data = _object(payload, http_exception)
    raw_deck = data.get("deck_text")
    if not isinstance(raw_deck, str) or not raw_deck.strip():
        raise http_exception(
            status_code=422, detail="deck_text must be a non-empty string"
        )
    # Unlike ordinary form values, deck bytes are physics input. Preserve all
    # whitespace, line endings, and the final newline exactly as submitted.
    deck = raw_deck
    if len(deck.encode("utf-8")) > 1_000_000:
        raise http_exception(status_code=422, detail="deck_text exceeds 1 MB")
    filename = _required_text(data, "deck_filename", http_exception)
    if not _DECK_NAME.fullmatch(filename) or Path(filename).name != filename:
        raise http_exception(status_code=422, detail="deck_filename must be a simple .x2m filename")
    timeout = int(_positive_number(data.get("timeout_seconds", 1800), "timeout_seconds", http_exception))
    source_deck_path = _text(data.get("source_deck_path"))
    source_deck_sha256 = _text(data.get("source_deck_sha256")).lower()
    if source_deck_path and not _SHA256.fullmatch(source_deck_sha256):
        raise http_exception(
            status_code=422,
            detail="source_deck_sha256 is required and must be lowercase SHA-256",
        )
    if source_deck_sha256 and not source_deck_path:
        raise http_exception(
            status_code=422,
            detail="source_deck_sha256 requires source_deck_path",
        )
    component_id = _text(data.get("component_id"))
    if component_id and not _COMPONENT_ID.fullmatch(component_id):
        raise http_exception(status_code=422, detail="component_id is invalid")
    raw_input_files = data.get("input_files", [])
    if raw_input_files is None:
        raw_input_files = []
    if not isinstance(raw_input_files, list):
        raise http_exception(status_code=422, detail="input_files must be a list")
    if len(raw_input_files) > DONJON_MAX_DECLARED_INPUT_FILES:
        raise http_exception(
            status_code=422,
            detail=(
                "input_files exceeds the bounded declared-input count "
                f"({DONJON_MAX_DECLARED_INPUT_FILES})"
            ),
        )
    input_files: list[dict[str, str]] = []
    seen_relative_paths: set[str] = set()
    for index, raw_input in enumerate(raw_input_files):
        if not isinstance(raw_input, dict):
            raise http_exception(
                status_code=422,
                detail=f"input_files[{index}] must be an object",
            )
        source_path = _required_text(raw_input, "source_path", http_exception)
        relative_path = _required_text(raw_input, "relative_path", http_exception)
        try:
            relative = _declared_input_relative_path(relative_path)
        except ValueError as exc:
            raise http_exception(status_code=422, detail=str(exc)) from exc
        normalized_relative = relative.as_posix()
        if normalized_relative in seen_relative_paths:
            raise http_exception(
                status_code=422,
                detail=f"input_files repeats relative_path: {normalized_relative}",
            )
        seen_relative_paths.add(normalized_relative)
        input_files.append(
            {
                "source_path": source_path,
                "relative_path": normalized_relative,
            }
        )
    return {
        "deck_text": deck,
        "deck_filename": filename,
        "donjon_root": _text(data.get("donjon_root")),
        "artifact_directory": _text(data.get("artifact_directory")),
        "working_directory": _text(data.get("working_directory")),
        "source_deck_path": source_deck_path,
        "source_deck_sha256": source_deck_sha256,
        "project_root": _text(data.get("project_root")),
        "component_id": component_id,
        "input_files": input_files,
        "timeout_seconds": min(timeout, DONJON_MAX_TIMEOUT_SECONDS),
        "expect_k_effective": _boolean(
            data.get("expect_k_effective", True),
            "expect_k_effective",
            http_exception,
        ),
    }


def _run_donjon_job(
    *,
    jobs: _JobStore,
    job_id: str,
    request: dict[str, Any],
    root: Path,
    shutdown_event: Event | None = None,
) -> None:
    donjon_dir = root / "Donjon"
    unique_stem = f"openmc2donjon_web_{job_id}"
    deck_name = f"{unique_stem}.x2m"
    transient_deck_path = donjon_dir / "data" / deck_name
    access_hook_path = donjon_dir / "data" / f"{unique_stem}.access"
    save_hook_path = donjon_dir / "data" / f"{unique_stem}.save"
    machine = f"{platform.system()}_{platform.machine()}"
    solver_result_path = donjon_dir / machine / f"{unique_stem}.result"
    run_directory = Path(str(request["artifact_directory"])) / job_id
    archived_deck_path = run_directory / request["deck_filename"]
    log_path = run_directory / "run.log"
    archived_result_path = run_directory / f"{Path(request['deck_filename']).stem}.result"
    working_directory = (
        Path(request["working_directory"]) if request.get("working_directory") else None
    )
    staged_directory = run_directory / "staged-working-directory"
    staged_manifest_path = run_directory / "staged-inputs.json"
    runtime_output_directory = run_directory / "runtime-output"
    runtime_output_manifest_path = run_directory / "runtime-output-manifest.json"
    access_receipt_path = run_directory / "access-receipt.json"
    hook_helper_path = run_directory / "rdonjon-hook.py"
    isolated_launcher_path = run_directory / "rdonjon-isolated"
    isolated_solver_path = run_directory / "Donjon-solver"
    transient_paths: tuple[Path, ...] = ()
    isolated_tmp_root: Path | None = None
    launcher_owned = False
    staged_total_bytes = 0
    staged_entry_count = 0
    try:
        _raise_if_execution_stopped(
            shutdown_event, "; DONJON job was not started"
        )
        while not _RDONJON_PROCESS_LOCK.acquire(timeout=0.1):
            _raise_if_execution_stopped(
                shutdown_event, "; queued DONJON launcher wait was cancelled"
            )
        launcher_owned = True
        _raise_if_execution_stopped(
            shutdown_event, "; queued DONJON job was cancelled"
        )
        trusted_launcher = donjon_dir / "rdonjon"
        trusted_solver = donjon_dir / "bin" / machine / "Donjon"
        launcher_bytes = _read_trusted_file_bytes(
            trusted_launcher,
            expected_sha256=request.get("launcher_sha256"),
            label="rdonjon launcher",
            max_bytes=DONJON_MAX_LAUNCHER_BYTES,
        )
        solver_bytes = _read_trusted_file_bytes(
            trusted_solver,
            expected_sha256=request.get("solver_sha256"),
            label="DONJON solver",
            max_bytes=DONJON_MAX_SOLVER_BYTES,
        )
        isolated_launcher_path.write_text(
            _isolated_rdonjon_launcher_source(
                launcher_bytes.decode("utf-8", errors="strict")
            ),
            encoding="utf-8",
        )
        isolated_launcher_path.chmod(0o700)
        isolated_solver_path.write_bytes(solver_bytes)
        isolated_solver_path.chmod(0o700)
        admitted_deck_bytes = request["deck_text"].encode("utf-8")
        archived_deck_path.write_bytes(admitted_deck_bytes)
        archived_deck_path.chmod(0o600)
        if _file_sha256(archived_deck_path) != hashlib.sha256(
            admitted_deck_bytes
        ).hexdigest():
            raise RuntimeError("archived deck does not match the admitted deck bytes")
        if working_directory is not None:
            staging = _stage_working_directory(
                working_directory,
                staged_directory,
                exclude_roots=(Path(str(request["artifact_directory"])),),
                shutdown_event=shutdown_event,
            )
            staged_total_bytes = int(staging["total_bytes"])
            staged_entry_count = int(staging["entry_count"])
        else:
            staged_directory.mkdir(mode=0o700)
            staging = {
                "entry_count": 0,
                "directory_count": 0,
                "directories": [],
                "file_count": 0,
                "total_bytes": 0,
                "excluded_paths": [],
                "artifacts": [],
            }
        if request.get("input_files"):
            staging = _stage_declared_input_files(
                request["input_files"],
                staged_directory,
                existing=staging,
                shutdown_event=shutdown_event,
            )
            staged_total_bytes = int(staging["total_bytes"])
            staged_entry_count = int(staging["entry_count"])
        _atomic_write_json(
            staged_manifest_path,
            {
                "schema": DONJON_STAGING_SCHEMA,
                "job_id": job_id,
                "working_directory": (
                    str(working_directory) if working_directory is not None else None
                ),
                **staging,
            },
        )
        hook_helper_path.write_text(_rdonjon_fixed_hook_source(), encoding="utf-8")
        hook_helper_path.chmod(0o600)
        transient_paths = (access_hook_path, save_hook_path)
        for hook_path in transient_paths:
            hook_path.write_text(_rdonjon_hook_wrapper_source(), encoding="utf-8")
            hook_path.chmod(0o700)
        jobs.update(
            job_id,
            status="queued",
            message="Prepared; waiting for exclusive rdonjon launcher ownership.",
            deck_path=str(archived_deck_path),
        )
        environment = _donjon_execution_environment()
        _require_execution_free_space(
            (
                (
                    Path(tempfile.gettempdir()),
                    staged_total_bytes + DONJON_MAX_RUNTIME_OUTPUT_BYTES,
                ),
                (
                    run_directory,
                    DONJON_MAX_RUNTIME_OUTPUT_BYTES + DONJON_MAX_RESULT_BYTES,
                ),
                (
                    solver_result_path.parent,
                    DONJON_MAX_SINGLE_RUNTIME_FILE_BYTES,
                ),
            )
        )
        isolated_tmp_root = Path(
            tempfile.mkdtemp(prefix=f"o2d-{job_id}-", dir=tempfile.gettempdir())
        ).resolve()
        environment["OPENMC2DONJON_WEB_TMPDIR"] = str(isolated_tmp_root)
        environment["TMPDIR"] = str(isolated_tmp_root)
        environment["OPENMC2DONJON_WEB_SOLVER"] = str(isolated_solver_path)
        environment["OPENMC2DONJON_WEB_DECK"] = str(archived_deck_path)
        environment["OPENMC2DONJON_WEB_EXPECTED_DECK_SHA256"] = hashlib.sha256(
            request["deck_text"].encode("utf-8")
        ).hexdigest()
        environment["OPENMC2DONJON_WEB_MAX_FILE_BLOCKS"] = str(
            (DONJON_MAX_SINGLE_RUNTIME_FILE_BYTES + 511) // 512
        )
        environment.update(
            {
                "OPENMC2DONJON_WEB_JOB_ID": job_id,
                "OPENMC2DONJON_WEB_STAGED_DIRECTORY": str(staged_directory),
                "OPENMC2DONJON_WEB_STAGED_MANIFEST": str(staged_manifest_path),
                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_DIRECTORY": str(
                    runtime_output_directory
                ),
                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_MANIFEST": str(
                    runtime_output_manifest_path
                ),
                "OPENMC2DONJON_WEB_ACCESS_RECEIPT": str(access_receipt_path),
                "OPENMC2DONJON_WEB_PYTHON": sys.executable,
                "OPENMC2DONJON_WEB_HOOK_HELPER": str(hook_helper_path),
                "OPENMC2DONJON_WEB_MAX_OUTPUT_FILES": str(
                    DONJON_MAX_RUNTIME_OUTPUT_FILES
                ),
                "OPENMC2DONJON_WEB_MAX_OUTPUT_ENTRIES": str(
                    DONJON_MAX_RUNTIME_OUTPUT_ENTRIES
                ),
                "OPENMC2DONJON_WEB_MAX_OUTPUT_BYTES": str(
                    DONJON_MAX_RUNTIME_OUTPUT_BYTES
                ),
            }
        )
        jobs.update(
            job_id,
            status="running",
            started_at=time.time(),
            message="DONJON is running; process completion is not physics acceptance.",
        )
        completed = _run_rdonjon_bounded(
            [str(isolated_launcher_path), "-q", deck_name],
            cwd=donjon_dir,
            env=environment,
            timeout=request["timeout_seconds"],
            shutdown_event=shutdown_event,
            runtime_root=isolated_tmp_root,
            runtime_max_bytes=(
                staged_total_bytes
                + DONJON_MAX_RUNTIME_OUTPUT_BYTES
                + len(solver_bytes)
                + DONJON_RUNTIME_RESERVE_BYTES
            ),
            runtime_max_entries=(
                staged_entry_count + DONJON_MAX_RUNTIME_OUTPUT_ENTRIES + 256
            ),
            result_path=solver_result_path,
            result_max_bytes=DONJON_MAX_RESULT_BYTES,
        )
        result_text = ""
        result_snapshot_issue: str | None = None
        try:
            result_text = _archive_result_snapshot(
                solver_result_path,
                archived_result_path,
                max_bytes=DONJON_MAX_RESULT_BYTES,
                tail_bytes=1_000_000,
            )
            result_within_bound = True
        except (OSError, RuntimeError, ValueError) as exc:
            result_snapshot_issue = str(exc)
            result_within_bound = False
        combined = "\n".join(
            part for part in (completed.stdout, completed.stderr, result_text) if part
        )
        log_path.write_text(combined, encoding="utf-8")
        keff = parse_donjon_k_effective(result_text)
        staging_issue = None
        try:
            _validate_rdonjon_hook_evidence(
                job_id=job_id,
                expected_deck_sha256=hashlib.sha256(
                    request["deck_text"].encode("utf-8")
                ).hexdigest(),
                access_receipt_path=access_receipt_path,
                staged_manifest_path=staged_manifest_path,
                runtime_output_manifest_path=runtime_output_manifest_path,
                runtime_output_directory=runtime_output_directory,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            staging_issue = str(exc)
        staging_complete = staging_issue is None
        has_expected_result = (
            (keff is not None or not request["expect_k_effective"])
            and result_within_bound
        )
        status = (
            "completed"
            if completed.returncode == 0
            and has_expected_result
            and staging_complete
            else "failed"
        )
        message = (
            f"DONJON completed with k-effective={keff:.6f}."
            if status == "completed" and keff is not None
            else "DONJON process completed; run the independent physics validator."
            if status == "completed"
            else f"DONJON relative-file staging did not complete safely: {staging_issue}"
            if not staging_complete
            else f"DONJON result could not be archived safely: {result_snapshot_issue}"
            if result_snapshot_issue is not None
            else "DONJON did not produce the expected finite result."
        )
        jobs.publish_terminal(
            job_id,
            status=status,
            finished_at=time.time(),
            message=message,
            result_path=str(archived_result_path) if result_within_bound else None,
            deck_path=str(archived_deck_path),
            k_effective=keff,
            return_code=completed.returncode,
            log_tail=combined[-12000:],
        )
    except subprocess.TimeoutExpired as exc:
        timeout_text = _timeout_log(exc)
        log_path.write_text(timeout_text, encoding="utf-8")
        jobs.publish_terminal(
            job_id,
            status="failed",
            finished_at=time.time(),
            message=f"DONJON timed out after {request['timeout_seconds']} s.",
            deck_path=str(archived_deck_path) if archived_deck_path.exists() else None,
            log_tail=timeout_text[-12000:],
        )
    except (OSError, RuntimeError, ValueError) as exc:
        error_text = str(exc)
        try:
            log_path.write_text(error_text, encoding="utf-8")
        except OSError:
            pass
        jobs.publish_terminal(
            job_id,
            status="failed",
            finished_at=time.time(),
            message=f"DONJON execution failed: {exc}",
            deck_path=str(archived_deck_path) if archived_deck_path.exists() else None,
            log_tail=error_text[-12000:],
        )
    finally:
        for path in (transient_deck_path, solver_result_path, *transient_paths):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        if isolated_tmp_root is not None:
            try:
                shutil.rmtree(isolated_tmp_root)
            except OSError:
                pass
        if launcher_owned:
            _RDONJON_PROCESS_LOCK.release()


def _require_execution_free_space(
    requirements: tuple[tuple[Path, int], ...],
) -> None:
    """Reserve worst-case execution bytes on each backing filesystem."""

    by_device: dict[int, tuple[Path, int]] = {}
    for path, required_bytes in requirements:
        resolved = path.resolve()
        device = resolved.stat().st_dev
        previous = by_device.get(device)
        if previous is None:
            by_device[device] = (resolved, required_bytes)
        else:
            by_device[device] = (previous[0], previous[1] + required_bytes)
    for probe, required_bytes in by_device.values():
        required_with_reserve = required_bytes + DONJON_RUNTIME_RESERVE_BYTES
        if shutil.disk_usage(probe).free < required_with_reserve:
            raise RuntimeError(
                "insufficient free space for the bounded DONJON execution "
                f"budget ({required_with_reserve} bytes required on {probe})"
            )


def _run_rdonjon_bounded(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int,
    shutdown_event: Event | None = None,
    runtime_root: Path | None = None,
    runtime_max_bytes: int | None = None,
    runtime_max_entries: int | None = None,
    result_path: Path | None = None,
    result_max_bytes: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the fixed launcher with bounded output and process-group cleanup."""

    with _ACTIVE_RDONJON_LOCK:
        _raise_if_execution_stopped(
            shutdown_event, "; solver launch was cancelled"
        )
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
        _ACTIVE_RDONJON_PROCESSES[process.pid] = (
            process,
            shutdown_event,
        )
    group_terminated = False

    def terminate_once(*, grace_seconds: float = DONJON_TERMINATION_GRACE_SECONDS) -> None:
        nonlocal group_terminated
        if group_terminated:
            return
        if grace_seconds == DONJON_TERMINATION_GRACE_SECONDS:
            _terminate_rdonjon_process_group(process)
        else:
            _terminate_rdonjon_process_group(
                process,
                grace_seconds=grace_seconds,
            )
        group_terminated = True

    if process.stdout is None or process.stderr is None:  # pragma: no cover - Popen contract
        terminate_once(grace_seconds=0.0)
        with _ACTIVE_RDONJON_LOCK:
            _ACTIVE_RDONJON_PROCESSES.pop(process.pid, None)
        raise RuntimeError("rdonjon output pipes were not created")

    overflow = Event()
    captures: dict[str, tuple[int, bytes, BaseException | None]] = {}
    capture_lock = Lock()
    readers = [
        Thread(
            target=_capture_bounded_pipe,
            kwargs={
                "name": name,
                "stream": stream,
                "captures": captures,
                "capture_lock": capture_lock,
                "overflow": overflow,
            },
            daemon=True,
            name=f"openmc2donjon-rdonjon-{name}",
        )
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
    ]
    try:
        for reader in readers:
            reader.start()
    except BaseException:
        terminate_once(grace_seconds=0.0)
        with _ACTIVE_RDONJON_LOCK:
            _ACTIVE_RDONJON_PROCESSES.pop(process.pid, None)
        raise

    timed_out = False
    quota_issue: str | None = None
    cancellation_issue: str | None = None
    try:
        deadline = time.monotonic() + timeout
        while True:
            try:
                _raise_if_execution_stopped(
                    shutdown_event, "; running DONJON solver was cancelled"
                )
            except RuntimeError as exc:
                cancellation_issue = str(exc)
                terminate_once()
                break
            quota_issue = _runtime_quota_issue(
                runtime_root=runtime_root,
                runtime_max_bytes=runtime_max_bytes,
                runtime_max_entries=runtime_max_entries,
                result_path=result_path,
                result_max_bytes=result_max_bytes,
            )
            if quota_issue is not None:
                terminate_once()
                break
            if overflow.is_set():
                terminate_once()
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                terminate_once()
                break
            try:
                process.wait(timeout=min(0.05, remaining))
                break
            except subprocess.TimeoutExpired:
                continue

        for reader in readers:
            reader.join(timeout=2.0)
        if any(reader.is_alive() for reader in readers):
            terminate_once(grace_seconds=0.0)
            for reader in readers:
                reader.join(timeout=1.0)
        if any(reader.is_alive() for reader in readers):
            raise RuntimeError("rdonjon output reader did not stop after process-group cleanup")

        stdout_count, stdout_bytes, stdout_error = captures.get(
            "stdout", (0, b"", RuntimeError("stdout capture did not finish"))
        )
        stderr_count, stderr_bytes, stderr_error = captures.get(
            "stderr", (0, b"", RuntimeError("stderr capture did not finish"))
        )
        if stdout_error is not None or stderr_error is not None:
            issue = stdout_error or stderr_error
            raise RuntimeError(f"could not capture bounded rdonjon output: {issue}")
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        if timed_out:
            raise subprocess.TimeoutExpired(
                argv,
                timeout,
                output=stdout,
                stderr=stderr,
            )
        if cancellation_issue is not None:
            raise RuntimeError(cancellation_issue)
        if quota_issue is not None:
            raise RuntimeError(quota_issue)
        if overflow.is_set():
            raise RuntimeError(
                "rdonjon stdout/stderr exceeded the bounded stream limit "
                f"({DONJON_MAX_STDIO_STREAM_BYTES} bytes per stream; "
                f"stdout={stdout_count}, stderr={stderr_count})"
            )
    except BaseException:
        terminate_once(grace_seconds=0.0)
        raise
    finally:
        with _ACTIVE_RDONJON_LOCK:
            _ACTIVE_RDONJON_PROCESSES.pop(process.pid, None)
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _runtime_quota_issue(
    *,
    runtime_root: Path | None,
    runtime_max_bytes: int | None,
    runtime_max_entries: int | None,
    result_path: Path | None,
    result_max_bytes: int | None,
) -> str | None:
    """Return a fail-closed issue while solver-owned files exceed admission."""

    if runtime_root is not None:
        if runtime_max_bytes is None or runtime_max_entries is None:
            return "DONJON runtime quota is incomplete"
        entries = 0
        total_bytes = 0
        pending = [runtime_root]
        while pending:
            directory = pending.pop()
            try:
                iterator = os.scandir(directory)
            except FileNotFoundError:
                continue
            except OSError as exc:
                return f"could not inspect DONJON runtime quota: {exc}"
            with iterator:
                for entry in iterator:
                    entries += 1
                    if entries > runtime_max_entries:
                        return (
                            "DONJON runtime exceeded the bounded entry quota "
                            f"({runtime_max_entries})"
                        )
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue
                    except OSError as exc:
                        return f"could not inspect DONJON runtime entry quota: {exc}"
                    if stat.S_ISLNK(info.st_mode):
                        return f"DONJON runtime produced a symlink: {entry.path}"
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(entry.path))
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        return f"DONJON runtime produced a special entry: {entry.path}"
                    total_bytes += info.st_size
                    if total_bytes > runtime_max_bytes:
                        return (
                            "DONJON runtime exceeded the bounded byte quota "
                            f"({runtime_max_bytes} bytes)"
                        )
    if result_path is not None:
        if result_max_bytes is None:
            return "DONJON result quota is incomplete"
        try:
            result_info = result_path.lstat()
        except FileNotFoundError:
            return None
        except OSError as exc:
            return f"could not inspect DONJON result quota: {exc}"
        if not stat.S_ISREG(result_info.st_mode):
            return "DONJON result path is not a regular file"
        if result_info.st_size > result_max_bytes:
            return (
                "DONJON result exceeded the bounded byte quota "
                f"({result_max_bytes} bytes)"
            )
    return None


def _capture_bounded_pipe(
    *,
    name: str,
    stream: Any,
    captures: dict[str, tuple[int, bytes, BaseException | None]],
    capture_lock: Lock,
    overflow: Event,
) -> None:
    """Drain one child pipe while retaining only a bounded byte tail."""

    total = 0
    tail = bytearray()
    error: BaseException | None = None
    try:
        while block := stream.read(64 * 1024):
            if isinstance(block, str):  # Defensive support for test doubles.
                block = block.encode("utf-8", errors="replace")
            total += len(block)
            if len(block) >= DONJON_STDIO_TAIL_BYTES:
                tail[:] = block[-DONJON_STDIO_TAIL_BYTES:]
            else:
                tail.extend(block)
                if len(tail) > DONJON_STDIO_TAIL_BYTES:
                    del tail[: len(tail) - DONJON_STDIO_TAIL_BYTES]
            if total > DONJON_MAX_STDIO_STREAM_BYTES:
                overflow.set()
    except BaseException as exc:  # pragma: no cover - OS pipe failures are rare
        error = exc
        overflow.set()
    finally:
        try:
            stream.close()
        except OSError:
            pass
        with capture_lock:
            captures[name] = (total, bytes(tail), error)


def _terminate_rdonjon_process_group(
    process: subprocess.Popen[Any],
    *,
    grace_seconds: float = DONJON_TERMINATION_GRACE_SECONDS,
) -> None:
    """TERM then KILL the original launcher process group and reap its leader.

    The launcher may exit on TERM while a descendant in the same group ignores
    it.  Therefore leader state is never used as proof that the group is empty:
    after the grace period POSIX always targets the original pgid with SIGKILL,
    unless a process-group probe reports ``ProcessLookupError`` first.
    """

    if os.name == "posix":
        process_group = process.pid
        try:
            os.killpg(process_group, signal.SIGTERM)
        except ProcessLookupError:
            _reap_rdonjon_leader(process)
            return
        except PermissionError:
            _terminate_rdonjon_leader_only(process, grace_seconds=grace_seconds)
            return
        deadline = time.monotonic() + max(0.0, grace_seconds)
        while True:
            # Reap an exited leader so that a leader-only group can disappear.
            # Its return code is deliberately not used as group-liveness proof.
            process.poll()
            try:
                os.killpg(process_group, 0)
            except ProcessLookupError:
                break
            except PermissionError:
                _terminate_rdonjon_leader_only(
                    process, grace_seconds=max(0.0, deadline - time.monotonic())
                )
                return
            if time.monotonic() >= deadline:
                try:
                    os.killpg(process_group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    _terminate_rdonjon_leader_only(process, grace_seconds=0.0)
                    return
                break
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
    else:  # pragma: no cover - Windows CI is not used for DONJON
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=max(0.0, grace_seconds))
            except subprocess.TimeoutExpired:
                process.kill()
    _reap_rdonjon_leader(process)


def _terminate_rdonjon_leader_only(
    process: subprocess.Popen[Any], *, grace_seconds: float
) -> None:
    """Best-effort fallback when the host denies process-group signalling."""

    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=max(0.0, grace_seconds))
        except subprocess.TimeoutExpired:
            process.kill()
    _reap_rdonjon_leader(process)


def _reap_rdonjon_leader(process: subprocess.Popen[Any]) -> None:
    """Best-effort reap of the launcher leader after group termination."""

    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        if os.name != "posix":  # pragma: no cover - defensive Windows fallback
            process.kill()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass


def _terminate_active_rdonjon_processes(
    *, shutdown_event: Event | None = None
) -> None:
    """Terminate every solver process group still owned by this web process."""

    if shutdown_event is None:
        _RDONJON_SHUTDOWN.set()
    with _ACTIVE_RDONJON_LOCK:
        processes = [
            process
            for process, owner_event in _ACTIVE_RDONJON_PROCESSES.values()
            if shutdown_event is None or owner_event is shutdown_event
        ]
    for process in processes:
        _terminate_rdonjon_process_group(process)


def _validate_rdonjon_hook_evidence(
    *,
    job_id: str,
    expected_deck_sha256: str,
    access_receipt_path: Path,
    staged_manifest_path: Path,
    runtime_output_manifest_path: Path,
    runtime_output_directory: Path,
) -> None:
    try:
        access = json.loads(access_receipt_path.read_text(encoding="utf-8"))
        staged = json.loads(staged_manifest_path.read_text(encoding="utf-8"))
        outputs = json.loads(runtime_output_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"rdonjon access/save evidence is missing or invalid: {exc}") from exc
    if (
        not isinstance(access, dict)
        or not isinstance(staged, dict)
        or not isinstance(outputs, dict)
    ):
        raise ValueError("rdonjon access/save evidence must be JSON objects")
    if (
        access.get("schema") != "openmc2donjon.web-donjon-access.v1"
        or access.get("job_id") != job_id
    ):
        raise ValueError("rdonjon access receipt does not belong to this job")
    if access.get("staged_manifest_sha256") != _file_sha256(staged_manifest_path):
        raise ValueError("rdonjon access receipt does not match the staged input manifest")
    if access.get("executed_deck_sha256") != expected_deck_sha256:
        raise ValueError("rdonjon executed deck does not match the admitted deck bytes")
    staged_artifacts = staged.get("artifacts")
    executed_inputs = access.get("executed_inputs")
    if not isinstance(staged_artifacts, list) or not isinstance(executed_inputs, list):
        raise ValueError("rdonjon access receipt has no executed-input manifest")
    expected_inputs = sorted(
        staged_artifacts,
        key=lambda item: str(item.get("relative_path")) if isinstance(item, dict) else "",
    )
    if executed_inputs != expected_inputs:
        raise ValueError("rdonjon executed inputs do not match the staged input manifest")
    canonical_executed = json.dumps(
        executed_inputs,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if access.get("executed_inputs_sha256") != hashlib.sha256(
        canonical_executed
    ).hexdigest():
        raise ValueError("rdonjon executed-input manifest digest is invalid")
    if (
        access.get("staged_file_count") != staged.get("file_count")
        or access.get("staged_total_bytes") != staged.get("total_bytes")
    ):
        raise ValueError("rdonjon access receipt counts do not match staging")
    if outputs.get("schema") != DONJON_RUNTIME_OUTPUT_SCHEMA or outputs.get("job_id") != job_id:
        raise ValueError("rdonjon runtime-output manifest does not belong to this job")
    declared = outputs.get("artifacts")
    if not isinstance(declared, list):
        raise ValueError("rdonjon runtime-output manifest has no artifact list")
    actual_paths: set[str] = set()
    actual_bytes = 0
    entry_count = 0
    if runtime_output_directory.is_dir():
        for path in runtime_output_directory.rglob("*"):
            entry_count += 1
            if entry_count > DONJON_MAX_RUNTIME_OUTPUT_ENTRIES:
                raise ValueError("rdonjon runtime-output archive exceeds its entry limit")
            relative = path.relative_to(runtime_output_directory)
            if len(relative.parts) > DONJON_MAX_STAGED_DEPTH:
                raise ValueError("rdonjon runtime-output archive exceeds its path-depth limit")
            if (
                len(relative.as_posix().encode("utf-8"))
                > DONJON_MAX_STAGED_RELATIVE_PATH_BYTES
            ):
                raise ValueError(
                    "rdonjon runtime-output archive exceeds its relative-path limit"
                )
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"runtime-output archive contains a symlink: {path}")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise ValueError(
                    f"runtime-output archive contains a special entry: {path}"
                )
            actual_paths.add(relative.as_posix())
            actual_bytes += info.st_size
            if len(actual_paths) > DONJON_MAX_RUNTIME_OUTPUT_FILES:
                raise ValueError("rdonjon runtime-output archive exceeds its file limit")
            if actual_bytes > DONJON_MAX_RUNTIME_OUTPUT_BYTES:
                raise ValueError("rdonjon runtime-output archive exceeds its byte limit")
    declared_paths: set[str] = set()
    for item in declared:
        if not isinstance(item, dict):
            raise ValueError("rdonjon runtime-output artifact entry is invalid")
        relative_text = item.get("relative_path")
        if not isinstance(relative_text, str) or not relative_text:
            raise ValueError("rdonjon runtime-output artifact path is invalid")
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"rdonjon runtime-output artifact escapes its archive: {relative_text}")
        target = (runtime_output_directory / relative).resolve()
        if not _is_relative_to(target, runtime_output_directory.resolve()) or not target.is_file():
            raise ValueError(f"rdonjon runtime-output artifact is missing: {relative_text}")
        if item.get("bytes") != target.stat().st_size or item.get("sha256") != _file_sha256(target):
            raise ValueError(f"rdonjon runtime-output artifact hash mismatch: {relative_text}")
        if relative_text in declared_paths:
            raise ValueError(f"duplicate rdonjon runtime-output artifact: {relative_text}")
        declared_paths.add(relative_text)
    if declared_paths != actual_paths:
        raise ValueError("rdonjon runtime-output manifest is incomplete")
    if outputs.get("file_count") != len(actual_paths):
        raise ValueError("rdonjon runtime-output manifest file count is incorrect")
    if outputs.get("total_bytes") != actual_bytes:
        raise ValueError("rdonjon runtime-output manifest byte count is incorrect")


def _declared_input_relative_path(raw: str) -> Path:
    """Return one canonical, bounded path in the staged runtime namespace."""

    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ValueError("input_files relative_path must be a non-empty trimmed path")
    if any(ord(character) < 32 for character in raw) or "\\" in raw:
        raise ValueError("input_files relative_path contains unsupported characters")
    relative = Path(raw)
    normalized = relative.as_posix()
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or normalized != raw
    ):
        raise ValueError(
            "input_files relative_path must be a canonical path inside the staged runtime"
        )
    if relative.parts[0] in {"code", "mydata", "assertS.c2m", "assertV.c2m"}:
        raise ValueError(
            f"input_files relative_path uses an rdonjon-reserved name: {normalized}"
        )
    _validate_staging_relative_path(relative)
    return relative


def _bind_declared_input_files(
    input_files: list[dict[str, str]],
    *,
    filesystem_scope: FilesystemScope,
    http_exception: Any,
) -> list[dict[str, Any]]:
    """Bind exact standalone FILE inputs before a DONJON job is admitted."""

    bound: list[dict[str, Any]] = []
    total_bytes = 0
    for item in input_files:
        raw_source = item["source_path"]
        candidate = filesystem_scope.candidate(raw_source)
        try:
            candidate_info = candidate.lstat()
        except OSError as exc:
            raise http_exception(
                status_code=404,
                detail=f"input_files source was not found: {candidate}",
            ) from exc
        if stat.S_ISLNK(candidate_info.st_mode):
            raise http_exception(
                status_code=422,
                detail=f"input_files source must not be a symlink: {candidate}",
            )
        source = filesystem_scope.resolve(candidate, http_exception)
        try:
            declaration = _snapshot_declared_input_identity(
                source,
                relative_path=item["relative_path"],
                max_bytes=DONJON_MAX_STAGED_BYTES - total_bytes,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            raise http_exception(
                status_code=422,
                detail=f"could not bind input_files source {source}: {exc}",
            ) from exc
        total_bytes += int(declaration["bytes"])
        bound.append(declaration)
    return bound


def _snapshot_declared_input_identity(
    source: Path,
    *,
    relative_path: str,
    max_bytes: int,
) -> dict[str, Any]:
    """Hash one regular source through a stable no-follow descriptor."""

    descriptor = os.open(
        source,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("source is not a regular file")
        if opened.st_size > max_bytes:
            raise ValueError(
                "declared inputs exceed the bounded staging size "
                f"({DONJON_MAX_STAGED_BYTES} bytes)"
            )
        digest = hashlib.sha256()
        copied = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            if copied + len(block) > opened.st_size:
                raise RuntimeError("source grew while its bytes were being bound")
            digest.update(block)
            copied += len(block)
        after = os.fstat(descriptor)
        if (
            after.st_dev != opened.st_dev
            or after.st_ino != opened.st_ino
            or after.st_mode != opened.st_mode
            or after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or copied != opened.st_size
        ):
            raise RuntimeError("source changed while its bytes were being bound")
        return {
            "source_path": str(source),
            "relative_path": _declared_input_relative_path(relative_path).as_posix(),
            "bytes": copied,
            "sha256": digest.hexdigest(),
            "device": opened.st_dev,
            "inode": opened.st_ino,
            "mode": opened.st_mode,
            "mtime_ns": opened.st_mtime_ns,
        }
    finally:
        os.close(descriptor)


def _stage_declared_input_files(
    declarations: list[dict[str, Any]],
    destination: Path,
    *,
    existing: dict[str, Any],
    shutdown_event: Event | None = None,
) -> dict[str, Any]:
    """Add only explicitly declared standalone inputs to a staged snapshot."""

    directories = set(existing.get("directories", []))
    artifacts_by_path = {
        item["relative_path"]: dict(item)
        for item in existing.get("artifacts", [])
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    entry_count = int(existing.get("entry_count", 0))
    total_bytes = int(existing.get("total_bytes", 0))
    declared_bytes = sum(int(item["bytes"]) for item in declarations)
    if total_bytes + declared_bytes > DONJON_MAX_STAGED_BYTES:
        raise ValueError(
            "declared inputs exceed the bounded staging size "
            f"({DONJON_MAX_STAGED_BYTES} bytes)"
        )
    reserve_bytes = 64 * 1024**2
    if shutil.disk_usage(destination.parent).free < declared_bytes + reserve_bytes:
        raise ValueError("insufficient free space for declared-input staging")
    declared_receipts: list[dict[str, Any]] = []
    for declaration in declarations:
        _raise_if_rdonjon_shutting_down(
            "while staging declared input files", shutdown_event
        )
        relative = _declared_input_relative_path(str(declaration["relative_path"]))
        relative_text = relative.as_posix()
        if relative_text in artifacts_by_path or relative_text in directories:
            raise ValueError(f"declared input collides with a staged path: {relative_text}")
        parents = [parent for parent in relative.parents if parent != Path(".")]
        for parent in reversed(parents):
            parent_text = parent.as_posix()
            if parent_text in artifacts_by_path:
                raise ValueError(
                    f"declared input parent collides with a staged file: {parent_text}"
                )
            if parent_text not in directories:
                entry_count += 1
                _check_staging_entry_count(entry_count)
                directory = destination / parent
                directory.mkdir(mode=0o700)
                directory.chmod(0o700)
                directories.add(parent_text)
        entry_count += 1
        _check_staging_entry_count(entry_count)
        expected_bytes = int(declaration["bytes"])
        if total_bytes + expected_bytes > DONJON_MAX_STAGED_BYTES:
            raise ValueError(
                "declared inputs exceed the bounded staging size "
                f"({DONJON_MAX_STAGED_BYTES} bytes)"
            )
        source = Path(str(declaration["source_path"]))
        target = destination / relative
        descriptor = os.open(
            source,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        digest = hashlib.sha256()
        copied = 0
        try:
            opened = os.fstat(descriptor)
            expected_identity = (
                declaration["device"],
                declaration["inode"],
                declaration["mode"],
                declaration["bytes"],
                declaration["mtime_ns"],
            )
            observed_identity = (
                opened.st_dev,
                opened.st_ino,
                opened.st_mode,
                opened.st_size,
                opened.st_mtime_ns,
            )
            if not stat.S_ISREG(opened.st_mode) or observed_identity != expected_identity:
                raise RuntimeError(
                    f"declared input changed before it was staged: {source}"
                )
            with os.fdopen(
                descriptor, "rb", closefd=False
            ) as source_stream, target.open("xb") as target_stream:
                for block in iter(lambda: source_stream.read(1024 * 1024), b""):
                    _raise_if_rdonjon_shutting_down(
                        "while copying declared input bytes", shutdown_event
                    )
                    if (
                        copied + len(block) > expected_bytes
                        or total_bytes + copied + len(block) > DONJON_MAX_STAGED_BYTES
                    ):
                        raise RuntimeError(
                            f"declared input grew beyond its admitted size: {source}"
                        )
                    target_stream.write(block)
                    digest.update(block)
                    copied += len(block)
            after = os.fstat(descriptor)
            if (
                after.st_dev != opened.st_dev
                or after.st_ino != opened.st_ino
                or after.st_mode != opened.st_mode
                or after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or copied != expected_bytes
                or digest.hexdigest() != declaration["sha256"]
            ):
                raise RuntimeError(
                    f"declared input changed while it was staged: {source}"
                )
        finally:
            os.close(descriptor)
        target.chmod(0o600)
        artifact = {
            "relative_path": relative_text,
            "bytes": copied,
            "sha256": digest.hexdigest(),
        }
        artifacts_by_path[relative_text] = artifact
        total_bytes += copied
        declared_receipts.append(
            {
                "source_path": str(source),
                **artifact,
            }
        )
    return {
        "entry_count": entry_count,
        "directory_count": len(directories),
        "directories": sorted(directories),
        "file_count": len(artifacts_by_path),
        "total_bytes": total_bytes,
        "excluded_paths": list(existing.get("excluded_paths", [])),
        "declared_input_files": declared_receipts,
        "artifacts": [artifacts_by_path[path] for path in sorted(artifacts_by_path)],
    }


def _stage_working_directory(
    source: Path,
    destination: Path,
    *,
    exclude_roots: tuple[Path, ...] = (),
    shutdown_event: Event | None = None,
) -> dict[str, Any]:
    """Create a bounded, symlink-free snapshot for rdonjon's rundir.

    ``rdonjon`` executes the solver in a private ``/tmp/rundirN`` rather than
    beside the submitted deck.  Its documented ``<stem>.access`` hook is the
    only supported way to stage relative files there.  Snapshotting before the
    launcher starts both makes that behavior deterministic and lets the web
    boundary reject paths it cannot preserve safely.
    """

    _raise_if_rdonjon_shutting_down(
        "before working-directory inventory", shutdown_event
    )
    source = source.resolve()
    source_info = source.lstat()
    if not stat.S_ISDIR(source_info.st_mode):
        raise ValueError(f"working_directory is not a directory: {source}")
    excluded = tuple(path.resolve() for path in exclude_roots)
    if any(_is_relative_to(source, root) for root in excluded):
        raise ValueError("working_directory must not be inside artifact_directory")
    reserved = {"code", "mydata", "assertS.c2m", "assertV.c2m"}
    directories: list[Path] = []
    files: list[tuple[Path, Path, os.stat_result]] = []
    excluded_paths: list[str] = []
    entry_count = 0
    total_bytes = 0

    pending_directories: list[tuple[Path, Path]] = [(source, Path())]
    while pending_directories:
        _raise_if_rdonjon_shutting_down(
            "during working-directory inventory", shutdown_event
        )
        current, relative_current = pending_directories.pop()
        names: list[str] = []
        with os.scandir(current) as entries:
            for entry in entries:
                _raise_if_rdonjon_shutting_down(
                    "during working-directory inventory", shutdown_event
                )
                entry_count += 1
                _check_staging_entry_count(entry_count)
                names.append(entry.name)
        child_directories: list[tuple[Path, Path]] = []
        for name in sorted(names):
            path = current / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"working_directory contains a symlink: {path}")
            relative = relative_current / name
            _validate_staging_relative_path(relative)
            if relative.parts and relative.parts[0] in reserved:
                raise ValueError(f"working_directory uses an rdonjon-reserved name: {relative}")
            if stat.S_ISDIR(info.st_mode):
                resolved = path.resolve()
                if any(_is_relative_to(resolved, root) for root in excluded):
                    excluded_paths.append(str(resolved))
                    continue
                directories.append(relative)
                child_directories.append((path, relative))
            elif stat.S_ISREG(info.st_mode):
                total_bytes += info.st_size
                files.append((path, relative, info))
                if total_bytes > DONJON_MAX_STAGED_BYTES:
                    raise ValueError(
                        "working_directory exceeds the bounded staging size "
                        f"({DONJON_MAX_STAGED_BYTES} bytes)"
                    )
            else:
                raise ValueError(f"working_directory contains a special entry: {path}")
        pending_directories.extend(reversed(child_directories))

    reserve_bytes = 64 * 1024**2
    if shutil.disk_usage(destination.parent).free < total_bytes + reserve_bytes:
        raise ValueError(
            "insufficient free space for a bounded working-directory snapshot"
        )
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    destination.chmod(0o700)
    for relative in directories:
        _raise_if_rdonjon_shutting_down(
            "while creating the staged directory tree", shutdown_event
        )
        directory = destination / relative
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)
    artifacts: list[dict[str, Any]] = []
    copied_bytes = 0
    root_descriptor = os.open(
        source,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened_root = os.fstat(root_descriptor)
        if (
            not stat.S_ISDIR(opened_root.st_mode)
            or opened_root.st_dev != source_info.st_dev
            or opened_root.st_ino != source_info.st_ino
        ):
            raise RuntimeError("working_directory changed while it was inventoried")
        for source_path, relative, expected in files:
            _raise_if_rdonjon_shutting_down(
                "while copying staged working files", shutdown_event
            )
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.parent.chmod(0o700)
            descriptor = _open_snapshot_file(root_descriptor, relative)
            digest = hashlib.sha256()
            copied = 0
            try:
                opened = os.fstat(descriptor)
                identity = (
                    opened.st_dev,
                    opened.st_ino,
                    opened.st_mode,
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                )
                expected_identity = (
                    expected.st_dev,
                    expected.st_ino,
                    expected.st_mode,
                    expected.st_size,
                    expected.st_mtime_ns,
                    expected.st_ctime_ns,
                )
                if not stat.S_ISREG(opened.st_mode) or identity != expected_identity:
                    raise RuntimeError(
                        f"working file changed before it was staged: {source_path}"
                    )
                with os.fdopen(
                    descriptor, "rb", closefd=False
                ) as source_stream, target.open("xb") as target_stream:
                    for block in iter(lambda: source_stream.read(1024 * 1024), b""):
                        _raise_if_rdonjon_shutting_down(
                            "while copying staged working-file bytes",
                            shutdown_event,
                        )
                        if (
                            copied + len(block) > opened.st_size
                            or copied_bytes + copied + len(block) > total_bytes
                            or copied_bytes + copied + len(block)
                            > DONJON_MAX_STAGED_BYTES
                        ):
                            raise RuntimeError(
                                f"working file grew beyond its admitted staging size: "
                                f"{source_path}"
                            )
                        target_stream.write(block)
                        digest.update(block)
                        copied += len(block)
                after = os.fstat(descriptor)
                if (
                    after.st_dev != opened.st_dev
                    or after.st_ino != opened.st_ino
                    or after.st_mode != opened.st_mode
                    or after.st_size != opened.st_size
                    or after.st_mtime_ns != opened.st_mtime_ns
                    or after.st_ctime_ns != opened.st_ctime_ns
                    or copied != opened.st_size
                ):
                    raise RuntimeError(
                        f"working file changed while it was staged: {source_path}"
                    )
            finally:
                os.close(descriptor)
            target.chmod(0o600)
            copied_bytes += copied
            artifacts.append(
                {
                    "relative_path": relative.as_posix(),
                    "bytes": copied,
                    "sha256": digest.hexdigest(),
                }
            )
    finally:
        os.close(root_descriptor)
    return {
        "entry_count": entry_count,
        "directory_count": len(directories),
        "directories": [relative.as_posix() for relative in directories],
        "file_count": len(artifacts),
        "total_bytes": copied_bytes,
        "excluded_paths": sorted(set(excluded_paths)),
        "artifacts": artifacts,
    }


def _check_staging_entry_count(entry_count: int) -> None:
    if entry_count > DONJON_MAX_STAGED_ENTRIES:
        raise ValueError(
            "working_directory exceeds the bounded staging entry count "
            f"({DONJON_MAX_STAGED_ENTRIES} directories and files)"
        )


def _validate_staging_relative_path(relative: Path) -> None:
    if len(relative.parts) > DONJON_MAX_STAGED_DEPTH:
        raise ValueError(
            "working_directory exceeds the bounded staging depth "
            f"({DONJON_MAX_STAGED_DEPTH})"
        )
    encoded_length = len(relative.as_posix().encode("utf-8"))
    if encoded_length > DONJON_MAX_STAGED_RELATIVE_PATH_BYTES:
        raise ValueError(
            "working_directory contains a relative path longer than the staging bound "
            f"({DONJON_MAX_STAGED_RELATIVE_PATH_BYTES} UTF-8 bytes)"
        )


def _raise_if_rdonjon_shutting_down(
    stage: str, shutdown_event: Event | None
) -> None:
    _raise_if_execution_stopped(shutdown_event, stage)


def _open_snapshot_file(root_descriptor: int, relative: Path) -> int:
    """Open a snapshot file through no-follow directory descriptors."""

    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"invalid working snapshot path: {relative}")
    directory_descriptor = os.dup(root_descriptor)
    try:
        for part in relative.parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY
                | getattr(os, "O_DIRECTORY", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return os.open(
            relative.parts[-1],
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
    finally:
        os.close(directory_descriptor)


def _rdonjon_fixed_hook_source() -> str:
    """Return the fixed access/save helper; no request text enters this source."""

    return f"""#!{sys.executable}
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import time

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()

def canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def safe_relative(raw: str) -> Path:
    relative = Path(raw)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeError(f"invalid staged relative path: {{raw}}")
    if len(relative.parts) > {DONJON_MAX_STAGED_DEPTH}:
        raise RuntimeError(f"staged relative path is too deep: {{raw}}")
    if len(relative.as_posix().encode("utf-8")) > {DONJON_MAX_STAGED_RELATIVE_PATH_BYTES}:
        raise RuntimeError(f"staged relative path is too long: {{raw}}")
    return relative

def open_staged_file(root_descriptor: int, relative: Path) -> int:
    directory_descriptor = os.dup(root_descriptor)
    try:
        for part in relative.parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=directory_descriptor,
            )
            os.close(directory_descriptor)
            directory_descriptor = next_descriptor
        return os.open(
            relative.parts[-1],
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
            dir_fd=directory_descriptor,
        )
    finally:
        os.close(directory_descriptor)

def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
    os.replace(temporary, path)

job_id = os.environ["OPENMC2DONJON_WEB_JOB_ID"]
if len(sys.argv) != 2:
    raise RuntimeError("the fixed rdonjon hook requires its access/save wrapper path")
mode = Path(sys.argv[1]).suffix
if mode == ".access":
    source = Path(os.environ["OPENMC2DONJON_WEB_STAGED_DIRECTORY"]).resolve()
    destination = Path.cwd().resolve()
    executed_deck_sha256 = digest(destination / "mydata")
    if executed_deck_sha256 != os.environ["OPENMC2DONJON_WEB_EXPECTED_DECK_SHA256"]:
        raise RuntimeError("executed deck does not match the admitted deck bytes")
    staged_manifest = Path(os.environ["OPENMC2DONJON_WEB_STAGED_MANIFEST"])
    manifest = json.loads(staged_manifest.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts")
    directories = manifest.get("directories", [])
    if not isinstance(artifacts, list) or not isinstance(directories, list):
        raise RuntimeError("staged manifest has no bounded file/directory inventory")
    expected = {{}}
    for item in artifacts:
        if not isinstance(item, dict):
            raise RuntimeError("staged manifest contains an invalid artifact")
        relative = safe_relative(item.get("relative_path"))
        relative_text = relative.as_posix()
        if relative_text in expected:
            raise RuntimeError(f"staged manifest repeats an artifact: {{relative_text}}")
        if not isinstance(item.get("bytes"), int) or item["bytes"] < 0:
            raise RuntimeError(f"staged manifest has an invalid byte count: {{relative_text}}")
        if not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64:
            raise RuntimeError(f"staged manifest has an invalid digest: {{relative_text}}")
        expected[relative_text] = item
    expected_directories = {{safe_relative(item).as_posix() for item in directories}}
    actual_files = set()
    actual_directories = set()
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            raise RuntimeError(f"staged snapshot contains a symlink: {{relative}}")
        if stat.S_ISDIR(info.st_mode):
            actual_directories.add(relative.as_posix())
            continue
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeError(f"staged snapshot contains a special entry: {{relative}}")
        actual_files.add(relative.as_posix())
    if actual_files != set(expected) or actual_directories != expected_directories:
        raise RuntimeError("staged snapshot inventory no longer matches its manifest")
    top_level_names = {{
        relative.parts[0]
        for relative in [
            *(safe_relative(item) for item in directories),
            *(safe_relative(item) for item in expected),
        ]
    }}
    for name in top_level_names:
        target = destination / name
        if target.exists() or target.is_symlink():
            raise RuntimeError(f"staged input collides with rdonjon runtime entry: {{name}}")
    for raw in sorted(directories, key=lambda item: (len(safe_relative(item).parts), item)):
        target = destination / safe_relative(raw)
        target.mkdir(mode=0o700)
    root_descriptor = os.open(
        source,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    executed_inputs = []
    try:
        for relative_text in sorted(expected):
            item = expected[relative_text]
            relative = safe_relative(relative_text)
            source_descriptor = open_staged_file(root_descriptor, relative)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target_descriptor = None
            value = hashlib.sha256()
            copied = 0
            try:
                before = os.fstat(source_descriptor)
                if not stat.S_ISREG(before.st_mode) or before.st_size != item["bytes"]:
                    raise RuntimeError(f"staged input changed before execution copy: {{relative_text}}")
                target_descriptor = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                remaining = item["bytes"]
                while remaining:
                    block = os.read(source_descriptor, min(1024 * 1024, remaining))
                    if not block:
                        raise RuntimeError(f"staged input shrank during execution copy: {{relative_text}}")
                    write_offset = 0
                    while write_offset < len(block):
                        write_offset += os.write(target_descriptor, block[write_offset:])
                    value.update(block)
                    copied += len(block)
                    remaining -= len(block)
                if os.read(source_descriptor, 1):
                    raise RuntimeError(f"staged input grew during execution copy: {{relative_text}}")
                after = os.fstat(source_descriptor)
                if (
                    after.st_dev != before.st_dev
                    or after.st_ino != before.st_ino
                    or after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                    or copied != item["bytes"]
                    or value.hexdigest() != item["sha256"]
                ):
                    raise RuntimeError(f"staged input changed during execution copy: {{relative_text}}")
                os.fsync(target_descriptor)
            finally:
                if target_descriptor is not None:
                    os.close(target_descriptor)
                os.close(source_descriptor)
            if target.stat().st_size != item["bytes"] or digest(target) != item["sha256"]:
                raise RuntimeError(f"executed input copy does not match staging: {{relative_text}}")
            executed_inputs.append(
                {{
                    "relative_path": relative_text,
                    "bytes": item["bytes"],
                    "sha256": item["sha256"],
                }}
            )
    finally:
        os.close(root_descriptor)
    write_json(
        Path(os.environ["OPENMC2DONJON_WEB_ACCESS_RECEIPT"]),
        {{
            "schema": "openmc2donjon.web-donjon-access.v1",
            "job_id": job_id,
            "executed_deck_sha256": executed_deck_sha256,
            "staged_file_count": manifest["file_count"],
            "staged_total_bytes": manifest["total_bytes"],
            "staged_manifest_sha256": digest(staged_manifest),
            "executed_inputs": executed_inputs,
            "executed_inputs_sha256": canonical_digest(executed_inputs),
            "completed_at": time.time(),
        }},
    )
elif mode == ".save":
    current = Path.cwd().resolve()
    output = Path(os.environ["OPENMC2DONJON_WEB_RUNTIME_OUTPUT_DIRECTORY"]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    staged_manifest = Path(os.environ["OPENMC2DONJON_WEB_STAGED_MANIFEST"])
    staged_payload = json.loads(staged_manifest.read_text(encoding="utf-8"))
    staged = {{item["relative_path"]: item["sha256"] for item in staged_payload["artifacts"]}}
    max_files = int(os.environ["OPENMC2DONJON_WEB_MAX_OUTPUT_FILES"])
    max_entries = int(os.environ["OPENMC2DONJON_WEB_MAX_OUTPUT_ENTRIES"])
    max_bytes = int(os.environ["OPENMC2DONJON_WEB_MAX_OUTPUT_BYTES"])
    artifacts = []
    total_bytes = 0
    inventory = []
    for path in current.rglob("*"):
        relative = path.relative_to(current)
        if relative.parts and relative.parts[0] in {{"code", "mydata"}}:
            continue
        if relative == Path(f"openmc2donjon_web_{{job_id}}.result"):
            continue
        inventory.append((relative, path))
        if len(inventory) > max_entries:
            raise RuntimeError("rdonjon runtime outputs exceed the bounded entry limit")
    runtime_root_descriptor = os.open(
        current,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        for relative, path in sorted(inventory, key=lambda item: item[0].as_posix()):
            if len(relative.parts) > {DONJON_MAX_STAGED_DEPTH}:
                raise RuntimeError("rdonjon runtime output exceeds the bounded path depth")
            relative_text = relative.as_posix()
            if len(relative_text.encode("utf-8")) > {DONJON_MAX_STAGED_RELATIVE_PATH_BYTES}:
                raise RuntimeError("rdonjon runtime output exceeds the bounded relative-path length")
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError(f"rdonjon runtime produced a symlink: {{relative}}")
            if stat.S_ISDIR(info.st_mode):
                continue
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError(f"rdonjon runtime produced a special entry: {{relative}}")
            source_descriptor = open_staged_file(runtime_root_descriptor, relative)
            target = None
            try:
                before = os.fstat(source_descriptor)
                admitted_identity = (
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_size,
                    info.st_mtime_ns,
                )
                opened_identity = (
                    before.st_dev,
                    before.st_ino,
                    before.st_mode,
                    before.st_size,
                    before.st_mtime_ns,
                )
                if not stat.S_ISREG(before.st_mode) or opened_identity != admitted_identity:
                    raise RuntimeError(
                        f"rdonjon runtime output changed before archival: {{relative_text}}"
                    )
                source_value = hashlib.sha256()
                observed = 0
                while True:
                    block = os.read(source_descriptor, 1024 * 1024)
                    if not block:
                        break
                    if observed + len(block) > before.st_size:
                        raise RuntimeError(
                            f"rdonjon runtime output grew during archival admission: {{relative_text}}"
                        )
                    source_value.update(block)
                    observed += len(block)
                after_digest = os.fstat(source_descriptor)
                if (
                    after_digest.st_dev != before.st_dev
                    or after_digest.st_ino != before.st_ino
                    or after_digest.st_mode != before.st_mode
                    or after_digest.st_size != before.st_size
                    or after_digest.st_mtime_ns != before.st_mtime_ns
                    or observed != before.st_size
                ):
                    raise RuntimeError(
                        f"rdonjon runtime output changed during archival admission: {{relative_text}}"
                    )
                source_sha256 = source_value.hexdigest()
                staged_digest = staged.get(relative_text)
                if staged_digest == source_sha256:
                    continue
                if (
                    len(artifacts) + 1 > max_files
                    or total_bytes + before.st_size > max_bytes
                ):
                    raise RuntimeError("rdonjon runtime outputs exceed the bounded archive limits")
                os.lseek(source_descriptor, 0, os.SEEK_SET)
                target = output / relative
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target_descriptor = None
                copied = 0
                copied_value = hashlib.sha256()
                try:
                    target_descriptor = os.open(
                        target,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0),
                        0o600,
                    )
                    while True:
                        block = os.read(source_descriptor, 1024 * 1024)
                        if not block:
                            break
                        if (
                            copied + len(block) > before.st_size
                            or total_bytes + copied + len(block) > max_bytes
                        ):
                            raise RuntimeError(
                                "rdonjon runtime output grew beyond its admitted "
                                f"archive size: {{relative_text}}"
                            )
                        offset = 0
                        while offset < len(block):
                            offset += os.write(target_descriptor, block[offset:])
                        copied_value.update(block)
                        copied += len(block)
                    after_copy = os.fstat(source_descriptor)
                    archived = os.fstat(target_descriptor)
                    if (
                        after_copy.st_dev != before.st_dev
                        or after_copy.st_ino != before.st_ino
                        or after_copy.st_mode != before.st_mode
                        or after_copy.st_size != before.st_size
                        or after_copy.st_mtime_ns != before.st_mtime_ns
                        or copied != before.st_size
                        or copied_value.hexdigest() != source_sha256
                        or archived.st_size != copied
                    ):
                        raise RuntimeError(
                            f"rdonjon runtime output changed during archival copy: {{relative_text}}"
                        )
                    os.fsync(target_descriptor)
                finally:
                    if target_descriptor is not None:
                        os.close(target_descriptor)
                target.chmod(0o600)
                total_bytes += copied
                artifacts.append(
                    {{
                        "relative_path": relative_text,
                        "bytes": copied,
                        "sha256": source_sha256,
                    }}
                )
            except BaseException:
                if target is not None:
                    target.unlink(missing_ok=True)
                raise
            finally:
                os.close(source_descriptor)
    finally:
        os.close(runtime_root_descriptor)
    write_json(
        Path(os.environ["OPENMC2DONJON_WEB_RUNTIME_OUTPUT_MANIFEST"]),
        {{
            "schema": "{DONJON_RUNTIME_OUTPUT_SCHEMA}",
            "job_id": job_id,
            "entry_count": len(inventory),
            "file_count": len(artifacts),
            "total_bytes": total_bytes,
            "artifacts": artifacts,
            "completed_at": time.time(),
        }},
    )
else:
    raise RuntimeError(f"unsupported rdonjon hook mode: {{mode}}")
"""


def _rdonjon_hook_wrapper_source() -> str:
    """Return the fixed shell bridge used to invoke the helper in isolated mode."""

    return """#!/bin/sh
exec "$OPENMC2DONJON_WEB_PYTHON" -I "$OPENMC2DONJON_WEB_HOOK_HELPER" "$0"
"""


def _isolated_rdonjon_launcher_source(source: str) -> str:
    """Bind the stock launcher to a server-created per-job temporary root."""

    marker = "\ninum=1\n"
    if source.count(marker) != 1:
        raise RuntimeError("unsupported rdonjon launcher: temporary-root marker not found")
    guard = """
if [ -z "${OPENMC2DONJON_WEB_TMPDIR:-}" ]; then
  echo "OPENMC2DONJON_WEB_TMPDIR is required" 1>&2
  exit 1
fi
case "${OPENMC2DONJON_WEB_MAX_FILE_BLOCKS:-}" in
  ''|*[!0-9]*)
    echo "OPENMC2DONJON_WEB_MAX_FILE_BLOCKS must be a positive integer" 1>&2
    exit 1
    ;;
esac
if [ "$OPENMC2DONJON_WEB_MAX_FILE_BLOCKS" -le 0 ]; then
  echo "OPENMC2DONJON_WEB_MAX_FILE_BLOCKS must be positive" 1>&2
  exit 1
fi
ulimit -f "$OPENMC2DONJON_WEB_MAX_FILE_BLOCKS" || exit 1
Tmpdir=$OPENMC2DONJON_WEB_TMPDIR
"""
    solver_copy = '  cp "$CodeDir"/bin/"$MACH"/$Code ./code'
    if source.count(solver_copy) != 1:
        raise RuntimeError("unsupported rdonjon launcher: solver-copy marker not found")
    isolated = source.replace(marker, f"\n{guard}inum=1\n", 1)
    isolated = isolated.replace(
        solver_copy,
        '  cp "$OPENMC2DONJON_WEB_SOLVER" ./code',
        1,
    )
    deck_copy = 'cp "$CodeDir"/data/$mydata ./mydata'
    if isolated.count(deck_copy) != 1:
        raise RuntimeError("unsupported rdonjon launcher: deck-copy marker not found")
    return isolated.replace(
        deck_copy,
        'cp "$OPENMC2DONJON_WEB_DECK" ./mydata',
        1,
    )


def _read_trusted_file_bytes(
    path: Path,
    *,
    expected_sha256: object,
    label: str,
    max_bytes: int | None = None,
) -> bytes:
    """Read and hash the exact no-follow inode that will be snapshotted."""

    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"the configured {label} is not a regular file")
        if max_bytes is not None and before.st_size > max_bytes:
            raise RuntimeError(
                f"the configured {label} exceeds the bounded size ({max_bytes} bytes)"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            payload = stream.read()
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        after.st_dev != before.st_dev
        or after.st_ino != before.st_ino
        or after.st_size != before.st_size
        or after.st_mtime_ns != before.st_mtime_ns
        or len(payload) != before.st_size
    ):
        raise RuntimeError(f"the configured {label} changed while it was snapshotted")
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        raise RuntimeError(f"the configured {label} changed after admission")
    return payload


def _donjon_execution_environment() -> dict[str, str]:
    """Build the small environment needed by the trusted launcher and solver."""

    environment = {"PATH": os.defpath}
    for name in (
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "DYLD_FALLBACK_LIBRARY_PATH",
        "LIBPATH",
    ):
        value = os.environ.get(name)
        if value:
            environment[name] = value
    return environment


def _file_clause_paths(deck_text: str, http_exception: Any) -> list[str]:
    """Parse every literal following each CLE ``FILE`` keyword through ``;``."""

    semantic_text = _cle_semantic_text(deck_text)
    paths: list[str] = []
    index = 0
    length = len(semantic_text)
    while index < length:
        quote = semantic_text[index]
        if quote in {"'", '"'}:
            index += 1
            while index < length and semantic_text[index] != quote:
                index += 1
            if index >= length:
                raise http_exception(
                    status_code=422,
                    detail="unterminated quoted literal in web-run deck",
                )
            index += 1
            continue
        match = _FILE_TOKEN.match(semantic_text, index)
        if match is None:
            index += 1
            continue
        index = match.end()
        clause_paths: list[str] = []
        while True:
            while index < length and semantic_text[index].isspace():
                index += 1
            if index >= length:
                raise http_exception(
                    status_code=422,
                    detail="FILE clause must end with ';' in a web-run deck",
                )
            if semantic_text[index] == ";":
                if not clause_paths:
                    raise http_exception(
                        status_code=422,
                        detail="FILE clause must contain at least one quoted literal path",
                    )
                index += 1
                paths.extend(clause_paths)
                break
            quote = semantic_text[index]
            if quote not in {"'", '"'}:
                raise http_exception(
                    status_code=422,
                    detail=(
                        "every FILE path in a web-run deck must be a quoted literal; "
                        "dynamic or trailing FILE arguments cannot be scoped safely"
                    ),
                )
            index += 1
            start = index
            while index < length and semantic_text[index] != quote:
                index += 1
            if index >= length:
                raise http_exception(
                    status_code=422,
                    detail="unterminated FILE path literal in web-run deck",
                )
            clause_paths.append(semantic_text[start:index])
            index += 1
    return paths


def _validate_deck_file_paths(
    deck_text: str,
    *,
    working_directory: Path | None,
    declared_input_paths: set[str] | None = None,
    filesystem_scope: FilesystemScope,
    http_exception: Any,
) -> None:
    semantic_text = _cle_semantic_text(deck_text)
    if "(*" in semantic_text or "*)" in semantic_text:
        raise http_exception(
            status_code=422,
            detail=(
                "legacy CLE block comments are not accepted by the web runner; "
                "use line comments so the deck boundary can be verified exactly"
            ),
        )
    if _contains_unquoted_deck_keyword(deck_text, "PROCEDURE"):
        raise http_exception(
            status_code=422,
            detail=(
                "the web runner accepts self-contained decks only; external "
                "PROCEDURE/*.c2m execution requires a separately sandboxed runner"
            ),
        )
    declared = declared_input_paths or set()
    referenced_declared: set[str] = set()
    for raw_value in _file_clause_paths(deck_text, http_exception):
        raw = raw_value.strip()
        if not raw or "\x00" in raw:
            raise http_exception(status_code=422, detail="deck FILE path is empty or invalid")
        expanded = Path(raw).expanduser()
        if expanded.is_absolute():
            raise http_exception(
                status_code=422,
                detail=(
                    "absolute FILE paths are not accepted by the web runner; "
                    "place the file under working_directory and use a relative path"
                ),
            )
        try:
            relative = _declared_input_relative_path(raw)
        except ValueError as exc:
            if working_directory is not None and ".." in Path(raw).parts:
                raise http_exception(
                    status_code=422,
                    detail=f"relative FILE path escapes working_directory: {raw}",
                ) from exc
            raise http_exception(status_code=422, detail=str(exc)) from exc
        normalized = relative.as_posix()
        if normalized in declared:
            referenced_declared.add(normalized)
            continue
        if working_directory is None:
            raise http_exception(
                status_code=422,
                detail=(
                    "relative FILE paths require an explicit working_directory or "
                    "an exact input_files declaration"
                ),
            )
        candidate = (working_directory / relative).resolve()
        if not _is_relative_to(candidate, working_directory):
            raise http_exception(
                status_code=422,
                detail=f"relative FILE path escapes working_directory: {raw}",
            )
        filesystem_scope.enforce(candidate, http_exception)
    unused = declared - referenced_declared
    if unused:
        raise http_exception(
            status_code=422,
            detail=(
                "input_files contains paths not referenced by a FILE clause: "
                + ", ".join(sorted(unused))
            ),
        )


def _contains_unquoted_deck_keyword(deck_text: str, keyword: str) -> bool:
    semantic_text = _cle_semantic_text(deck_text)
    token = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
    index = 0
    while index < len(semantic_text):
        quote = semantic_text[index]
        if quote in {"'", '"'}:
            index += 1
            while index < len(semantic_text) and semantic_text[index] != quote:
                index += 1
            index += 1
            continue
        if token.match(semantic_text, index):
            return True
        index += 1
    return False


def _cle_semantic_text(deck_text: str) -> str:
    """Apply CLE's line-comment rules before scanning security-sensitive tokens."""

    semantic_lines: list[str] = []
    for raw_line in deck_text.splitlines():
        line = raw_line.split("!", 1)[0]
        if line.lstrip().startswith("*"):
            continue
        semantic_lines.append(line)
    return "\n".join(semantic_lines)


def _project_native_sph_binding(
    *,
    project_root: Path,
    component_id: str,
    source_deck_path: Path,
    working_directory: Path | None,
    http_exception: Any,
) -> dict[str, Any]:
    """Bind a web run to the live, validated Project component declaration."""

    # Local import avoids the project module's intentional use of the public
    # ``parse_donjon_k_effective`` helper during module initialization.
    from .project import PROJECT_MANIFEST_NAME, _validate_manifest

    manifest_path = project_root / PROJECT_MANIFEST_NAME
    try:
        manifest_bytes = _read_trusted_file_bytes(
            manifest_path,
            expected_sha256=None,
            label="project manifest",
            max_bytes=2 * 1024**2,
        )
        manifest = json.loads(manifest_bytes.decode("utf-8", errors="strict"))
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise http_exception(
            status_code=422,
            detail=f"project-declared native SPH binding is invalid: {exc}",
        ) from exc
    if not isinstance(manifest, dict):
        issues = ["project manifest must be a JSON object"]
    else:
        issues = _validate_manifest(manifest, project_root)
    if issues:
        detail = "; ".join(issues) if issues else "manifest is unavailable"
        raise http_exception(
            status_code=422,
            detail=f"project-declared native SPH binding is invalid: {detail}",
        )
    components = manifest.get("components")
    component = next(
        (
            item
            for item in components
            if isinstance(item, dict) and item.get("id") == component_id
        ),
        None,
    ) if isinstance(components, list) else None
    if component is None:
        raise http_exception(
            status_code=422,
            detail=f"project manifest has no component {component_id}",
        )
    contract = component.get("contract", "converter-hdf5")
    if isinstance(contract, dict):
        contract = contract.get("kind")
    declaration = component.get("native_sph")
    if contract != "native-sph" or not isinstance(declaration, dict):
        raise http_exception(
            status_code=422,
            detail=f"project component {component_id} has no native-sph declaration",
        )
    raw_deck = declaration.get("deck")
    raw_working = declaration.get("working_directory")
    if not isinstance(raw_deck, str) or not isinstance(raw_working, str):
        raise http_exception(
            status_code=422,
            detail=f"project component {component_id} native-sph declaration is incomplete",
        )
    declared_deck = (project_root / raw_deck).resolve()
    declared_working = (project_root / raw_working).resolve()
    if declared_deck != source_deck_path or declared_working != working_directory:
        raise http_exception(
            status_code=409,
            detail=(
                f"submitted deck/working directory does not match project component "
                f"{component_id} native-sph declaration"
            ),
        )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    declaration_payload = {
        "component": component,
        "component_id": component_id,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
    }
    return {
        "declaration_sha256": hashlib.sha256(
            json.dumps(
                declaration_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "project_manifest_path": str(manifest_path),
        "project_manifest_sha256": manifest_sha256,
        "project_component_declaration": component,
        "_project_manifest_bytes": manifest_bytes,
    }


def _project_component_diagnostic_binding(
    *,
    project_root: Path,
    component_id: str,
    input_files: list[dict[str, Any]],
    http_exception: Any,
) -> dict[str, Any]:
    """Bind one generated diagnostic to an accepted manifest-owned output.

    The generated deck remains a single-object diagnostic; this receipt does
    not claim it is the project's declared aggregate/full-core consumer.
    """

    from .project import PROJECT_MANIFEST_NAME, _validate_manifest, project_status

    manifest_path = project_root / PROJECT_MANIFEST_NAME
    try:
        manifest_bytes = _read_trusted_file_bytes(
            manifest_path,
            expected_sha256=None,
            label="project manifest",
            max_bytes=2 * 1024**2,
        )
        manifest = json.loads(manifest_bytes.decode("utf-8", errors="strict"))
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise http_exception(
            status_code=422,
            detail=f"project component diagnostic binding is invalid: {exc}",
        ) from exc
    issues = (
        _validate_manifest(manifest, project_root)
        if isinstance(manifest, dict)
        else ["project manifest must be a JSON object"]
    )
    if issues:
        raise http_exception(
            status_code=422,
            detail="project component diagnostic binding is invalid: " + "; ".join(issues),
        )
    assert isinstance(manifest, dict)
    components = manifest.get("components")
    component = next(
        (
            item
            for item in components
            if isinstance(item, dict) and item.get("id") == component_id
        ),
        None,
    ) if isinstance(components, list) else None
    if component is None:
        raise http_exception(
            status_code=422,
            detail=f"project manifest has no component {component_id}",
        )
    live_status = project_status(project_root)
    row = next(
        (item for item in live_status["components"] if item["id"] == component_id),
        None,
    )
    if row is None or row["output"]["state"] != "accepted":
        detail = "; ".join(row["output"]["issues"]) if row is not None else "missing row"
        raise http_exception(
            status_code=409,
            detail=(
                f"project component {component_id} has no accepted Converter output: "
                f"{detail}"
            ),
        )
    if len(input_files) != 1:
        raise http_exception(
            status_code=422,
            detail=(
                "a project-bound single-object diagnostic must stage exactly the "
                "selected component output"
            ),
        )
    declared_output = Path(row["paths"]["output"]).resolve()
    submitted_output = Path(str(input_files[0]["source_path"])).resolve()
    if submitted_output != declared_output:
        raise http_exception(
            status_code=409,
            detail=(
                f"diagnostic input does not match project component {component_id} "
                "output"
            ),
        )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    declaration_payload = {
        "component": component,
        "component_id": component_id,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
    }
    return {
        "declaration_sha256": hashlib.sha256(
            json.dumps(
                declaration_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "project_manifest_path": str(manifest_path),
        "project_manifest_sha256": manifest_sha256,
        "project_component_declaration": component,
        "_project_manifest_bytes": manifest_bytes,
    }


def _request_receipt(
    *,
    job_id: str,
    request: dict[str, Any],
    working_directory: Path | None,
    archive_root: Path | None,
    donjon_root: Path | None,
    owner_path: Path | None,
    owner_token: str | None,
    owner_pid: int | None,
) -> dict[str, Any]:
    unique_deck = f"openmc2donjon_web_{job_id}.x2m"
    isolated_launcher = (
        archive_root / job_id / "rdonjon-isolated"
        if archive_root is not None
        else None
    )
    return {
        "schema": DONJON_REQUEST_SCHEMA,
        "job_id": job_id,
        "run_id": job_id,
        "owner_path": str(owner_path) if owner_path is not None else None,
        "owner_token": owner_token,
        "owner_pid": owner_pid,
        "created_at": time.time(),
        "deck_filename": request["deck_filename"],
        "deck_sha256": hashlib.sha256(request["deck_text"].encode("utf-8")).hexdigest(),
        "source_deck_path": request.get("source_deck_path") or None,
        "source_deck_sha256": request.get("source_deck_sha256") or None,
        "project_root": request.get("project_root") or None,
        "component_id": request.get("component_id") or None,
        "declaration_sha256": request.get("declaration_sha256") or None,
        "project_manifest_path": request.get("project_manifest_path") or None,
        "project_manifest_sha256": request.get("project_manifest_sha256") or None,
        "project_manifest_snapshot_path": (
            str(archive_root / job_id / "project-manifest.snapshot.json")
            if archive_root is not None and request.get("_project_manifest_bytes") is not None
            else None
        ),
        "project_component_declaration": request.get("project_component_declaration"),
        "request_binding_sha256": request.get("request_binding_sha256") or None,
        "input_files": request.get("input_files", []),
        "working_directory": (
            str(working_directory) if working_directory is not None else None
        ),
        "artifact_directory": str(archive_root) if archive_root is not None else None,
        "donjon_root": str(donjon_root) if donjon_root is not None else None,
        "timeout_seconds": request["timeout_seconds"],
        "expect_k_effective": request["expect_k_effective"],
        "launcher_contract": {
            "source_path": (
                str(donjon_root / "Donjon" / "rdonjon")
                if donjon_root is not None
                else None
            ),
            "source_sha256": request.get("launcher_sha256"),
            "solver_sha256": request.get("solver_sha256"),
            "cwd": str(donjon_root / "Donjon") if donjon_root is not None else None,
            "argv": (
                [str(isolated_launcher), "-q", unique_deck]
                if isolated_launcher is not None
                else None
            ),
            "deck_location": "Donjon/data/<job-unique-name>.x2m",
            "relative_file_staging": "fixed-rdonjon-access-save-hooks",
            "python_hook_mode": "isolated (-I), fixed helper",
            "temporary_root": "server-created-per-job",
            "environment": "minimal-whitelist",
            "arbitrary_shell_exposed": False,
        },
    }


def _read_persisted_job(archive_root: Path, job_id: str) -> dict[str, Any] | None:
    root = archive_root.resolve()
    run_directory = (root / job_id).resolve()
    if run_directory.parent != root:
        return None
    status_path = run_directory / "status.json"
    try:
        if status_path.is_symlink() or not status_path.is_file():
            return None
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if (
        payload.get("schema") != DONJON_JOB_SCHEMA
        or payload.get("job_id") != job_id
        or payload.get("run_id") != job_id
        or payload.get("operation") != "donjon"
        or payload.get("status") not in {"queued", "running", "completed", "failed"}
    ):
        return None
    expected_paths = {
        "archive_root": root,
        "run_directory": run_directory,
        "request_path": run_directory / "request.json",
        "status_path": run_directory / "status.json",
        "artifacts_path": run_directory / "artifacts.json",
        "completion_path": run_directory / "completion.json",
        "log_path": run_directory / "run.log",
        "owner_path": run_directory / "owner.lock",
    }
    if any(payload.get(key) != str(path) for key, path in expected_paths.items()):
        return None
    request_path = run_directory / "request.json"
    try:
        if request_path.is_symlink() or not request_path.is_file():
            return None
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(request, dict)
        or request.get("schema") != DONJON_REQUEST_SCHEMA
        or request.get("job_id") != job_id
        or request.get("run_id") != job_id
    ):
        return None
    for status_key, request_key in (
        ("owner_path", "owner_path"),
        ("owner_token", "owner_token"),
        ("owner_pid", "owner_pid"),
        ("deck_sha256", "deck_sha256"),
        ("source_deck_path", "source_deck_path"),
        ("source_deck_sha256", "source_deck_sha256"),
        ("project_root", "project_root"),
        ("component_id", "component_id"),
        ("declaration_sha256", "declaration_sha256"),
        ("project_manifest_path", "project_manifest_path"),
        ("project_manifest_sha256", "project_manifest_sha256"),
        ("project_manifest_snapshot_path", "project_manifest_snapshot_path"),
        ("request_binding_sha256", "request_binding_sha256"),
        ("working_directory", "working_directory"),
    ):
        if payload.get(status_key) != request.get(request_key):
            return None
    if (
        not isinstance(payload.get("owner_token"), str)
        or not _OWNER_TOKEN.fullmatch(payload["owner_token"])
        or not isinstance(payload.get("owner_pid"), int)
        or payload["owner_pid"] <= 0
        or not _owner_receipt_matches(payload)
    ):
        return None
    expected_optional_paths = {
        "project_manifest_snapshot_path": (
            run_directory / "project-manifest.snapshot.json"
            if isinstance(payload.get("project_manifest_path"), str)
            else None
        ),
        "staged_manifest_path": (
            run_directory / "staged-inputs.json"
        ),
        "runtime_output_directory": (
            run_directory / "runtime-output"
        ),
    }
    for key, path in expected_optional_paths.items():
        expected = str(path) if path is not None else None
        if payload.get(key) != expected:
            return None
    if not _project_manifest_snapshot_matches(payload, request):
        return None
    for key in ("deck_path", "result_path"):
        raw_path = payload.get(key)
        if raw_path is None:
            continue
        if not isinstance(raw_path, str):
            return None
        candidate = Path(raw_path)
        if candidate.is_symlink() or not _is_relative_to(
            candidate.resolve(strict=False), run_directory
        ):
            return None
    raw_deck_path = payload.get("deck_path")
    if raw_deck_path is not None:
        try:
            if _file_sha256(Path(raw_deck_path)) != payload.get("deck_sha256"):
                return None
        except OSError:
            return None
    if not isinstance(payload.get("created_at"), (int, float)):
        return None
    if not isinstance(payload.get("message"), str) or not isinstance(
        payload.get("log_tail"), str
    ):
        return None
    if payload["status"] in {"completed", "failed"}:
        if (
            payload.get("artifacts_finalized") is not True
            or not _completion_receipt_matches(payload)
            or not _artifact_manifest_matches(payload)
        ):
            return None
        if (
            payload["status"] == "completed"
            and _terminal_completed_evidence_issue(payload) is not None
        ):
            return None
    return payload


def _project_manifest_snapshot_matches(
    job: dict[str, Any], request: dict[str, Any]
) -> bool:
    raw_manifest_path = job.get("project_manifest_path")
    raw_snapshot_path = job.get("project_manifest_snapshot_path")
    component_id = job.get("component_id")
    if raw_manifest_path is None:
        return (
            raw_snapshot_path is None
            and job.get("project_manifest_sha256") is None
            and request.get("project_component_declaration") is None
        )
    if (
        not isinstance(raw_manifest_path, str)
        or not isinstance(raw_snapshot_path, str)
        or not isinstance(component_id, str)
        or not isinstance(job.get("project_manifest_sha256"), str)
        or not isinstance(job.get("declaration_sha256"), str)
    ):
        return False
    try:
        snapshot = _read_trusted_file_bytes(
            Path(raw_snapshot_path),
            expected_sha256=job["project_manifest_sha256"],
            label="archived project manifest",
            max_bytes=2 * 1024**2,
        )
        manifest = json.loads(snapshot.decode("utf-8", errors="strict"))
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    components = manifest.get("components") if isinstance(manifest, dict) else None
    component = next(
        (
            item
            for item in components
            if isinstance(item, dict) and item.get("id") == component_id
        ),
        None,
    ) if isinstance(components, list) else None
    if component is None or request.get("project_component_declaration") != component:
        return False
    declaration_payload = {
        "component": component,
        "component_id": component_id,
        "manifest_path": raw_manifest_path,
        "manifest_sha256": job["project_manifest_sha256"],
    }
    actual_declaration_sha256 = hashlib.sha256(
        json.dumps(
            declaration_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return actual_declaration_sha256 == job["declaration_sha256"]


def _completion_projection(job: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in sorted(job.items())
        if key != "completion_sha256"
    }


def _downgrade_terminal_evidence(job: dict[str, Any], issue: str) -> None:
    job.update(
        status="failed",
        result_path=None,
        k_effective=None,
        message=(
            "DONJON terminal evidence is inconsistent; this run is not valid. "
            f"{issue}"
        ),
    )


def _terminal_completed_evidence_issue(job: dict[str, Any]) -> str | None:
    """Bind completed status to the final deck, hook outputs, and result bytes."""

    if job.get("status") != "completed":
        return None
    raw_run = job.get("run_directory")
    raw_deck = job.get("deck_path")
    raw_staged = job.get("staged_manifest_path")
    raw_runtime = job.get("runtime_output_directory")
    raw_result = job.get("result_path")
    deck_sha256 = job.get("deck_sha256")
    if not all(
        isinstance(value, str)
        for value in (
            raw_run,
            raw_deck,
            raw_staged,
            raw_runtime,
            raw_result,
            deck_sha256,
        )
    ):
        return "A completed run is missing required archived evidence paths."
    assert isinstance(raw_run, str)
    assert isinstance(raw_deck, str)
    assert isinstance(raw_staged, str)
    assert isinstance(raw_runtime, str)
    assert isinstance(raw_result, str)
    assert isinstance(deck_sha256, str)
    run_directory = Path(raw_run)
    deck_path = Path(raw_deck)
    staged_manifest_path = Path(raw_staged)
    runtime_output_directory = Path(raw_runtime)
    result_path = Path(raw_result)
    required_paths = (
        deck_path,
        staged_manifest_path,
        runtime_output_directory,
        result_path,
    )
    if any(
        path.is_symlink()
        or not _is_relative_to(path.resolve(strict=False), run_directory.resolve())
        for path in required_paths
    ):
        return "A completed run references evidence outside its archive."
    try:
        if _file_sha256(deck_path) != deck_sha256:
            return "The archived deck no longer matches the admitted deck bytes."
        _validate_declared_input_evidence(
            request_path=run_directory / "request.json",
            staged_manifest_path=staged_manifest_path,
        )
        _validate_rdonjon_hook_evidence(
            job_id=str(job.get("job_id")),
            expected_deck_sha256=deck_sha256,
            access_receipt_path=run_directory / "access-receipt.json",
            staged_manifest_path=staged_manifest_path,
            runtime_output_manifest_path=(
                run_directory / "runtime-output-manifest.json"
            ),
            runtime_output_directory=runtime_output_directory,
        )
        result_text = _read_text_tail(
            result_path,
            max_bytes=1_000_000,
            max_file_bytes=DONJON_MAX_RESULT_BYTES,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return str(exc)
    observed_keff = parse_donjon_k_effective(result_text)
    expected_keff = job.get("k_effective")
    if observed_keff != expected_keff:
        return (
            "The archived result no longer reproduces the published "
            f"k-effective ({observed_keff!r} != {expected_keff!r})."
        )
    return None


def _validate_declared_input_evidence(
    *,
    request_path: Path,
    staged_manifest_path: Path,
) -> None:
    """Bind exact standalone declarations to the staged and executed bytes."""

    request = json.loads(
        _read_trusted_file_bytes(
            request_path,
            expected_sha256=None,
            label="DONJON request receipt",
            max_bytes=2 * 1024 * 1024,
        ).decode("utf-8", errors="strict")
    )
    staged = json.loads(
        _read_trusted_file_bytes(
            staged_manifest_path,
            expected_sha256=None,
            label="DONJON staged-input manifest",
            max_bytes=DONJON_MAX_STAGING_MANIFEST_BYTES,
        ).decode("utf-8", errors="strict")
    )
    raw_declared = request.get("input_files", [])
    raw_staged_declared = staged.get("declared_input_files", [])
    artifacts = staged.get("artifacts")
    if (
        not isinstance(raw_declared, list)
        or not isinstance(raw_staged_declared, list)
        or not isinstance(artifacts, list)
    ):
        raise ValueError("declared input evidence has an invalid inventory")

    def projection(item: Any) -> tuple[str, str, int, str]:
        if not isinstance(item, dict):
            raise ValueError("declared input evidence contains a non-object entry")
        source_path = item.get("source_path")
        relative_path = item.get("relative_path")
        byte_count = item.get("bytes")
        sha256 = item.get("sha256")
        if (
            not isinstance(source_path, str)
            or not isinstance(relative_path, str)
            or not isinstance(byte_count, int)
            or byte_count < 0
            or not isinstance(sha256, str)
            or not _SHA256.fullmatch(sha256)
        ):
            raise ValueError("declared input evidence contains invalid fields")
        _declared_input_relative_path(relative_path)
        return source_path, relative_path, byte_count, sha256

    expected = sorted(projection(item) for item in raw_declared)
    observed = sorted(projection(item) for item in raw_staged_declared)
    if expected != observed:
        raise ValueError("staged declared inputs do not match the admitted request")
    artifact_index = {
        item.get("relative_path"): item
        for item in artifacts
        if isinstance(item, dict) and isinstance(item.get("relative_path"), str)
    }
    for _, relative_path, byte_count, sha256 in expected:
        artifact = artifact_index.get(relative_path)
        if not isinstance(artifact, dict) or (
            artifact.get("bytes") != byte_count
            or artifact.get("sha256") != sha256
        ):
            raise ValueError(
                "staged manifest does not bind an admitted declared input"
            )


def _owner_receipt_matches(job: dict[str, Any]) -> bool:
    raw_path = job.get("owner_path")
    if not isinstance(raw_path, str):
        return False
    path = Path(raw_path)
    try:
        payload = _read_trusted_file_bytes(
            path,
            expected_sha256=None,
            label="DONJON job owner receipt",
            max_bytes=64 * 1024,
        )
        receipt = json.loads(payload.decode("utf-8", errors="strict"))
    except (OSError, RuntimeError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(receipt, dict)
        and receipt.get("schema") == DONJON_OWNER_SCHEMA
        and receipt.get("job_id") == job.get("job_id")
        and receipt.get("owner_token") == job.get("owner_token")
        and receipt.get("owner_pid") == job.get("owner_pid")
    )


def _completion_receipt_matches(job: dict[str, Any]) -> bool:
    raw_path = job.get("completion_path")
    expected_sha256 = job.get("completion_sha256")
    if not isinstance(raw_path, str) or not isinstance(expected_sha256, str):
        return False
    path = Path(raw_path)
    try:
        if path.is_symlink() or not path.is_file() or _file_sha256(path) != expected_sha256:
            return False
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(receipt, dict)
        and receipt.get("schema") == DONJON_COMPLETION_SCHEMA
        and receipt.get("job_id") == job.get("job_id")
        and receipt.get("run_id") == job.get("job_id")
        and receipt.get("status") == _completion_projection(job)
    )


def _artifact_manifest_matches(job: dict[str, Any]) -> bool:
    raw_run = job.get("run_directory")
    raw_manifest = job.get("artifacts_path")
    if not isinstance(raw_run, str) or not isinstance(raw_manifest, str):
        return False
    run_directory = Path(raw_run)
    manifest_path = Path(raw_manifest)
    try:
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != DONJON_ARTIFACT_MANIFEST_SCHEMA
        or manifest.get("job_id") != job.get("job_id")
        or manifest.get("run_id") != job.get("job_id")
        or manifest.get("status") != job.get("status")
        or not isinstance(manifest.get("artifacts"), list)
    ):
        return False
    expected_paths = {
        path.relative_to(run_directory).as_posix(): path
        for path in _job_evidence_files(run_directory, manifest_path=manifest_path)
    }
    declared_paths: set[str] = set()
    for item in manifest["artifacts"]:
        if not isinstance(item, dict):
            return False
        relative_text = item.get("relative_path")
        if not isinstance(relative_text, str) or relative_text in declared_paths:
            return False
        target = expected_paths.get(relative_text)
        if target is None:
            return False
        try:
            if (
                target.is_symlink()
                or not target.is_file()
                or item.get("path") != str(target)
                or item.get("bytes") != target.stat().st_size
                or item.get("sha256") != _file_sha256(target)
            ):
                return False
        except OSError:
            return False
        declared_paths.add(relative_text)
    return declared_paths == set(expected_paths)


def _job_evidence_files(run_directory: Path, *, manifest_path: Path) -> list[Path]:
    evidence: list[Path] = []
    for path in sorted(run_directory.rglob("*")):
        if (
            path == manifest_path
            or path == run_directory / "status.json"
            or not path.is_file()
            or path.is_symlink()
        ):
            continue
        relative = path.relative_to(run_directory)
        if relative.parts and relative.parts[0] == "staged-working-directory":
            continue
        evidence.append(path)
    return evidence


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timeout_log(exc: subprocess.TimeoutExpired) -> str:
    parts: list[str] = []
    for raw in (exc.stdout, exc.stderr):
        if isinstance(raw, bytes):
            parts.append(raw.decode("utf-8", errors="replace"))
        elif isinstance(raw, str):
            parts.append(raw)
    parts.append(str(exc))
    return "\n".join(part for part in parts if part)


def _read_text_tail(
    path: Path,
    *,
    max_bytes: int,
    max_file_bytes: int | None = None,
) -> str:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("terminal evidence is not a regular file")
        size = before.st_size
        if max_file_bytes is not None and size > max_file_bytes:
            raise RuntimeError("terminal evidence exceeds its admitted size")
        if size > max_bytes:
            os.lseek(descriptor, size - max_bytes, os.SEEK_SET)
        expected = min(size, max_bytes)
        chunks: list[bytes] = []
        remaining = expected
        while remaining:
            block = os.read(descriptor, remaining)
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or len(payload) != expected
        ):
            raise RuntimeError("terminal evidence changed while it was read")
    finally:
        os.close(descriptor)
    text = payload.decode("utf-8", errors="replace")
    if size > max_bytes:
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        return f"[listing tail; first {size - max_bytes} bytes omitted]\n{text}"
    return text


def _archive_result_snapshot(
    source: Path,
    destination: Path,
    *,
    max_bytes: int,
    tail_bytes: int,
) -> str:
    """Archive and parse the exact same bounded result-listing inode."""

    source_descriptor = os.open(
        source,
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
    )
    target_descriptor: int | None = None
    try:
        before = os.fstat(source_descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("DONJON result listing is not a regular file")
        if before.st_size > max_bytes:
            raise ValueError(
                f"DONJON result listing exceeds {max_bytes} admitted bytes"
            )
        target_descriptor = os.open(
            destination,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        copied = 0
        tail = bytearray()
        while block := os.read(source_descriptor, 1024 * 1024):
            copied += len(block)
            if copied > before.st_size or copied > max_bytes:
                raise RuntimeError("DONJON result listing grew while it was archived")
            offset = 0
            while offset < len(block):
                offset += os.write(target_descriptor, block[offset:])
            if len(block) >= tail_bytes:
                tail[:] = block[-tail_bytes:]
            else:
                tail.extend(block)
                if len(tail) > tail_bytes:
                    del tail[: len(tail) - tail_bytes]
        os.fsync(target_descriptor)
        after = os.fstat(source_descriptor)
        if (
            after.st_dev != before.st_dev
            or after.st_ino != before.st_ino
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or copied != before.st_size
        ):
            raise RuntimeError("DONJON result listing changed while it was archived")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        if target_descriptor is not None:
            os.close(target_descriptor)
        os.close(source_descriptor)
    text = bytes(tail).decode("utf-8", errors="replace")
    if before.st_size > tail_bytes:
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline >= 0 else text
        return (
            f"[listing tail; first {before.st_size - tail_bytes} bytes omitted]\n"
            f"{text}"
        )
    return text


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def parse_donjon_k_effective(text: str) -> float | None:
    values = [float(match.group(1)) for match in _KEFF.finditer(text)]
    if not values:
        return None
    value = values[-1]
    return value if value == value and abs(value) != float("inf") else None


def _donjon_root(raw: str, http_exception: Any, scope: FilesystemScope) -> Path:
    """Resolve only the server-configured, locally trusted DONJON installation."""

    configured_raw = os.environ.get(
        "OPENMC2DONJON_ROOT", str(Path.home() / "dragon-5.1")
    )
    configured_candidate = scope.candidate(configured_raw)
    try:
        configured_info = configured_candidate.lstat()
    except OSError as exc:
        raise http_exception(
            status_code=404,
            detail=(
                "configured DONJON root not found; set OPENMC2DONJON_ROOT "
                "when starting the web service"
            ),
        ) from exc
    if stat.S_ISLNK(configured_info.st_mode):
        raise http_exception(
            status_code=422,
            detail="configured DONJON root must not be a symbolic link",
        )
    root = scope.resolve(configured_candidate, http_exception)
    if raw:
        requested = scope.resolve(raw, http_exception)
        if requested != root:
            raise http_exception(
                status_code=403,
                detail=(
                    "donjon_root is fixed by the web service; set "
                    "OPENMC2DONJON_ROOT and restart to use another installation"
                ),
            )

    machine = f"{platform.system()}_{platform.machine()}"
    for label, directory in (
        ("DONJON root", root),
        ("Donjon directory", root / "Donjon"),
        ("Donjon data directory", root / "Donjon" / "data"),
        ("Donjon bin directory", root / "Donjon" / "bin"),
        ("Donjon machine bin directory", root / "Donjon" / "bin" / machine),
        ("Donjon result directory", root / "Donjon" / machine),
    ):
        _trusted_installation_directory(
            directory,
            label=label,
            http_exception=http_exception,
            scope=scope,
        )
    for label, executable in (
        ("rdonjon launcher", root / "Donjon" / "rdonjon"),
        ("DONJON solver", root / "Donjon" / "bin" / machine / "Donjon"),
    ):
        _trusted_installation_executable(
            executable,
            label=label,
            http_exception=http_exception,
            scope=scope,
        )
    return root


def _trusted_installation_directory(
    path: Path,
    *,
    label: str,
    http_exception: Any,
    scope: FilesystemScope,
) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise http_exception(
            status_code=404, detail=f"{label} not found: {path}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise http_exception(
            status_code=422,
            detail=f"{label} must be a real directory, not a link: {path}",
        )
    scope.enforce(path.resolve(), http_exception)
    _validate_installation_ownership(path, info, label, http_exception)


def _trusted_installation_executable(
    path: Path,
    *,
    label: str,
    http_exception: Any,
    scope: FilesystemScope,
) -> None:
    try:
        info = path.lstat()
    except OSError as exc:
        raise http_exception(
            status_code=404, detail=f"{label} not found: {path}"
        ) from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise http_exception(
            status_code=422,
            detail=f"{label} must be a real regular file, not a link: {path}",
        )
    if not os.access(path, os.X_OK):
        raise http_exception(status_code=422, detail=f"{label} is not executable: {path}")
    scope.enforce(path.resolve(), http_exception)
    _validate_installation_ownership(path, info, label, http_exception)


def _validate_installation_ownership(
    path: Path,
    info: os.stat_result,
    label: str,
    http_exception: Any,
) -> None:
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise http_exception(
            status_code=403,
            detail=f"{label} is not owned by the web-service user: {path}",
        )
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise http_exception(
            status_code=403,
            detail=f"{label} must not be group- or world-writable: {path}",
        )


def _input_file(raw: str, http_exception: Any, scope: FilesystemScope, *, suffix: str) -> Path:
    path = scope.resolve(raw, http_exception)
    if not path.is_file():
        raise http_exception(status_code=404, detail=f"input file not found: {raw}")
    if not str(path).lower().endswith(suffix):
        raise http_exception(status_code=422, detail=f"input must end with {suffix}: {raw}")
    return path


def _output_file(raw: str, http_exception: Any, scope: FilesystemScope, *, overwrite: bool) -> Path:
    path = scope.enforce(scope.candidate(raw), http_exception).resolve()
    if path.exists() and not overwrite:
        raise http_exception(status_code=409, detail=f"output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _optional_json_output(
    raw: str | None,
    http_exception: Any,
    scope: FilesystemScope,
    *,
    overwrite: bool,
) -> Path | None:
    if not raw:
        return None
    if Path(raw).suffix.lower() != ".json":
        raise http_exception(
            status_code=422,
            detail=f"summary_json must end with .json: {raw}",
        )
    return _output_file(raw, http_exception, scope, overwrite=overwrite)


def _scoped_dataset_spec(raw: str, http_exception: Any, scope: FilesystemScope) -> str:
    if not raw:
        raise http_exception(status_code=422, detail="flux dataset spec is required")
    path_text, marker, dataset = raw.partition("::")
    path = _input_file(path_text, http_exception, scope, suffix=".h5")
    return f"{path}::{dataset}" if marker else str(path)


def _scoped_previous_sph(raw: str, http_exception: Any, scope: FilesystemScope) -> str:
    path_text, marker, dataset = raw.partition("::")
    suffix = Path(path_text).suffix.lower()
    if suffix not in {".csv", ".h5", ".hdf5"}:
        raise http_exception(
            status_code=422,
            detail=f"previous_sph must be CSV or HDF5: {raw}",
        )
    path = _input_file(path_text, http_exception, scope, suffix=suffix)
    return f"{path}::{dataset}" if marker else str(path)


def _validate_physical_sph_source(path: Path, http_exception: Any) -> None:
    import h5py

    with h5py.File(path, "r") as h5:
        kind = _decoded_attr(h5.attrs.get("sph_kind"))
        derivation = _decoded_attr(h5.attrs.get("sph_derivation"))
        target = _decoded_attr(h5.attrs.get("sph_target"))
        normalization = _decoded_attr(h5.attrs.get("sph_flux_normalization"))
        zero_flux_policy = _decoded_attr(h5.attrs.get("sph_zero_flux_policy"))
        identity_bin_count = _integer_attr(h5.attrs.get("sph_identity_bin_count"))
        floored_bin_count = _integer_attr(h5.attrs.get("sph_floored_bin_count"))
        frozen_bin_count = _integer_attr(h5.attrs.get("sph_frozen_group_bin_count"))
        clipped_count = _integer_attr(h5.attrs.get("sph_clipped_count"))
        residual = h5.attrs.get("sph_max_update_residual")
        is_real = bool(h5.attrs.get("sph_real", False))
    if not is_real or not kind.startswith("openmc-ce-mg"):
        raise http_exception(
            status_code=422,
            detail="apply-sph requires a real OpenMC CE/MG-derived sidecar",
        )
    if "global" in kind or "optical" in kind or "calibrat" in kind:
        raise http_exception(
            status_code=422,
            detail="empirical global or optical SPH sidecars are forbidden",
        )
    if derivation != "rate-preserving-ce-mg-fixed-point" or target != "rate":
        raise http_exception(
            status_code=422,
            detail="apply-sph requires rate-preserving CE/MG fixed-point provenance",
        )
    if normalization != "power":
        raise http_exception(
            status_code=422,
            detail="apply-sph requires H-FACTOR/kappa-fission power normalization",
        )
    numerical_exemptions = {
        "identity-substituted": identity_bin_count,
        "flux-floored": floored_bin_count,
        "frozen-group": frozen_bin_count,
        "clipped": clipped_count,
    }
    if zero_flux_policy != "reject" or any(count != 0 for count in numerical_exemptions.values()):
        details = ", ".join(f"{name}={count}" for name, count in numerical_exemptions.items())
        raise http_exception(
            status_code=422,
            detail=(
                "apply-sph forbids numerical exemptions: zero-flux policy must be reject "
                f"and all exemption counts must be zero ({details})"
            ),
        )
    try:
        numeric_residual = float(residual)
    except (TypeError, ValueError):
        numeric_residual = float("inf")
    if not numeric_residual <= SPH_MAX_UPDATE_RESIDUAL:
        raise http_exception(
            status_code=422,
            detail=(
                "SPH sidecar is not converged: max update residual "
                f"{numeric_residual:.6g} exceeds {SPH_MAX_UPDATE_RESIDUAL:.6g}"
            ),
        )


def _decoded_attr(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)


def _integer_attr(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _object(payload: Any, http_exception: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise http_exception(status_code=422, detail="request body must be an object")
    return payload


def _required_text(data: dict[str, Any], key: str, http_exception: Any) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise http_exception(status_code=422, detail=f"{key} must be a non-empty string")
    return value.strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _boolean(value: Any, key: str, http_exception: Any) -> bool:
    if not isinstance(value, bool):
        raise http_exception(status_code=422, detail=f"{key} must be a boolean")
    return value


def _choice(value: Any, allowed: set[str], key: str, http_exception: Any) -> str:
    text = str(value)
    if text not in allowed:
        raise http_exception(status_code=422, detail=f"{key} must be one of: {', '.join(sorted(allowed))}")
    return text


def _number(value: Any, key: str, http_exception: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise http_exception(status_code=422, detail=f"{key} must be a number") from exc
    if number != number or abs(number) == float("inf"):
        raise http_exception(status_code=422, detail=f"{key} must be finite")
    return number


def _positive_number(value: Any, key: str, http_exception: Any) -> float:
    number = _number(value, key, http_exception)
    if number <= 0.0:
        raise http_exception(status_code=422, detail=f"{key} must be positive")
    return number


def _optional_number(value: Any, key: str, http_exception: Any) -> float | None:
    if value is None or value == "":
        return None
    return _number(value, key, http_exception)


def _integer_list(value: Any, key: str, http_exception: Any) -> list[int]:
    if isinstance(value, str):
        values = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        values = value
    else:
        raise http_exception(status_code=422, detail=f"{key} must be a list or comma-separated string")
    try:
        return [int(item) for item in values]
    except (TypeError, ValueError) as exc:
        raise http_exception(status_code=422, detail=f"{key} must contain integers") from exc
