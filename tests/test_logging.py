from __future__ import annotations

import contextlib
import io
import logging
import unittest

from openmc2donjon._logging import (
    add_cli_logging_arguments,
    configure_cli_logging,
    get_logger,
)


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


if __name__ == "__main__":
    logging.basicConfig()
    unittest.main()
