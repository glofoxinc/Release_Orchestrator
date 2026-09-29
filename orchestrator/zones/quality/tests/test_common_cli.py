"""Tests for the shared CLI scaffolding."""
from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from common import cli


class TestAddCommonArgs:
    def test_parses_verbose_flag(self):
        parser = argparse.ArgumentParser()
        cli.add_common_args(parser)
        args = parser.parse_args(["-vv"])
        assert args.verbose == 2

    def test_parses_quiet_flag(self):
        parser = argparse.ArgumentParser()
        cli.add_common_args(parser)
        args = parser.parse_args(["--quiet"])
        assert args.quiet is True

    def test_json_output_flag(self):
        parser = argparse.ArgumentParser()
        cli.add_common_args(parser)
        args = parser.parse_args(["--json"])
        assert args.json_output is True

    def test_dry_run_default_false(self):
        parser = argparse.ArgumentParser()
        cli.add_common_args(parser)
        args = parser.parse_args([])
        assert args.dry_run is False

    def test_config_path_parsed(self, tmp_path):
        parser = argparse.ArgumentParser()
        cli.add_common_args(parser)
        args = parser.parse_args(["--config", str(tmp_path / "c.yml")])
        assert isinstance(args.config, Path)


class TestLoadConfigFile:
    def test_yaml_file(self, tmp_path):
        p = tmp_path / "c.yml"
        p.write_text("a: 1\nb:\n  c: 2\n", encoding="utf-8")
        data = cli.load_config_file(p)
        assert data == {"a": 1, "b": {"c": 2}}

    def test_json_file(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text('{"k": "v"}', encoding="utf-8")
        assert cli.load_config_file(p) == {"k": "v"}

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            cli.load_config_file(tmp_path / "nope.yml")

    def test_non_mapping_raises(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text('[1, 2, 3]', encoding="utf-8")
        with pytest.raises(ValueError):
            cli.load_config_file(p)

    def test_empty_yaml_returns_dict(self, tmp_path):
        p = tmp_path / "c.yml"
        p.write_text("", encoding="utf-8")
        assert cli.load_config_file(p) == {}


class TestPrintJson:
    def test_prints_sorted_keys(self):
        buf = io.StringIO()
        cli.print_json({"b": 1, "a": 2}, stream=buf)
        text = buf.getvalue()
        assert text.index('"a"') < text.index('"b"')

    def test_handles_non_serialisable_via_default(self):
        buf = io.StringIO()
        cli.print_json({"p": Path("x")}, stream=buf)
        assert "x" in buf.getvalue()

    def test_emits_trailing_newline(self):
        buf = io.StringIO()
        cli.print_json({"k": "v"}, stream=buf)
        assert buf.getvalue().endswith("\n")


class TestDispatch:
    def test_dispatches_to_correct_handler(self):
        def configure(sp):
            sp.add_argument("--name")

        def run_hello(args):
            return 0 if args.name == "abc" else 1

        parser, handlers = cli.build_subparsers(
            "tool", "Tool", [("hello", "Say hi", configure, run_hello)]
        )
        assert cli.dispatch(parser, handlers, ["hello", "--name", "abc"]) == 0

    def test_file_not_found_returns_config_exit(self):
        def run(args):
            raise FileNotFoundError("missing")

        parser, handlers = cli.build_subparsers(
            "tool", "Tool", [("x", "X", lambda sp: None, run)]
        )
        assert cli.dispatch(parser, handlers, ["x"]) == cli.EXIT_CONFIG

    def test_validation_error_returns_validation_exit(self):
        def run(args):
            raise ValueError("bad")

        parser, handlers = cli.build_subparsers(
            "tool", "Tool", [("x", "X", lambda sp: None, run)]
        )
        assert cli.dispatch(parser, handlers, ["x"]) == cli.EXIT_VALIDATION

    def test_unexpected_error_returns_unexpected_exit(self):
        def run(args):
            raise RuntimeError("oops")

        parser, handlers = cli.build_subparsers(
            "tool", "Tool", [("x", "X", lambda sp: None, run)]
        )
        assert cli.dispatch(parser, handlers, ["x"]) == cli.EXIT_UNEXPECTED


class TestLoggingSetup:
    def test_quiet_sets_warning_level(self):
        ns = argparse.Namespace(quiet=True, verbose=0)
        cli.setup_cli_logging(ns)
        import logging
        assert logging.getLogger().level == logging.WARNING

    def test_verbose_sets_debug(self):
        ns = argparse.Namespace(quiet=False, verbose=2)
        cli.setup_cli_logging(ns)
        import logging
        assert logging.getLogger().level == logging.DEBUG
