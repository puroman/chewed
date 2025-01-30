import os
from chewed.config import chewedConfig
import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from chewed.cli import cli
from chewed._version import __version__
import ast
from pathlib import Path


def test_cli_local_package(tmp_path):
    runner = CliRunner()
    with patch("chewed.cli.analyze_package") as mock_analyze, patch(
        "pathlib.Path.exists"
    ) as mock_exists, patch("chewed.cli.generate_docs") as _:
        mock_exists.return_value = True
        mock_analyze.return_value = {
            "name": "testpkg",
            "package": "testpkg",
            "version": "1.0.0",
            "author": "Test Author",
            "license": "MIT",
            "python_requires": ">=3.8",
            "dependencies": ["requests>=2.25"],
            "modules": [
                {
                    "name": "testmod",
                    "path": "/fake/path/testmod.py",
                    "internal_deps": ["othermod"],
                    "imports": [
                        {"name": "sys", "type": "stdlib"},
                        {"name": "othermod", "type": "internal"},
                    ],
                    "type_info": {
                        "cross_references": {"MyType"},
                        "functions": {
                            "test_func": {
                                "args": ast.arguments(args=[], defaults=[]),
                                "returns": ast.Name(id="str"),
                            }
                        },
                        "classes": {
                            "TestClass": {
                                "methods": {
                                    "__init__": {
                                        "args": ast.arguments(args=[], defaults=[]),
                                        "returns": None,
                                    }
                                }
                            }
                        },
                    },
                    "examples": [
                        {"type": "doctest", "content": ">>> print('test')\n'test'"}
                    ],
                    "docstrings": {},
                    "ast": ast.Module(body=[]),
                    "layer": "application",
                    "role": "API interface",
                    "constants": {},
                }
            ],
            "config": chewedConfig(),
        }

        result = runner.invoke(
            cli,
            ["chew", str(tmp_path), "--local", "--output", str(tmp_path / "output")],
        )
        assert result.exit_code == 0
        assert (tmp_path / "output" / "index.md").exists()


def test_invalid_cli_arguments():
    runner = CliRunner()
    result = runner.invoke(cli, ["chew"])
    assert "Missing argument 'SOURCE'" in result.output
    assert "Error: Missing argument 'SOURCE'" in result.output


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Generate LLM-optimized documentation" in result.output


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    # Add cleanup for version file


def test_cli_missing_source_type(runner):
    result = runner.invoke(cli, ["chew", "testpkg", "-o", "/tmp"])
    assert "Error: Missing option '--local' or '--pypi'" in result.output


def test_cli_verbose_output(tmp_path):
    runner = CliRunner()
    mock_data = minimal_valid_package()
    mock_data["modules"][0]["examples"] = [{"code": "test = 123"}]

    with patch("chewed.cli.analyze_package", return_value=mock_data):
        result = runner.invoke(
            cli, ["chew", str(tmp_path), "--local", "-o", "docs", "-v"]
        )
        assert "📋 Found 1 usage examples" in result.output
        assert "⏱️  Documentation chewed" in result.output
        assert "📂 Output location" in result.output


def test_cli_exception_handling(tmp_path):
    runner = CliRunner()
    with patch("chewed.cli.analyze_package") as mock_analyze:
        mock_analyze.side_effect = ValueError("Test error")
        result = runner.invoke(cli, ["chew", str(tmp_path), "--local", "-o", "docs"])
        assert result.exit_code == 1
        assert "Error: Test error" in result.output


def minimal_valid_package():
    return {
        "package": "testpkg",
        "modules": [
            {
                "name": "testmod",
                "examples": [],
                "imports": [],
                "type_info": {},
                "docstrings": {},
                "ast": None,
            }
        ],
        "config": {},
    }


def test_cli_output_directory(tmp_path):
    runner = CliRunner()
    with patch("chewed.cli.analyze_package"), patch("chewed.cli.generate_docs"):
        result = runner.invoke(
            cli, ["chew", str(tmp_path), "--local", "-o", "custom_docs"]
        )
        assert result.exit_code == 0
        assert os.path.exists("custom_docs")


def test_cli_pypi_package():
    runner = CliRunner()
    with patch("chewed.metadata.get_pypi_metadata") as mock_pypi:
        mock_pypi.return_value = Path("/tmp/mock-package")
        result = runner.invoke(cli, ["chew", "requests", "--pypi", "-o", "docs"])
        assert result.exit_code == 0
        mock_pypi.assert_called_with("requests", None)
