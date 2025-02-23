import click
from pathlib import Path
from chewed.metadata import get_package_metadata, _download_pypi_package
from chewed.module_processor import process_modules, DocProcessor
from chewed.package_discovery import find_python_packages, get_package_name
from chewed.package_analysis import analyze_package, analyze_relationships
from chewed.doc_generation import generate_docs
from chewed.config import chewedConfig, load_config
import logging
import ast
import sys
from typing import List, Dict, Any, Optional, Union
import fnmatch

logger = logging.getLogger(__name__)


@click.command()
@click.argument("source", type=click.Path(exists=True))
@click.option(
    "--output", "-o", required=True, type=click.Path(), help="Output directory"
)
@click.option("--local/--pypi", default=True, help="Local package or PyPI package")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def cli(source: str, output: str, local: bool, verbose: bool) -> None:
    """Main entry point for package analysis"""
    logger.info("Loading configuration")
    config = load_config()
    logger.info("Analyzing package")
    package_info = analyze_package(
        source, is_local=local, config=config, verbose=verbose
    )
    logger.info("Generating documentation")
    generate_docs(package_info, Path(output), verbose=verbose)


def _find_imports(node: ast.AST, package_root: str) -> List[Dict[str, Any]]:
    logger.debug("Finding imports in AST")
    imports = []
    stdlib_modules = sys.stdlib_module_names

    for node in ast.walk(node):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                full_path = (
                    alias.name
                    if isinstance(node, ast.Import)
                    else f"{node.module}.{alias.name}"
                )
                first_part = full_path.split(".")[0]
                import_type = "stdlib" if first_part in stdlib_modules else "external"
                logger.debug(f"Found import: {full_path} of type: {import_type}")
                imports.append({"full_path": full_path, "type": import_type})
    logger.info(f"Total imports found: {len(imports)}")
    return imports


def process_package_modules(
    pkg_path: Path, config: chewedConfig
) -> List[Dict[str, Any]]:
    """Process all Python modules in a package"""
    logger.info(f"Processing package modules in: {pkg_path}")
    modules = []
    processed_files = set()  # Track processed files

    for py_file in pkg_path.glob("*.py"):
        logger.debug(f"Checking file: {py_file}")
        # Skip already processed files
        if str(py_file.resolve()) in processed_files:
            logger.debug(f"Skipping already processed file: {py_file}")
            continue

        # Skip excluded files
        if any(
            fnmatch.fnmatch(str(py_file), pattern)
            for pattern in config.exclude_patterns
        ):
            logger.debug(f"Skipping excluded file: {py_file}")
            continue

        # Skip empty __init__.py files
        if py_file.name == "__init__.py" and py_file.stat().st_size == 0:
            logger.debug(f"Skipping empty __init__.py file: {py_file}")
            continue

        try:
            logger.info(f"Processing module: {py_file}")
            module_info = process_modules([str(py_file)], config)
            if module_info:
                modules.extend(module_info)
                processed_files.add(str(py_file.resolve()))
                logger.info(f"Processed module: {py_file}")
            else:
                logger.error("No valid modules found")
                raise RuntimeError("No valid modules found")
        except SyntaxError:
            logger.warning(f"Syntax error in {py_file}")
            continue
        except Exception as e:
            logger.warning(f"Failed to process {py_file}: {str(e)}")
            continue

    logger.info(f"Total modules processed: {len(modules)}")
    return modules


def analyze_package(
    source: Union[str, Path],
    config: Optional[chewedConfig] = None,
    is_local: bool = True,
    verbose: bool = False
) -> dict:
    """Main package analysis entry point"""
    logger.info(f"Starting analysis for source: {source}")
    try:
        # Ensure source is a Path object and config exists
        source = Path(source).resolve()
        config = config or chewedConfig()
        
        if not source.exists():
            logger.error(f"Source path does not exist: {source}")
            raise ValueError(f"Source path does not exist: {source}")

        logger.info(f"Analyzing package at: {source}")
        
        try:
            # Process modules
            modules = process_modules(source, config)
            if not modules:
                logger.error("No valid modules found")
                raise RuntimeError("No valid modules found")
        except Exception as e:
            logger.error(f"Failed to process modules: {str(e)}")
            raise RuntimeError("No valid modules found")

        # Validate modules
        valid_modules = []
        for module in modules:
            if not isinstance(module, dict) or 'name' not in module:
                logger.warning(f"Skipping invalid module: {module}")
                continue
            valid_modules.append(module)

        if not valid_modules:
            logger.error("No valid modules found after validation")
            raise RuntimeError("No valid modules found")

        # Get package name and analyze relationships
        package_name = get_package_name(source)
        logger.info(f"Analyzing relationships for package: {package_name}")
        try:
            relationships = analyze_relationships(valid_modules, package_name)
        except Exception as e:
            logger.error(f"Failed to analyze relationships: {str(e)}")
            if verbose:
                logger.debug("Module data causing relationship analysis failure:", exc_info=True)
            relationships = {"dependency_graph": {}, "external_deps": []}
        
        logger.info("Package analysis completed successfully")
        return {
            "package": package_name,
            "path": str(source),
            "modules": valid_modules,
            "relationships": relationships,
            "metadata": get_package_metadata(source)
        }
        
    except (RuntimeError, ValueError):
        logger.error("Runtime or value error occurred during analysis")
        raise
    except Exception as e:
        logger.error(f"Package analysis failed: {str(e)}")
        raise RuntimeError("No valid modules found")


def _create_empty_package_info(path: Path) -> dict:
    """Create minimal package info for empty namespace packages"""
    logger.info(f"Creating empty package info for: {path}")
    return {
        "package": path.name,
        "path": str(path),
        "modules": [],
        "relationships": {"dependency_graph": {}, "external_deps": []},
        "metadata": {},
    }
