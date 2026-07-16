from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
from threading import Lock, Thread
import time
import unittest
from unittest.mock import Mock, call, patch

import h5py

try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover
    TestClient = None  # type: ignore[assignment]

from openmc2donjon.web.execution import (
    DONJON_MAX_STAGED_ENTRIES,
    DONJON_MAX_STAGED_RELATIVE_PATH_BYTES,
    DONJON_MAX_STAGING_MANIFEST_BYTES,
    DONJON_MAX_TIMEOUT_SECONDS,
    _JobStore,
    _archive_result_snapshot,
    _bind_declared_input_files,
    _donjon_execution_environment,
    _isolated_rdonjon_launcher_source,
    _normalize_donjon,
    _project_component_diagnostic_binding,
    _rdonjon_fixed_hook_source,
    _rdonjon_hook_wrapper_source,
    _read_persisted_job,
    _run_donjon_job,
    _run_rdonjon_bounded,
    _runtime_quota_issue,
    _stage_working_directory,
    _stage_declared_input_files,
    _terminate_rdonjon_process_group,
    _validate_deck_file_paths,
    _validate_declared_input_evidence,
    _validate_rdonjon_hook_evidence,
    _validate_physical_sph_source,
    parse_donjon_k_effective,
)
from openmc2donjon.web.filesystem import FilesystemScope


_WEB_AVAILABLE = TestClient is not None


def _write_fake_donjon_installation(root: Path) -> tuple[Path, Path]:
    machine = f"{platform.system()}_{platform.machine()}"
    donjon = root / "Donjon"
    (donjon / "data").mkdir(parents=True)
    (donjon / machine).mkdir()
    solver = donjon / "bin" / machine / "Donjon"
    solver.parent.mkdir(parents=True)
    solver.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    solver.chmod(0o700)
    launcher = donjon / "rdonjon"
    launcher.write_text(
        (
            "#!/bin/sh\nTmpdir=/tmp\ninum=1\n"
            "if [ $typ = 'custom' ]; then\n"
            '  cp "$CodeDir"/bin/"$MACH"/$Code ./code\n'
            "fi\n"
            'cp "$CodeDir"/data/$mydata ./mydata\n'
            "exit 0\n"
        ),
        encoding="utf-8",
    )
    launcher.chmod(0o700)
    return launcher, solver


def _write_valid_terminal_evidence(
    job: dict[str, object],
    *,
    deck_text: str = "QUIT .\n",
    result_text: str = "k-effective = 1.000000\n",
) -> tuple[Path, Path, Path]:
    run = Path(str(job["run_directory"]))
    deck = run / "case.x2m"
    deck.write_text(deck_text, encoding="utf-8")
    staged = run / "staged-inputs.json"
    staged.write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.web-donjon-staging.v1",
                "job_id": job["job_id"],
                "file_count": 0,
                "total_bytes": 0,
                "artifacts": [],
            }
        ),
        encoding="utf-8",
    )
    executed_inputs: list[object] = []
    (run / "access-receipt.json").write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.web-donjon-access.v1",
                "job_id": job["job_id"],
                "executed_deck_sha256": hashlib.sha256(
                    deck_text.encode("utf-8")
                ).hexdigest(),
                "staged_file_count": 0,
                "staged_total_bytes": 0,
                "staged_manifest_sha256": hashlib.sha256(
                    staged.read_bytes()
                ).hexdigest(),
                "executed_inputs": executed_inputs,
                "executed_inputs_sha256": hashlib.sha256(b"[]").hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    runtime = run / "runtime-output"
    runtime.mkdir()
    output = runtime / "physics.dat"
    output.write_bytes(b"AAAA")
    (run / "runtime-output-manifest.json").write_text(
        json.dumps(
            {
                "schema": "openmc2donjon.web-donjon-runtime-output.v1",
                "job_id": job["job_id"],
                "file_count": 1,
                "total_bytes": 4,
                "artifacts": [
                    {
                        "relative_path": "physics.dat",
                        "bytes": 4,
                        "sha256": hashlib.sha256(b"AAAA").hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    result = run / "case.result"
    result.write_text(result_text, encoding="utf-8")
    return deck, output, result


class DonjonResultParserTests(unittest.TestCase):
    def test_uses_the_last_finite_k_effective(self) -> None:
        text = "k-effective = 7.67000E+05\nouter\nk-effective = 1.145655\n"
        self.assertAlmostEqual(parse_donjon_k_effective(text) or 0.0, 1.145655)

    def test_returns_none_without_a_result(self) -> None:
        self.assertIsNone(parse_donjon_k_effective("DONJON stopped"))

    def test_result_archive_and_keff_use_the_same_bounded_inode_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source = root / "solver.result"
            archived = root / "archived.result"
            source.write_text("k-effective = 1.012345\nnormal end\n", encoding="utf-8")

            text = _archive_result_snapshot(
                source,
                archived,
                max_bytes=1024,
                tail_bytes=1024,
            )

            self.assertAlmostEqual(parse_donjon_k_effective(text) or 0.0, 1.012345)
            self.assertEqual(archived.read_bytes(), source.read_bytes())

    def test_parses_the_explicit_openmc2donjon_echo_marker(self) -> None:
        text = (
            ">|OPENMC2DONJON MULTICOMPO DIFFUSION K-EFFECTIVE  "
            "2.730422e-02 |>0019\n"
        )
        self.assertAlmostEqual(
            parse_donjon_k_effective(text) or 0.0,
            2.730422e-02,
        )

    def test_long_physics_jobs_are_bounded_at_twenty_four_hours(self) -> None:
        from fastapi import HTTPException

        request = _normalize_donjon(
            {
                "deck_text": "QUIT .",
                "deck_filename": "case.x2m",
                "timeout_seconds": DONJON_MAX_TIMEOUT_SECONDS * 2,
            },
            HTTPException,
        )
        self.assertEqual(
            request["timeout_seconds"],
            DONJON_MAX_TIMEOUT_SECONDS,
        )

    def test_source_deck_binding_requires_a_sha256(self) -> None:
        from fastapi import HTTPException

        with self.assertRaisesRegex(HTTPException, "source_deck_sha256"):
            _normalize_donjon(
                {
                    "deck_text": "QUIT .\n",
                    "deck_filename": "case.x2m",
                    "source_deck_path": "/project/case.x2m",
                },
                HTTPException,
            )

    def test_launcher_environment_excludes_python_and_unrelated_secrets(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PYTHONPATH": "/attacker/src",
                "PYTHONHOME": "/attacker/python",
                "VIRTUAL_ENV": "/attacker/venv",
                "API_SECRET": "do-not-forward",
                "LANG": "C.UTF-8",
            },
            clear=True,
        ):
            environment = _donjon_execution_environment()

        self.assertEqual(environment["LANG"], "C.UTF-8")
        for forbidden in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "API_SECRET"):
            self.assertNotIn(forbidden, environment)
        self.assertIn(
            ' -I "$OPENMC2DONJON_WEB_HOOK_HELPER" ',
            _rdonjon_hook_wrapper_source(),
        )

    def test_isolated_launcher_requires_a_server_created_temporary_root(self) -> None:
        source = (
            "#!/bin/sh\nTmpdir=/tmp\ninum=1\n"
            "if [ $typ = 'custom' ]; then\n"
            '  cp "$CodeDir"/bin/"$MACH"/$Code ./code\n'
            "fi\n"
            'cp "$CodeDir"/data/$mydata ./mydata\n'
        )
        isolated = _isolated_rdonjon_launcher_source(source)
        self.assertIn("OPENMC2DONJON_WEB_TMPDIR is required", isolated)
        self.assertIn("Tmpdir=$OPENMC2DONJON_WEB_TMPDIR", isolated)
        self.assertIn('ulimit -f "$OPENMC2DONJON_WEB_MAX_FILE_BLOCKS"', isolated)
        self.assertIn('cp "$OPENMC2DONJON_WEB_SOLVER" ./code', isolated)

    def test_runtime_quota_detects_bytes_entries_and_result_growth(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            runtime = root / "runtime"
            runtime.mkdir()
            (runtime / "large.bin").write_bytes(b"x" * 11)
            issue = _runtime_quota_issue(
                runtime_root=runtime,
                runtime_max_bytes=10,
                runtime_max_entries=10,
                result_path=None,
                result_max_bytes=None,
            )
            self.assertIsNotNone(issue)
            self.assertIn("byte quota", str(issue))

            result = root / "case.result"
            result.write_bytes(b"y" * 6)
            issue = _runtime_quota_issue(
                runtime_root=None,
                runtime_max_bytes=None,
                runtime_max_entries=None,
                result_path=result,
                result_max_bytes=5,
            )
            self.assertIsNotNone(issue)
            self.assertIn("result exceeded", str(issue))

    @unittest.skipUnless(os.name == "posix", "native runner quotas are POSIX-specific")
    def test_running_solver_is_stopped_when_aggregate_runtime_quota_is_exceeded(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            runtime = Path(tmpdir).resolve()
            program = (
                "from pathlib import Path; import time; "
                "Path('oversized.bin').write_bytes(b'x' * 4096); time.sleep(10)"
            )
            with self.assertRaisesRegex(RuntimeError, "byte quota"):
                _run_rdonjon_bounded(
                    [sys.executable, "-c", program],
                    cwd=runtime,
                    env={"PATH": os.defpath},
                    timeout=10,
                    runtime_root=runtime,
                    runtime_max_bytes=1024,
                    runtime_max_entries=10,
                )

    def test_monitor_failure_still_terminates_the_solver_process_group(self) -> None:
        process = Mock()
        process.pid = 4568
        process.stdout = io.BytesIO(b"")
        process.stderr = io.BytesIO(b"")
        process.returncode = -signal.SIGKILL
        with (
            patch("openmc2donjon.web.execution.subprocess.Popen", return_value=process),
            patch(
                "openmc2donjon.web.execution._runtime_quota_issue",
                side_effect=OSError("quota monitor failed"),
            ),
            patch(
                "openmc2donjon.web.execution._terminate_rdonjon_process_group"
            ) as terminate,
            self.assertRaisesRegex(OSError, "quota monitor failed"),
        ):
            _run_rdonjon_bounded(
                ["/fixed/rdonjon", "-q", "case.x2m"],
                cwd=Path("/fixed"),
                env={},
                timeout=1,
            )
        terminate.assert_called_with(process, grace_seconds=0.0)

    def test_working_directory_is_explicit_request_data(self) -> None:
        from fastapi import HTTPException

        request = _normalize_donjon(
            {
                "deck_text": "QUIT .",
                "deck_filename": "case.x2m",
                "working_directory": "/project/native-sph",
            },
            HTTPException,
        )
        self.assertEqual(request["working_directory"], "/project/native-sph")

    def test_relative_file_paths_fail_closed_without_a_scoped_working_directory(self) -> None:
        from fastapi import HTTPException

        scope = FilesystemScope()
        with self.assertRaisesRegex(HTTPException, "explicit working_directory"):
            _validate_deck_file_paths(
                "SEQ_ASCII REF :: FILE 'reference.txt' ;",
                working_directory=None,
                filesystem_scope=scope,
                http_exception=HTTPException,
            )

    def test_exact_declared_input_allows_a_standalone_relative_file_clause(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source = root / "converter-output.mcompo.txt"
            source.write_bytes(b"exact converter object\n")
            normalized = _normalize_donjon(
                {
                    "deck_text": (
                        "SEQ_ASCII CPO :: FILE "
                        "'openmc2donjon_input.mcompo.txt' ;\nQUIT .\n"
                    ),
                    "deck_filename": "ingest.x2m",
                    "input_files": [
                        {
                            "source_path": str(source),
                            "relative_path": "openmc2donjon_input.mcompo.txt",
                        }
                    ],
                },
                HTTPException,
            )
            declarations = _bind_declared_input_files(
                normalized["input_files"],
                filesystem_scope=FilesystemScope(root=root),
                http_exception=HTTPException,
            )
            declared_paths = {item["relative_path"] for item in declarations}

            _validate_deck_file_paths(
                normalized["deck_text"],
                working_directory=None,
                declared_input_paths=declared_paths,
                filesystem_scope=FilesystemScope(root=root),
                http_exception=HTTPException,
            )
            staged_directory = root / "staged"
            staged_directory.mkdir()
            staged = _stage_declared_input_files(
                declarations,
                staged_directory,
                existing={
                    "entry_count": 0,
                    "directories": [],
                    "total_bytes": 0,
                    "excluded_paths": [],
                    "artifacts": [],
                },
            )

            self.assertEqual(
                (staged_directory / "openmc2donjon_input.mcompo.txt").read_bytes(),
                source.read_bytes(),
            )
            self.assertEqual(staged["file_count"], 1)
            self.assertEqual(staged["declared_input_files"][0]["source_path"], str(source))

    def test_declared_inputs_must_be_used_by_the_submitted_deck(self) -> None:
        from fastapi import HTTPException

        with self.assertRaisesRegex(HTTPException, "not referenced"):
            _validate_deck_file_paths(
                "QUIT .\n",
                working_directory=None,
                declared_input_paths={"unused.txt"},
                filesystem_scope=FilesystemScope(),
                http_exception=HTTPException,
            )

    def test_declared_input_change_after_admission_fails_closed(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source = root / "input.txt"
            source.write_bytes(b"admitted")
            declarations = _bind_declared_input_files(
                [{"source_path": str(source), "relative_path": "input.txt"}],
                filesystem_scope=FilesystemScope(root=root),
                http_exception=HTTPException,
            )
            source.write_bytes(b"changed!")
            staged_directory = root / "staged"
            staged_directory.mkdir()

            with self.assertRaisesRegex(RuntimeError, "changed before"):
                _stage_declared_input_files(
                    declarations,
                    staged_directory,
                    existing={
                        "entry_count": 0,
                        "directories": [],
                        "total_bytes": 0,
                        "excluded_paths": [],
                        "artifacts": [],
                    },
                )

    def test_terminal_evidence_binds_declared_inputs_to_the_staged_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            sha256 = hashlib.sha256(b"exact input").hexdigest()
            declaration = {
                "source_path": str(root / "source.txt"),
                "relative_path": "input.txt",
                "bytes": 11,
                "sha256": sha256,
            }
            request = root / "request.json"
            request.write_text(
                json.dumps({"input_files": [{**declaration, "inode": 1}]}),
                encoding="utf-8",
            )
            staged = root / "staged-inputs.json"
            staged_payload = {
                "declared_input_files": [declaration],
                "artifacts": [
                    {
                        "relative_path": declaration["relative_path"],
                        "bytes": declaration["bytes"],
                        "sha256": declaration["sha256"],
                    }
                ],
            }
            staged.write_text(json.dumps(staged_payload), encoding="utf-8")

            _validate_declared_input_evidence(
                request_path=request,
                staged_manifest_path=staged,
            )

            staged_payload["declared_input_files"][0]["sha256"] = "0" * 64
            staged.write_text(json.dumps(staged_payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "admitted request"):
                _validate_declared_input_evidence(
                    request_path=request,
                    staged_manifest_path=staged,
                )

    def test_relative_file_paths_cannot_escape_the_working_directory(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            working = root / "case"
            working.mkdir()
            with self.assertRaisesRegex(HTTPException, "escapes working_directory"):
                _validate_deck_file_paths(
                    "SEQ_ASCII REF :: FILE '../secret.txt' ;",
                    working_directory=working,
                    filesystem_scope=FilesystemScope(root=root),
                    http_exception=HTTPException,
                )

    def test_absolute_file_paths_are_rejected_even_inside_the_workspace(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            with self.assertRaisesRegex(HTTPException, "absolute FILE paths"):
                _validate_deck_file_paths(
                    f"SEQ_ASCII REF :: FILE '{root / 'reference.txt'}' ;",
                    working_directory=root,
                    filesystem_scope=FilesystemScope(root=root),
                    http_exception=HTTPException,
                )

    def test_every_path_in_a_multi_file_clause_is_scoped(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            working = root / "case"
            working.mkdir()
            with self.assertRaisesRegex(HTTPException, "absolute FILE paths"):
                _validate_deck_file_paths(
                    "SEQ_ASCII A B :: FILE 'safe.txt' '/outside/secret.txt' ;",
                    working_directory=working,
                    filesystem_scope=FilesystemScope(root=root),
                    http_exception=HTTPException,
                )

    def test_dynamic_or_trailing_file_arguments_fail_closed(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            working = Path(tmpdir).resolve()
            for deck in (
                "SEQ_ASCII A :: FILE <<dynamic>> ;",
                "SEQ_ASCII A :: FILE 'safe.txt' UNCHECKED ;",
            ):
                with self.assertRaisesRegex(HTTPException, "quoted literal"):
                    _validate_deck_file_paths(
                        deck,
                        working_directory=working,
                        filesystem_scope=FilesystemScope(root=working),
                        http_exception=HTTPException,
                    )

    def test_external_procedure_files_cannot_bypass_main_deck_scope(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            working = Path(tmpdir).resolve()
            (working / "EVIL.c2m").write_text(
                "SEQ_ASCII X :: FILE '/outside/secret' ;\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(HTTPException, "self-contained decks"):
                _validate_deck_file_paths(
                    "PROCEDURE EVIL ;\nEVIL :: ;\nEND: ;\n",
                    working_directory=working,
                    filesystem_scope=FilesystemScope(root=working),
                    http_exception=HTTPException,
                )

    def test_cle_bang_comments_cannot_hide_file_or_procedure_tokens(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            working = Path(tmpdir).resolve()
            hidden_quote_file = (
                "! '\n"
                "SEQ_ASCII X :: FILE '/etc/passwd' ;\n"
                "! '\n"
                "QUIT .\n"
            )
            with self.assertRaisesRegex(HTTPException, "absolute FILE paths"):
                _validate_deck_file_paths(
                    hidden_quote_file,
                    working_directory=working,
                    filesystem_scope=FilesystemScope(root=working),
                    http_exception=HTTPException,
                )

            hidden_quote_procedure = "! '\nPROCEDURE EVIL ;\n! '\nQUIT .\n"
            with self.assertRaisesRegex(HTTPException, "self-contained decks"):
                _validate_deck_file_paths(
                    hidden_quote_procedure,
                    working_directory=working,
                    filesystem_scope=FilesystemScope(root=working),
                    http_exception=HTTPException,
                )

    def test_legacy_cle_block_comments_fail_closed(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            working = Path(tmpdir).resolve()
            with self.assertRaisesRegex(HTTPException, "block comments"):
                _validate_deck_file_paths(
                    "(* unsupported comment *)\nQUIT .\n",
                    working_directory=working,
                    filesystem_scope=FilesystemScope(root=working),
                    http_exception=HTTPException,
                )

    def test_staging_rejects_symlinks_instead_of_following_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "case"
            source.mkdir()
            outside = root / "outside.txt"
            outside.write_text("secret", encoding="utf-8")
            (source / "escape.txt").symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "contains a symlink"):
                _stage_working_directory(source, root / "stage")

    def test_staging_rejects_a_file_replaced_after_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "case"
            source.mkdir()
            input_path = source / "reference.txt"
            input_path.write_text("original", encoding="utf-8")
            real_open = os.open
            replaced = False

            def replacing_open(
                path: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal replaced
                if Path(path).name == input_path.name and not replaced:
                    replaced = True
                    input_path.unlink()
                    input_path.write_text("replaced", encoding="utf-8")
                return real_open(path, flags, *args, **kwargs)

            with patch(
                "openmc2donjon.web.execution.os.open",
                side_effect=replacing_open,
            ), self.assertRaisesRegex(RuntimeError, "changed before"):
                _stage_working_directory(source, root / "stage")

    def test_staging_rejects_a_same_size_file_changed_after_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "case"
            source.mkdir()
            input_path = source / "reference.txt"
            input_path.write_text("original", encoding="utf-8")
            original_mtime_ns = input_path.stat().st_mtime_ns
            real_open = os.open
            changed = False

            def changing_open(
                path: object,
                flags: int,
                *args: object,
                **kwargs: object,
            ) -> int:
                nonlocal changed
                if Path(path).name == input_path.name and not changed:
                    changed = True
                    input_path.write_text("modified", encoding="utf-8")
                    os.utime(
                        input_path,
                        ns=(original_mtime_ns, original_mtime_ns + 1_000_000_000),
                    )
                return real_open(path, flags, *args, **kwargs)

            with patch(
                "openmc2donjon.web.execution.os.open",
                side_effect=changing_open,
            ), self.assertRaisesRegex(RuntimeError, "changed before"):
                _stage_working_directory(source, root / "stage")

    def test_staging_never_writes_concurrently_appended_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "case"
            source.mkdir()
            input_path = source / "input.bin"
            input_path.write_bytes(b"12345678")
            real_fdopen = os.fdopen

            class AppendingReader:
                def __init__(self, stream: object) -> None:
                    self.stream = stream
                    self.appended = False

                def __enter__(self) -> "AppendingReader":
                    return self

                def __exit__(self, *args: object) -> None:
                    self.stream.__exit__(*args)  # type: ignore[attr-defined]

                def read(self, size: int = -1) -> bytes:
                    block = self.stream.read(size)  # type: ignore[attr-defined]
                    if not self.appended:
                        self.appended = True
                        with input_path.open("ab") as output:
                            output.write(b"abcdefgh")
                    return block

            def appending_fdopen(
                descriptor: int,
                mode: str = "r",
                *args: object,
                **kwargs: object,
            ) -> object:
                stream = real_fdopen(descriptor, mode, *args, **kwargs)
                return AppendingReader(stream) if "r" in mode else stream

            destination = root / "stage"
            with (
                patch(
                    "openmc2donjon.web.execution.os.fdopen",
                    side_effect=appending_fdopen,
                ),
                self.assertRaisesRegex(RuntimeError, "grew beyond"),
            ):
                _stage_working_directory(source, destination)

            self.assertEqual((destination / "input.bin").stat().st_size, 8)

    def test_access_hook_receipts_bind_the_exact_executed_input_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            source = root / "working"
            source.mkdir()
            (source / "nested").mkdir()
            (source / "nested" / "input.txt").write_bytes(b"physics input\n")
            (source / "empty").mkdir()
            staged = root / "staged"
            staging = _stage_working_directory(source, staged)
            job_id = "0123456789abcdef"
            staged_manifest = root / "staged-inputs.json"
            staged_manifest.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.web-donjon-staging.v1",
                        "job_id": job_id,
                        "working_directory": str(source),
                        **staging,
                    }
                ),
                encoding="utf-8",
            )
            helper = root / "hook.py"
            helper.write_text(_rdonjon_fixed_hook_source(), encoding="utf-8")
            wrapper = root / "case.access"
            wrapper.write_text("", encoding="utf-8")
            save_wrapper = root / "case.save"
            save_wrapper.write_text("", encoding="utf-8")
            runtime = root / "runtime"
            runtime.mkdir()
            deck_bytes = b"QUIT .\n"
            (runtime / "mydata").write_bytes(deck_bytes)
            deck_sha256 = hashlib.sha256(deck_bytes).hexdigest()
            receipt = root / "access-receipt.json"
            runtime_output = root / "runtime-output"
            runtime_manifest = root / "runtime-output-manifest.json"
            environment = {
                "PATH": os.defpath,
                "OPENMC2DONJON_WEB_JOB_ID": job_id,
                "OPENMC2DONJON_WEB_STAGED_DIRECTORY": str(staged),
                "OPENMC2DONJON_WEB_STAGED_MANIFEST": str(staged_manifest),
                "OPENMC2DONJON_WEB_ACCESS_RECEIPT": str(receipt),
                "OPENMC2DONJON_WEB_EXPECTED_DECK_SHA256": deck_sha256,
                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_DIRECTORY": str(runtime_output),
                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_MANIFEST": str(runtime_manifest),
                "OPENMC2DONJON_WEB_MAX_OUTPUT_FILES": "10",
                "OPENMC2DONJON_WEB_MAX_OUTPUT_ENTRIES": "10",
                "OPENMC2DONJON_WEB_MAX_OUTPUT_BYTES": "1048576",
            }

            completed = subprocess.run(
                [sys.executable, "-I", str(helper), str(wrapper)],
                cwd=runtime,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(
                (runtime / "nested" / "input.txt").read_bytes(),
                b"physics input\n",
            )
            self.assertTrue((runtime / "empty").is_dir())
            access = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(access["executed_inputs"], staging["artifacts"])
            save_completed = subprocess.run(
                [sys.executable, "-I", str(helper), str(save_wrapper)],
                cwd=runtime,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            self.assertEqual(save_completed.returncode, 0, save_completed.stderr)
            saved_outputs = json.loads(runtime_manifest.read_text(encoding="utf-8"))
            self.assertEqual(saved_outputs["entry_count"], 3)
            self.assertEqual(saved_outputs["file_count"], 0)
            _validate_rdonjon_hook_evidence(
                job_id=job_id,
                expected_deck_sha256=deck_sha256,
                access_receipt_path=receipt,
                staged_manifest_path=staged_manifest,
                runtime_output_manifest_path=runtime_manifest,
                runtime_output_directory=runtime_output,
            )

            access["executed_inputs"][0]["sha256"] = "0" * 64
            receipt.write_text(json.dumps(access), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "executed inputs"):
                _validate_rdonjon_hook_evidence(
                    job_id=job_id,
                    expected_deck_sha256=deck_sha256,
                    access_receipt_path=receipt,
                    staged_manifest_path=staged_manifest,
                    runtime_output_manifest_path=runtime_manifest,
                    runtime_output_directory=runtime_output,
                )

    def test_save_hook_never_archives_concurrently_appended_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            runtime = root / "runtime"
            runtime.mkdir()
            source_output = runtime / "physics.dat"
            source_output.write_bytes(b"A")
            staged_manifest = root / "staged-inputs.json"
            staged_manifest.write_text(
                json.dumps(
                    {
                        "schema": "openmc2donjon.web-donjon-staging.v1",
                        "job_id": "0123456789abcdef",
                        "entry_count": 0,
                        "directory_count": 0,
                        "directories": [],
                        "file_count": 0,
                        "total_bytes": 0,
                        "artifacts": [],
                    }
                ),
                encoding="utf-8",
            )
            source = _rdonjon_fixed_hook_source()
            copy_boundary = "                os.lseek(source_descriptor, 0, os.SEEK_SET)\n"
            self.assertEqual(source.count(copy_boundary), 1)
            source = source.replace(
                copy_boundary,
                (
                    "                with path.open(\"ab\") as concurrent_output:\n"
                    "                    concurrent_output.write(b\"B\" * 100)\n"
                    + copy_boundary
                ),
            )
            helper = root / "hook.py"
            helper.write_text(source, encoding="utf-8")
            wrapper = root / "case.save"
            wrapper.write_text("", encoding="utf-8")
            archived_output = root / "runtime-output"
            output_manifest = root / "runtime-output-manifest.json"
            environment = {
                "PATH": os.defpath,
                "OPENMC2DONJON_WEB_JOB_ID": "0123456789abcdef",
                "OPENMC2DONJON_WEB_STAGED_MANIFEST": str(staged_manifest),
                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_DIRECTORY": str(archived_output),
                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_MANIFEST": str(output_manifest),
                "OPENMC2DONJON_WEB_MAX_OUTPUT_FILES": "10",
                "OPENMC2DONJON_WEB_MAX_OUTPUT_ENTRIES": "10",
                "OPENMC2DONJON_WEB_MAX_OUTPUT_BYTES": "1",
            }

            completed = subprocess.run(
                [sys.executable, "-I", str(helper), str(wrapper)],
                cwd=runtime,
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("grew beyond its admitted archive size", completed.stderr)
            self.assertFalse(output_manifest.exists())
            target = archived_output / "physics.dat"
            self.assertTrue(not target.exists() or target.stat().st_size <= 1)

    def test_staging_entry_limit_counts_directories_and_files_together(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "case"
            source.mkdir()
            (source / "directory-a").mkdir()
            (source / "directory-b").mkdir()
            (source / "input.txt").write_text("input", encoding="utf-8")
            with (
                patch("openmc2donjon.web.execution.DONJON_MAX_STAGED_ENTRIES", 2),
                self.assertRaisesRegex(ValueError, "staging entry count"),
            ):
                _stage_working_directory(source, root / "stage")

    def test_staging_bounds_depth_and_relative_path_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            depth_source = root / "depth-case"
            (depth_source / "one" / "two").mkdir(parents=True)
            with (
                patch("openmc2donjon.web.execution.DONJON_MAX_STAGED_DEPTH", 1),
                self.assertRaisesRegex(ValueError, "staging depth"),
            ):
                _stage_working_directory(depth_source, root / "depth-stage")

            length_source = root / "length-case"
            length_source.mkdir()
            (length_source / "long-name.txt").write_text("input", encoding="utf-8")
            with (
                patch(
                    "openmc2donjon.web.execution.DONJON_MAX_STAGED_RELATIVE_PATH_BYTES",
                    8,
                ),
                self.assertRaisesRegex(ValueError, "relative path longer"),
            ):
                _stage_working_directory(length_source, root / "length-stage")

    def test_staging_manifest_bound_covers_the_entry_and_path_contract(self) -> None:
        conservative_json_bytes_per_entry = (
            DONJON_MAX_STAGED_RELATIVE_PATH_BYTES + 256
        )
        self.assertGreaterEqual(
            DONJON_MAX_STAGING_MANIFEST_BYTES,
            DONJON_MAX_STAGED_ENTRIES * conservative_json_bytes_per_entry,
        )

    def test_staging_stops_when_service_shutdown_has_started(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source = root / "case"
            source.mkdir()
            with (
                patch(
                    "openmc2donjon.web.execution._RDONJON_SHUTDOWN.is_set",
                    return_value=True,
                ),
                self.assertRaisesRegex(RuntimeError, "service is shutting down"),
            ):
                _stage_working_directory(source, root / "stage")

    @unittest.skipUnless(os.name == "posix", "process-group termination is POSIX-specific")
    def test_timeout_terminates_the_entire_rdonjon_process_group(self) -> None:
        process = Mock()
        process.pid = 4567
        process.returncode = -signal.SIGTERM
        process.stdout = io.BytesIO(b"partial stdout")
        process.stderr = io.BytesIO(b"partial stderr")
        process.wait.side_effect = subprocess.TimeoutExpired(["rdonjon"], 0.001)
        with (
            patch("openmc2donjon.web.execution.subprocess.Popen", return_value=process) as popen,
            patch(
                "openmc2donjon.web.execution._terminate_rdonjon_process_group"
            ) as terminate_group,
            self.assertRaises(subprocess.TimeoutExpired),
        ):
            _run_rdonjon_bounded(
                ["/fixed/Donjon/rdonjon", "-q", "case.x2m"],
                cwd=Path("/fixed/Donjon"),
                env={},
                timeout=0.001,
            )
        self.assertTrue(popen.call_args.kwargs["start_new_session"])
        terminate_group.assert_called_once_with(process)

    @unittest.skipUnless(os.name == "posix", "process-group termination is POSIX-specific")
    def test_group_kill_does_not_trust_an_exited_launcher_leader(self) -> None:
        process = Mock()
        process.pid = 4567
        process.returncode = 0
        process.poll.return_value = 0
        process.wait.return_value = 0
        with patch("openmc2donjon.web.execution.os.killpg") as killpg:
            _terminate_rdonjon_process_group(process, grace_seconds=0.0)

        self.assertEqual(
            killpg.call_args_list,
            [
                call(4567, signal.SIGTERM),
                call(4567, 0),
                call(4567, signal.SIGKILL),
            ],
        )
        process.poll.assert_called_once_with()

    def test_stdout_is_drained_to_a_bounded_tail(self) -> None:
        process = Mock()
        process.pid = 4567
        process.returncode = 0
        process.stdout = io.BytesIO(b"0123456789")
        process.stderr = io.BytesIO(b"")
        process.wait.return_value = 0
        with (
            patch("openmc2donjon.web.execution.subprocess.Popen", return_value=process),
            patch("openmc2donjon.web.execution.DONJON_MAX_STDIO_STREAM_BYTES", 8),
            patch(
                "openmc2donjon.web.execution._terminate_rdonjon_process_group"
            ) as terminate_group,
            self.assertRaisesRegex(RuntimeError, "bounded stream limit"),
        ):
            _run_rdonjon_bounded(
                ["/fixed/Donjon/rdonjon", "-q", "case.x2m"],
                cwd=Path("/fixed/Donjon"),
                env={},
                timeout=1,
            )
        terminate_group.assert_called_once_with(process)

    def test_persisted_job_cannot_redirect_status_writes_outside_its_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            job_id = "0123456789abcdef"
            run = archive / job_id
            run.mkdir(parents=True)
            outside = Path(tmpdir).resolve() / "outside.json"
            outside.write_text("do not replace", encoding="utf-8")
            payload = {
                "schema": "openmc2donjon.web-donjon-job.v1",
                "job_id": job_id,
                "run_id": job_id,
                "operation": "donjon",
                "status": "running",
                "created_at": 1.0,
                "message": "forged",
                "log_tail": "",
                "archive_root": str(archive),
                "run_directory": str(run),
                "request_path": str(run / "request.json"),
                "status_path": str(outside),
                "artifacts_path": str(run / "artifacts.json"),
                "log_path": str(run / "run.log"),
                "working_directory": None,
                "staged_manifest_path": None,
                "runtime_output_directory": None,
                "deck_path": None,
                "result_path": None,
            }
            (run / "status.json").write_text(json.dumps(payload), encoding="utf-8")

            self.assertIsNone(_read_persisted_job(archive, job_id))
            self.assertEqual(outside.read_text(encoding="utf-8"), "do not replace")

    def test_second_store_does_not_fail_a_live_foreign_job(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": False,
            }
            owner = _JobStore()
            job = owner.create(
                operation="donjon",
                archive_root=archive,
                request=request,
            )
            observer = _JobStore()

            observed = observer.recover(job["job_id"], archive)

            self.assertIsNotNone(observed)
            assert observed is not None
            self.assertEqual(observed["status"], "queued")
            persisted = json.loads(
                Path(job["status_path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(persisted["status"], "queued")
            owner.publish_terminal(
                job["job_id"],
                status="failed",
                finished_at=time.time(),
                message="test owner completed",
            )

    def test_recovery_fails_closed_only_after_owner_lock_is_released(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": False,
            }
            owner = _JobStore()
            job = owner.create(
                operation="donjon",
                archive_root=archive,
                request=request,
            )
            owner.release_owner(job["job_id"])

            recovered = _JobStore().recover(job["job_id"], archive)

            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(recovered["status"], "failed")
            self.assertIn("interrupted", recovered["message"])

    def test_terminal_cache_is_bounded_without_deleting_persisted_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "openmc2donjon.web.execution.DONJON_MAX_CACHED_TERMINAL_JOBS", 2
        ):
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": False,
            }
            jobs = _JobStore()
            created = []
            for index in range(3):
                job = jobs.create(
                    operation="donjon",
                    archive_root=archive,
                    request=request,
                )
                jobs.publish_terminal(
                    job["job_id"],
                    status="failed",
                    finished_at=time.time(),
                    message=f"failed {index}",
                )
                created.append(job)

            self.assertIsNone(jobs.get(created[0]["job_id"]))
            self.assertIsNotNone(jobs.get(created[-1]["job_id"]))
            self.assertIsNotNone(
                _read_persisted_job(archive, created[0]["job_id"])
            )

    def test_job_listing_returns_only_the_newest_bounded_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": False,
            }
            owner = _JobStore()
            created = []
            for index in range(3):
                job = owner.create(
                    operation="donjon",
                    archive_root=archive,
                    request=request,
                )
                owner.publish_terminal(
                    job["job_id"],
                    status="failed",
                    finished_at=time.time(),
                    message=f"failed {index}",
                )
                timestamp = 1_000_000_000 + index
                os.utime(job["run_directory"], ns=(timestamp, timestamp))
                created.append(job)

            with patch(
                "openmc2donjon.web.execution.DONJON_MAX_LISTED_JOBS", 2
            ):
                listed = _JobStore().list(archive)

            self.assertEqual(
                {job["job_id"] for job in listed},
                {created[1]["job_id"], created[2]["job_id"]},
            )

    def test_terminal_seal_rejects_an_archived_deck_with_different_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": False,
            }
            jobs = _JobStore()
            job = jobs.create(
                operation="donjon",
                archive_root=archive,
                request=request,
            )
            archived_deck = Path(job["run_directory"]) / "case.x2m"
            archived_deck.write_text("DIFFERENT .\n", encoding="utf-8")

            jobs.publish_terminal(
                job["job_id"],
                status="completed",
                finished_at=time.time(),
                message="must not remain completed",
                deck_path=str(archived_deck),
            )

            sealed = jobs.get(job["job_id"])
            assert sealed is not None
            self.assertEqual(sealed["status"], "failed")
            self.assertIsNone(sealed["deck_path"])
            self.assertIn("changed", sealed["message"])
            self.assertIsNotNone(_read_persisted_job(archive, job["job_id"]))

    def test_completed_job_fails_closed_if_runtime_output_changes_after_seal(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": True,
            }
            jobs = _JobStore()
            job = jobs.create(
                operation="donjon",
                archive_root=archive,
                request=request,
            )
            deck, output, result = _write_valid_terminal_evidence(job)
            jobs.publish_terminal(
                job["job_id"],
                status="completed",
                finished_at=time.time(),
                message="complete",
                deck_path=str(deck),
                result_path=str(result),
                k_effective=1.0,
            )
            self.assertIsNotNone(_read_persisted_job(archive, job["job_id"]))

            output.write_bytes(b"BBBB")

            self.assertIsNone(_read_persisted_job(archive, job["job_id"]))
            failed = jobs.get(job["job_id"])
            assert failed is not None
            self.assertEqual(failed["status"], "failed")
            self.assertIsNone(failed["k_effective"])
            self.assertIn("no longer valid", failed["message"])

    def test_completed_job_binds_published_keff_to_final_result_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir).resolve() / "archive"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "timeout_seconds": 10,
                "expect_k_effective": True,
            }
            jobs = _JobStore()
            job = jobs.create(
                operation="donjon",
                archive_root=archive,
                request=request,
            )
            deck, _, result = _write_valid_terminal_evidence(job)
            jobs.publish_terminal(
                job["job_id"],
                status="completed",
                finished_at=time.time(),
                message="complete",
                deck_path=str(deck),
                result_path=str(result),
                k_effective=1.0,
            )

            result.write_text("k-effective = 2.000000\n", encoding="utf-8")

            self.assertIsNone(_read_persisted_job(archive, job["job_id"]))
            failed = jobs.get(job["job_id"])
            assert failed is not None
            self.assertEqual(failed["status"], "failed")
            self.assertIsNone(failed["result_path"])
            self.assertIn("k-effective", failed["message"])

    def test_web_jobs_serialize_the_non_atomic_rdonjon_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve() / "dragon"
            donjon = root / "Donjon"
            launcher, solver = _write_fake_donjon_installation(root)
            archive = Path(tmpdir).resolve() / "runs"
            request = {
                "deck_text": "QUIT .\n",
                "deck_filename": "case.x2m",
                "donjon_root": str(root),
                "artifact_directory": str(archive),
                "working_directory": "",
                "timeout_seconds": 10,
                "expect_k_effective": False,
                "launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
                "solver_sha256": hashlib.sha256(solver.read_bytes()).hexdigest(),
            }
            jobs = _JobStore()
            first = jobs.create(
                operation="donjon",
                archive_root=archive,
                request=request,
                donjon_root=root,
            )
            second = jobs.create(
                operation="donjon",
                archive_root=archive,
                request=request,
                donjon_root=root,
            )
            guard = Lock()
            active = 0
            max_active = 0

            def fake_launcher(
                argv: list[str],
                **kwargs: object,
            ) -> subprocess.CompletedProcess[str]:
                nonlocal active, max_active
                with guard:
                    active += 1
                    max_active = max(max_active, active)
                try:
                    time.sleep(0.04)
                    environment = kwargs["env"]
                    assert isinstance(environment, dict)
                    staged_path = Path(
                        str(environment["OPENMC2DONJON_WEB_STAGED_MANIFEST"])
                    )
                    staged = json.loads(staged_path.read_text(encoding="utf-8"))
                    executed_inputs = sorted(
                        staged["artifacts"], key=lambda item: item["relative_path"]
                    )
                    Path(
                        str(environment["OPENMC2DONJON_WEB_ACCESS_RECEIPT"])
                    ).write_text(
                        json.dumps(
                            {
                                "schema": "openmc2donjon.web-donjon-access.v1",
                                "job_id": environment["OPENMC2DONJON_WEB_JOB_ID"],
                                "executed_deck_sha256": environment[
                                    "OPENMC2DONJON_WEB_EXPECTED_DECK_SHA256"
                                ],
                                "staged_file_count": staged["file_count"],
                                "staged_total_bytes": staged["total_bytes"],
                                "staged_manifest_sha256": hashlib.sha256(
                                    staged_path.read_bytes()
                                ).hexdigest(),
                                "executed_inputs": executed_inputs,
                                "executed_inputs_sha256": hashlib.sha256(
                                    json.dumps(
                                        executed_inputs,
                                        sort_keys=True,
                                        separators=(",", ":"),
                                    ).encode("utf-8")
                                ).hexdigest(),
                            }
                        ),
                        encoding="utf-8",
                    )
                    runtime_output = Path(
                        str(
                            environment[
                                "OPENMC2DONJON_WEB_RUNTIME_OUTPUT_DIRECTORY"
                            ]
                        )
                    )
                    runtime_output.mkdir()
                    Path(
                        str(environment["OPENMC2DONJON_WEB_RUNTIME_OUTPUT_MANIFEST"])
                    ).write_text(
                        json.dumps(
                            {
                                "schema": "openmc2donjon.web-donjon-runtime-output.v1",
                                "job_id": environment["OPENMC2DONJON_WEB_JOB_ID"],
                                "entry_count": 0,
                                "file_count": 0,
                                "total_bytes": 0,
                                "artifacts": [],
                            }
                        ),
                        encoding="utf-8",
                    )
                    stem = Path(argv[-1]).stem
                    machine = f"{platform.system()}_{platform.machine()}"
                    result = donjon / machine / f"{stem}.result"
                    result.parent.mkdir(parents=True, exist_ok=True)
                    result.write_text("normal end\n", encoding="utf-8")
                    return subprocess.CompletedProcess(argv, 0, stdout="[OK]", stderr="")
                finally:
                    with guard:
                        active -= 1

            with patch(
                "openmc2donjon.web.execution._run_rdonjon_bounded",
                side_effect=fake_launcher,
            ):
                threads = [
                    Thread(
                        target=_run_donjon_job,
                        kwargs={
                            "jobs": jobs,
                            "job_id": item["job_id"],
                            "request": dict(request),
                            "root": root,
                        },
                    )
                    for item in (first, second)
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=2)

            self.assertTrue(all(not thread.is_alive() for thread in threads))
            self.assertEqual(max_active, 1)
            self.assertEqual(jobs.get(first["job_id"])["status"], "completed")
            self.assertEqual(jobs.get(second["job_id"])["status"], "completed")


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class ProjectComponentDiagnosticBindingTests(unittest.TestCase):
    def test_binds_exactly_one_accepted_manifest_component_output(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "outputs" / "fuel.mcompo.txt"
            output.parent.mkdir()
            output.write_text("SIGNATURE\nL_MULTICOMPO\n", encoding="utf-8")
            manifest = {
                "schema": "openmc2donjon.project.v1",
                "name": "Diagnostic binding",
                "components": [
                    {
                        "id": "fuel",
                        "label": "Fuel",
                        "input": "components/fuel.h5",
                        "output": "outputs/fuel.mcompo.txt",
                        "format": "multicompo",
                        "contract": "converter-hdf5",
                    }
                ],
                "consumer": {"kind": "external", "label": "External", "href": "/donjon"},
            }
            (root / "openmc2donjon.project.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            bound = _bind_declared_input_files(
                [{"source_path": str(output), "relative_path": "fuel.mcompo.txt"}],
                filesystem_scope=FilesystemScope(),
                http_exception=HTTPException,
            )
            status = {
                "components": [
                    {
                        "id": "fuel",
                        "output": {"state": "accepted", "issues": []},
                        "paths": {"output": str(output)},
                    }
                ]
            }
            with patch("openmc2donjon.web.project.project_status", return_value=status):
                binding = _project_component_diagnostic_binding(
                    project_root=root,
                    component_id="fuel",
                    input_files=bound,
                    http_exception=HTTPException,
                )
            self.assertEqual(binding["project_component_declaration"]["id"], "fuel")
            self.assertRegex(binding["declaration_sha256"], r"^[a-f0-9]{64}$")
            self.assertEqual(
                binding["project_manifest_sha256"],
                hashlib.sha256((root / "openmc2donjon.project.json").read_bytes()).hexdigest(),
            )


class PhysicalSphSourceValidationTests(unittest.TestCase):
    def _write_sidecar(
        self,
        path: Path,
        *,
        kind: str = "openmc-ce-mg",
        residual: float = 0.01,
    ) -> None:
        with h5py.File(path, "w") as h5:
            h5.attrs["sph_real"] = True
            h5.attrs["sph_kind"] = kind
            h5.attrs["sph_derivation"] = "rate-preserving-ce-mg-fixed-point"
            h5.attrs["sph_target"] = "rate"
            h5.attrs["sph_flux_normalization"] = "power"
            h5.attrs["sph_zero_flux_policy"] = "reject"
            h5.attrs["sph_identity_bin_count"] = 0
            h5.attrs["sph_floored_bin_count"] = 0
            h5.attrs["sph_frozen_group_bin_count"] = 0
            h5.attrs["sph_clipped_count"] = 0
            h5.attrs["sph_max_update_residual"] = residual

    def test_accepts_only_converged_rate_preserving_sidecars(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "physical.h5"
            self._write_sidecar(path)
            _validate_physical_sph_source(path, HTTPException)

    def test_rejects_legacy_global_and_unconverged_sidecars(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            global_path = Path(tmpdir) / "global.h5"
            self._write_sidecar(
                global_path,
                kind="openmc-ce-mg-rate-120deg-tied-global",
            )
            with self.assertRaisesRegex(HTTPException, "empirical global"):
                _validate_physical_sph_source(global_path, HTTPException)

            unconverged_path = Path(tmpdir) / "unconverged.h5"
            self._write_sidecar(unconverged_path, residual=0.021)
            with self.assertRaisesRegex(HTTPException, "not converged"):
                _validate_physical_sph_source(unconverged_path, HTTPException)

    def test_rejects_sidecars_with_numerical_exemptions(self) -> None:
        from fastapi import HTTPException

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "identity.h5"
            self._write_sidecar(path)
            with h5py.File(path, "r+") as h5:
                h5.attrs["sph_zero_flux_policy"] = "identity"
                h5.attrs["sph_identity_bin_count"] = 1
            with self.assertRaisesRegex(HTTPException, "numerical exemptions"):
                _validate_physical_sph_source(path, HTTPException)


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class MockExecutionEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        from openmc2donjon.web.server import create_app

        self.client = TestClient(create_app(mock_mode=True))

    def test_mock_openmc_export_is_explicitly_non_scientific(self) -> None:
        response = self.client.post(
            "/api/execute/openmc-export",
            json={
                "recipe_path": "/mock/export_recipe.py",
                "statepoint_path": "/mock/statepoint.130.h5",
                "load_statepoint": True,
                "output_path": "/mock/mgxs_library.h5",
                "overwrite": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["mixtures"], 7)
        self.assertEqual(response.json()["energy_groups"], 33)
        self.assertTrue(response.json()["mock_mode"])
        provenance = response.json()["openmc_provenance"]
        self.assertEqual(provenance["status"], "legacy")
        self.assertFalse(provenance["capabilities"]["reference_bound"])
        self.assertFalse(provenance["integrity"]["ok"])

    def test_mock_physical_sph_and_apply(self) -> None:
        sidecar = self.client.post(
            "/api/execute/sph-sidecar",
            json={
                "strategy": "ratio",
                "input_h5": "/mock/mgxs_library.h5",
                "output_path": "/mock/openmc_sph.h5",
                "reference_flux": "/mock/openmc_ce_flux.h5::openmc_volume_flux",
                "mg_flux": "/mock/openmc_mg_flux.h5::openmc_mg_flux",
                "summary_json": "/mock/openmc_sph_summary.json",
            },
        )
        self.assertEqual(sidecar.status_code, 200)
        self.assertEqual(sidecar.json()["strategy"], "ratio")
        self.assertAlmostEqual(sidecar.json()["sph_min"], 1.0)
        self.assertAlmostEqual(sidecar.json()["max_update_residual"], 0.0)
        self.assertEqual(
            sidecar.json()["summary_path"],
            "/mock/openmc_sph_summary.json",
        )

        applied = self.client.post(
            "/api/execute/apply-sph",
            json={
                "input_h5": "/mock/mgxs_library.h5",
                "sph_source": "/mock/openmc_sph.h5",
                "output_path": "/mock/mgxs_sph_applied.h5",
                "input_format": "converter",
                "summary_json": "/mock/apply_sph_summary.json",
            },
        )
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["operation"], "apply-sph")
        self.assertEqual(
            applied.json()["summary_path"],
            "/mock/apply_sph_summary.json",
        )

    def test_rejects_invalid_sph_damping_instead_of_falling_back(self) -> None:
        base = {
            "strategy": "ratio",
            "input_h5": "/mock/mgxs_library.h5",
            "output_path": "/mock/openmc_sph.h5",
            "reference_flux": "/mock/openmc_ce_flux.h5::openmc_volume_flux",
            "mg_flux": "/mock/openmc_mg_flux.h5::openmc_mg_flux",
        }
        for damping in (-0.1, 1.01, "not-a-number"):
            response = self.client.post(
                "/api/execute/sph-sidecar",
                json={**base, "damping": damping},
            )
            self.assertEqual(response.status_code, 422)

    def test_rejects_empirical_constant_sph_strategy(self) -> None:
        response = self.client.post(
            "/api/execute/sph-sidecar",
            json={
                "strategy": "constant",
                "constant_value": 1.0082,
                "input_h5": "/mock/mgxs_library.h5",
                "output_path": "/mock/openmc_sph.h5",
                "reference_flux": "/mock/openmc_ce_flux.h5::openmc_volume_flux",
                "mg_flux": "/mock/openmc_mg_flux.h5::openmc_mg_flux",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_rejects_frozen_clipped_or_floored_production_sph(self) -> None:
        base = {
            "strategy": "ratio",
            "input_h5": "/mock/mgxs_library.h5",
            "output_path": "/mock/openmc_sph.h5",
            "reference_flux": "/mock/openmc_ce_flux.h5::openmc_volume_flux",
            "mg_flux": "/mock/openmc_mg_flux.h5::openmc_mg_flux",
        }
        for override in (
            {"freeze_groups": [1]},
            {"flux_floor_rel": 0.001},
            {"clip_min": 0.5},
            {"clip_max": 2.0},
        ):
            response = self.client.post(
                "/api/execute/sph-sidecar",
                json={**base, **override},
            )
            self.assertEqual(response.status_code, 422)
            self.assertIn("forbids frozen groups", response.json()["detail"])

        identity = self.client.post(
            "/api/execute/sph-sidecar",
            json={**base, "zero_flux_policy": "identity"},
        )
        self.assertEqual(identity.status_code, 422)
        self.assertIn("zero_flux_policy", identity.json()["detail"])

    def test_mock_donjon_job_completes_and_can_be_polled(self) -> None:
        started = self.client.post(
            "/api/execute/donjon",
            json={"deck_text": "MODULE END: ;\nEND: ;\n", "deck_filename": "case.x2m"},
        )
        self.assertEqual(started.status_code, 200)
        payload = started.json()
        self.assertEqual(payload["status"], "completed")
        self.assertAlmostEqual(payload["k_effective"], 1.145655)

        polled = self.client.get(f"/api/execution/jobs/{payload['job_id']}")
        self.assertEqual(polled.status_code, 200)
        self.assertEqual(polled.json()["status"], "completed")

    def test_rejects_non_x2m_or_nested_deck_names(self) -> None:
        for name in ("case.txt", "../case.x2m"):
            response = self.client.post(
                "/api/execute/donjon",
                json={"deck_text": "QUIT .", "deck_filename": name},
            )
            self.assertEqual(response.status_code, 422)


@unittest.skipUnless(_WEB_AVAILABLE, "openmc2donjon[web,dev] not installed")
class PersistentDonjonJobTests(unittest.TestCase):
    def test_thread_start_failure_is_sealed_and_releases_job_ownership(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir).resolve()
            donjon_root = workspace / "dragon"
            _write_fake_donjon_installation(donjon_root)
            archive = workspace / "runs"
            client = TestClient(create_app(mock_mode=False, workspace_root=workspace))

            class FailingThread:
                def __init__(self, **_: object) -> None:
                    pass

                def start(self) -> None:
                    raise RuntimeError("thread unavailable")

            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ), patch("openmc2donjon.web.execution.Thread", FailingThread):
                response = client.post(
                    "/api/execute/donjon",
                    json={
                        "deck_text": "QUIT .\n",
                        "deck_filename": "case.x2m",
                        "artifact_directory": str(archive),
                    },
                )

            self.assertEqual(response.status_code, 503, response.text)
            run_directories = [path for path in archive.iterdir() if path.is_dir()]
            self.assertEqual(len(run_directories), 1)
            job_id = run_directories[0].name
            recovered = _read_persisted_job(archive, job_id)
            self.assertIsNotNone(recovered)
            assert recovered is not None
            self.assertEqual(recovered["status"], "failed")
            self.assertIn("could not start", recovered["message"])

    def test_thread_constructor_failures_release_every_queue_slot(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir).resolve()
            donjon_root = workspace / "dragon"
            _write_fake_donjon_installation(donjon_root)
            archive = workspace / "runs"
            client = TestClient(create_app(mock_mode=False, workspace_root=workspace))

            class FailingThread:
                def __init__(self, **_: object) -> None:
                    raise RuntimeError("constructor unavailable")

            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ), patch("openmc2donjon.web.execution.Thread", FailingThread):
                responses = [
                    client.post(
                        "/api/execute/donjon",
                        json={
                            "deck_text": "QUIT .\n",
                            "deck_filename": "case.x2m",
                            "artifact_directory": str(archive),
                        },
                    )
                    for _ in range(5)
                ]

            self.assertTrue(
                all(response.status_code == 503 for response in responses),
                [response.text for response in responses],
            )
            run_directories = [path for path in archive.iterdir() if path.is_dir()]
            self.assertEqual(len(run_directories), 5)
            for run_directory in run_directories:
                recovered = _read_persisted_job(archive, run_directory.name)
                self.assertIsNotNone(recovered)
                assert recovered is not None
                self.assertEqual(recovered["status"], "failed")
                self.assertIn("could not be constructed", recovered["message"])

    def test_unexpected_worker_exception_fails_the_job_instead_of_leaving_queued(
        self,
    ) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir).resolve()
            donjon_root = workspace / "dragon"
            _write_fake_donjon_installation(donjon_root)
            archive = workspace / "runs"
            client = TestClient(create_app(mock_mode=False, workspace_root=workspace))

            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ), patch(
                "openmc2donjon.web.execution._run_donjon_job",
                side_effect=TypeError("worker boom"),
            ):
                response = client.post(
                    "/api/execute/donjon",
                    json={
                        "deck_text": "QUIT .\n",
                        "deck_filename": "case.x2m",
                        "artifact_directory": str(archive),
                    },
                )
                self.assertEqual(response.status_code, 200, response.text)
                terminal = self._wait_for_job(client, response.json(), archive)

            self.assertEqual(terminal["status"], "failed")
            self.assertIn("worker failed unexpectedly", str(terminal["message"]))
            self.assertIn("worker boom", str(terminal["message"]))

    def test_each_job_has_an_independent_hashed_archive_and_can_be_recovered(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir).resolve()
            donjon_root = workspace / "dragon"
            donjon_dir = donjon_root / "Donjon"
            _write_fake_donjon_installation(donjon_root)
            project_root = workspace / "project"
            project_root.mkdir()
            working = project_root / "case"
            working.mkdir()
            (working / "reference.txt").write_text("reference", encoding="utf-8")
            source_deck = project_root / "decks" / "native_sph.x2m"
            source_deck.parent.mkdir()
            deck_text = "SEQ_ASCII REF :: FILE 'reference.txt' ;\nQUIT .\n"
            source_deck.write_text(deck_text, encoding="utf-8")
            source_sha256 = hashlib.sha256(source_deck.read_bytes()).hexdigest()
            manifest = {
                "schema": "openmc2donjon.project.v1",
                "name": "Native SPH persistence test",
                "acceptance_mode": "handoff-only",
                "components": [
                    {
                        "id": "fullcore",
                        "label": "Full core",
                        "required": True,
                        "input": "case/reference-input.h5",
                        "output": "case/native-output.macrolib.txt",
                        "format": "macrolib",
                        "contract": "native-sph",
                        "native_sph": {
                            "deck": "decks/native_sph.x2m",
                            "working_directory": "case",
                        },
                    }
                ],
                "consumer": {"kind": "external", "label": "Test", "href": "/donjon"},
            }
            manifest_path = project_root / "openmc2donjon.project.json"
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            archive_root = project_root / "diagnostics" / "native-sph-runs"
            client = TestClient(
                create_app(mock_mode=False, workspace_root=workspace)
            )

            def completed_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertEqual(argv[1], "-q")
                self.assertRegex(argv[2], r"^openmc2donjon_web_[a-f0-9]{16}\.x2m$")
                self.assertEqual(Path(str(kwargs["cwd"])), donjon_dir)
                environment = kwargs["env"]
                assert isinstance(environment, dict)
                job_id = str(environment["OPENMC2DONJON_WEB_JOB_ID"])
                access_receipt = Path(
                    str(environment["OPENMC2DONJON_WEB_ACCESS_RECEIPT"])
                )
                staged_manifest_path = Path(
                    str(environment["OPENMC2DONJON_WEB_STAGED_MANIFEST"])
                )
                staged_manifest = json.loads(
                    staged_manifest_path.read_text(encoding="utf-8")
                )
                executed_inputs = sorted(
                    staged_manifest["artifacts"],
                    key=lambda item: item["relative_path"],
                )
                access_receipt.write_text(
                    json.dumps(
                        {
                            "schema": "openmc2donjon.web-donjon-access.v1",
                            "job_id": job_id,
                            "executed_deck_sha256": environment[
                                "OPENMC2DONJON_WEB_EXPECTED_DECK_SHA256"
                            ],
                            "staged_file_count": staged_manifest["file_count"],
                            "staged_total_bytes": staged_manifest["total_bytes"],
                            "staged_manifest_sha256": hashlib.sha256(
                                staged_manifest_path.read_bytes()
                            ).hexdigest(),
                            "executed_inputs": executed_inputs,
                            "executed_inputs_sha256": hashlib.sha256(
                                json.dumps(
                                    executed_inputs,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                ).encode("utf-8")
                            ).hexdigest(),
                        }
                    ),
                    encoding="utf-8",
                )
                runtime_output = Path(
                    str(environment["OPENMC2DONJON_WEB_RUNTIME_OUTPUT_DIRECTORY"])
                )
                runtime_output.mkdir()
                produced = runtime_output / "native_sph.macrolib.txt"
                produced.write_text("physical output", encoding="utf-8")
                output_manifest = Path(
                    str(environment["OPENMC2DONJON_WEB_RUNTIME_OUTPUT_MANIFEST"])
                )
                output_manifest.write_text(
                    json.dumps(
                        {
                            "schema": "openmc2donjon.web-donjon-runtime-output.v1",
                            "job_id": job_id,
                            "file_count": 1,
                            "total_bytes": produced.stat().st_size,
                            "artifacts": [
                                {
                                    "relative_path": produced.name,
                                    "bytes": produced.stat().st_size,
                                    "sha256": hashlib.sha256(
                                        produced.read_bytes()
                                    ).hexdigest(),
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                machine = f"{platform.system()}_{platform.machine()}"
                result = donjon_dir / machine / f"openmc2donjon_web_{job_id}.result"
                result.parent.mkdir(parents=True, exist_ok=True)
                result.write_text("normal end\n", encoding="utf-8")
                return subprocess.CompletedProcess(argv, 0, stdout="[OK]", stderr="")

            request = {
                "deck_text": deck_text,
                "deck_filename": "native_sph.x2m",
                "donjon_root": str(donjon_root),
                "artifact_directory": str(archive_root),
                "working_directory": str(working),
                "source_deck_path": str(source_deck),
                "source_deck_sha256": source_sha256,
                "project_root": str(project_root),
                "component_id": "fullcore",
                "timeout_seconds": DONJON_MAX_TIMEOUT_SECONDS,
                "expect_k_effective": False,
            }
            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ), patch(
                "openmc2donjon.web.execution._run_rdonjon_bounded",
                side_effect=completed_run,
            ):
                first = client.post("/api/execute/donjon", json=request)
                self.assertEqual(first.status_code, 200, first.text)
                first_job = self._wait_for_job(client, first.json(), archive_root)
                second = client.post("/api/execute/donjon", json=request)
                self.assertEqual(second.status_code, 200, second.text)
                second_job = self._wait_for_job(client, second.json(), archive_root)

            self.assertNotEqual(first_job["job_id"], second_job["job_id"])
            for job in (first_job, second_job):
                self.assertEqual(job["status"], "completed")
                self.assertEqual(job["source_deck_path"], str(source_deck))
                self.assertEqual(job["source_deck_sha256"], source_sha256)
                self.assertEqual(job["deck_sha256"], source_sha256)
                self.assertEqual(job["project_root"], str(project_root))
                self.assertEqual(job["component_id"], "fullcore")
                self.assertRegex(str(job["declaration_sha256"]), r"^[a-f0-9]{64}$")
                self.assertEqual(job["project_manifest_path"], str(manifest_path))
                self.assertEqual(job["project_manifest_sha256"], manifest_sha256)
                run_directory = Path(job["run_directory"])
                self.assertEqual(run_directory.parent, archive_root)
                for filename in (
                    "request.json",
                    "project-manifest.snapshot.json",
                    "status.json",
                    "completion.json",
                    "artifacts.json",
                    "run.log",
                    "native_sph.x2m",
                    "native_sph.result",
                    "staged-inputs.json",
                    "access-receipt.json",
                    "runtime-output-manifest.json",
                ):
                    self.assertTrue((run_directory / filename).is_file(), filename)
                artifacts = json.loads(
                    (run_directory / "artifacts.json").read_text(encoding="utf-8")
                )
                self.assertEqual(artifacts["job_id"], job["job_id"])
                self.assertTrue(artifacts["artifacts"])
                self.assertTrue(
                    all(len(item["sha256"]) == 64 for item in artifacts["artifacts"])
                )
                self.assertFalse(
                    any(
                        item["relative_path"].startswith("staged-working-directory/")
                        for item in artifacts["artifacts"]
                    )
                )

            second_status_path = Path(second_job["status_path"])
            original_second_status = json.loads(
                second_status_path.read_text(encoding="utf-8")
            )
            forged_second_status = dict(original_second_status)
            forged_second_status["k_effective"] = 9.99
            forged_second_status["message"] = "forged terminal physics"
            second_status_path.write_text(
                json.dumps(forged_second_status), encoding="utf-8"
            )
            self.assertIsNone(_read_persisted_job(archive_root, second_job["job_id"]))
            second_status_path.write_text(
                json.dumps(original_second_status), encoding="utf-8"
            )

            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ):
                changed = client.post(
                    "/api/execute/donjon",
                    json={**request, "deck_text": "QUIT .\n"},
                )
            self.assertEqual(changed.status_code, 409)
            self.assertIn("exact source deck bytes", changed.json()["detail"])

            other_working = project_root / "other-case"
            other_working.mkdir()
            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ):
                mismatched_declaration = client.post(
                    "/api/execute/donjon",
                    json={**request, "working_directory": str(other_working)},
                )
            self.assertEqual(mismatched_declaration.status_code, 409)
            self.assertIn(
                "does not match project component",
                mismatched_declaration.json()["detail"],
            )

            interrupted_status_path = Path(first_job["status_path"])
            interrupted = json.loads(interrupted_status_path.read_text(encoding="utf-8"))
            interrupted["status"] = "running"
            interrupted["finished_at"] = None
            interrupted_status_path.write_text(json.dumps(interrupted), encoding="utf-8")

            recovered_client = TestClient(
                create_app(mock_mode=False, workspace_root=workspace)
            )
            listed = recovered_client.get(
                "/api/execution/jobs",
                params={"artifact_directory": str(archive_root)},
            )
            self.assertEqual(listed.status_code, 200, listed.text)
            self.assertEqual(len(listed.json()["jobs"]), 2)
            recovered = recovered_client.get(
                f"/api/execution/jobs/{first_job['job_id']}",
                params={"artifact_directory": str(archive_root)},
            )
            self.assertEqual(recovered.status_code, 200, recovered.text)
            self.assertEqual(recovered.json()["run_directory"], first_job["run_directory"])
            self.assertEqual(recovered.json()["status"], "failed")
            self.assertIn("interrupted", recovered.json()["message"])
            persisted = json.loads(interrupted_status_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "failed")
            recovered_manifest = json.loads(
                (Path(first_job["run_directory"]) / "artifacts.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(recovered_manifest["status"], "failed")

    def test_working_and_archive_directories_obey_workspace_scope(self) -> None:
        from openmc2donjon.web.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir, tempfile.TemporaryDirectory() as outside:
            workspace = Path(tmpdir).resolve()
            donjon_root = workspace / "dragon"
            _write_fake_donjon_installation(donjon_root)
            client = TestClient(
                create_app(mock_mode=False, workspace_root=workspace)
            )
            with patch.dict(
                os.environ,
                {"OPENMC2DONJON_ROOT": str(donjon_root)},
            ):
                response = client.post(
                    "/api/execute/donjon",
                    json={
                        "deck_text": "QUIT .",
                        "deck_filename": "case.x2m",
                        "donjon_root": str(donjon_root),
                        "artifact_directory": str(workspace / "runs"),
                        "working_directory": outside,
                    },
                )
            self.assertEqual(response.status_code, 403)

    @staticmethod
    def _wait_for_job(
        client: object,
        initial: dict[str, object],
        archive_root: Path,
    ) -> dict[str, object]:
        assert TestClient is not None
        assert isinstance(client, TestClient)
        job = initial
        for _ in range(200):
            if job["status"] in {"completed", "failed"}:
                return job
            time.sleep(0.01)
            response = client.get(
                f"/api/execution/jobs/{job['job_id']}",
                params={"artifact_directory": str(archive_root)},
            )
            if response.status_code == 200:
                job = response.json()
        raise AssertionError(f"DONJON job did not finish: {job}")


if __name__ == "__main__":
    unittest.main()
