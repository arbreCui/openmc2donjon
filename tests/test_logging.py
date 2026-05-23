from __future__ import annotations

import contextlib
import io
import logging
import unittest

from openmc2donjon._logging import (
    CLI_LOGGING_VALUE_FLAGS,
    add_cli_logging_arguments,
    configure_cli_logging,
    get_logger,
    is_cli_logging_flag,
)
from openmc2donjon.cli import (
    _is_command_invocation,
    build_command_parser,
    build_parser as build_convert_parser,
)
from openmc2donjon.export_cli import build_parser as build_export_parser
from openmc2donjon.from_openmc_cli import build_parser as build_from_openmc_parser


class LoggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        configure_cli_logging()

    def test_default_level_is_warning_and_uses_stderr(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            configure_cli_logging()
            logger = get_logger("tests")
            logger.info("hidden")
            logger.warning("visible")

        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("hidden", stderr.getvalue())
        self.assertIn("WARNING: visible", stderr.getvalue())

    def test_verbose_levels_map_to_info_and_debug(self) -> None:
        info_stderr = io.StringIO()
        with contextlib.redirect_stderr(info_stderr):
            configure_cli_logging(verbose=1)
            logger = get_logger("tests")
            logger.debug("hidden")
            logger.info("info")

        debug_stderr = io.StringIO()
        with contextlib.redirect_stderr(debug_stderr):
            configure_cli_logging(verbose=2)
            get_logger("tests").debug("debug")

        self.assertNotIn("hidden", info_stderr.getvalue())
        self.assertIn("INFO: info", info_stderr.getvalue())
        self.assertIn("DEBUG: debug", debug_stderr.getvalue())

    def test_quiet_maps_to_error(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            configure_cli_logging(quiet=True)
            logger = get_logger("tests")
            logger.warning("hidden")
            logger.error("error")

        self.assertNotIn("hidden", stderr.getvalue())
        self.assertIn("ERROR: error", stderr.getvalue())

    def test_explicit_log_level_overrides_verbose_and_quiet(self) -> None:
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            configure_cli_logging(verbose=2, quiet=True, log_level="WARNING")
            logger = get_logger("tests")
            logger.info("hidden")
            logger.warning("warning")

        self.assertNotIn("hidden", stderr.getvalue())
        self.assertIn("WARNING: warning", stderr.getvalue())

    def test_reconfigure_replaces_cli_handler(self) -> None:
        first = io.StringIO()
        second = io.StringIO()

        with contextlib.redirect_stderr(first):
            configure_cli_logging(verbose=1)
        with contextlib.redirect_stderr(second):
            configure_cli_logging(verbose=1)
            get_logger("tests").info("once")

        self.assertEqual(first.getvalue(), "")
        self.assertEqual(second.getvalue().count("INFO: once"), 1)

    def test_invalid_log_level_raises(self) -> None:
        with self.assertRaises(ValueError):
            configure_cli_logging(log_level="chatty")

    def test_parser_helper_adds_standard_flags(self) -> None:
        import argparse

        parser = argparse.ArgumentParser()
        add_cli_logging_arguments(parser)
        args = parser.parse_args(["-vv", "-q", "--log-level", "warning"])

        self.assertEqual(args.verbose, 2)
        self.assertTrue(args.quiet)
        self.assertEqual(args.log_level, "WARNING")

    def test_entrypoint_parsers_accept_logging_flags(self) -> None:
        convert_args = build_convert_parser().parse_args(
            ["-vv", "--quiet", "--log-level", "info", "input.h5"]
        )
        from_openmc_args = build_from_openmc_parser().parse_args(
            ["--recipe", "recipe.py", "-v"]
        )
        export_args = build_export_parser().parse_args(["-q", "library.pkl"])

        self.assertEqual(convert_args.verbose, 2)
        self.assertTrue(convert_args.quiet)
        self.assertEqual(convert_args.log_level, "INFO")
        self.assertEqual(from_openmc_args.verbose, 1)
        self.assertTrue(export_args.quiet)

    def test_openmc2donjon_command_parser_accepts_logging_flags(self) -> None:
        before = build_command_parser().parse_args(["-v", "doctor"])
        after = build_command_parser().parse_args(["doctor", "-vv"])
        explicit = build_command_parser().parse_args(["doctor", "--log-level", "debug"])

        self.assertEqual(before.verbose, 1)
        self.assertEqual(after.verbose, 2)
        self.assertEqual(explicit.log_level, "DEBUG")

    def test_openmc2donjon_dispatch_detects_logging_flags_before_command(self) -> None:
        self.assertTrue(_is_command_invocation(["-v", "check", "input.h5"]))
        self.assertTrue(_is_command_invocation(["--log-level", "INFO", "doctor"]))
        self.assertFalse(_is_command_invocation(["-v", "input.h5"]))

    def test_openmc2donjon_dispatch_skips_vq_clusters(self) -> None:
        self.assertTrue(_is_command_invocation(["-vq", "check", "input.h5"]))
        self.assertTrue(_is_command_invocation(["-qv", "doctor"]))
        self.assertTrue(_is_command_invocation(["-vvq", "check", "input.h5"]))

    def test_is_cli_logging_flag_recognizes_supported_forms(self) -> None:
        self.assertTrue(is_cli_logging_flag("-v"))
        self.assertTrue(is_cli_logging_flag("-vv"))
        self.assertTrue(is_cli_logging_flag("-vvv"))
        self.assertTrue(is_cli_logging_flag("-q"))
        self.assertTrue(is_cli_logging_flag("--verbose"))
        self.assertTrue(is_cli_logging_flag("--quiet"))
        self.assertTrue(is_cli_logging_flag("--log-level"))
        self.assertTrue(is_cli_logging_flag("--log-level=INFO"))

    def test_is_cli_logging_flag_recognizes_vq_clusters(self) -> None:
        # argparse accepts ``-vq``, ``-qv``, ``-vvq`` etc. as short-flag
        # clusters; the dispatcher must treat them as logging flags too.
        self.assertTrue(is_cli_logging_flag("-vq"))
        self.assertTrue(is_cli_logging_flag("-qv"))
        self.assertTrue(is_cli_logging_flag("-vvq"))
        self.assertTrue(is_cli_logging_flag("-qvv"))

    def test_is_cli_logging_flag_rejects_non_logging_tokens(self) -> None:
        self.assertFalse(is_cli_logging_flag("check"))
        self.assertFalse(is_cli_logging_flag("input.h5"))
        self.assertFalse(is_cli_logging_flag("--format"))
        self.assertFalse(is_cli_logging_flag("-"))
        self.assertFalse(is_cli_logging_flag(""))
        # Clusters that include a non-logging short flag must not be skipped.
        self.assertFalse(is_cli_logging_flag("-vx"))
        self.assertFalse(is_cli_logging_flag("-qx"))

    def test_cli_logging_value_flags_includes_log_level(self) -> None:
        self.assertIn("--log-level", CLI_LOGGING_VALUE_FLAGS)


if __name__ == "__main__":
    logging.basicConfig()
    unittest.main()
