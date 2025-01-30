# Package analysis core logic
from pathlib import Path
from datetime import datetime
import logging
from typing import Any, Dict, Optional
from .module_processor import process_modules
from .metadata import get_package_metadata
from .relationships import analyze_relationships
from .ast_utils import extract_docstrings, extract_type_info
from .config import ChewdocConfig
from .utils import find_usage_examples, extract_constant_values, validate_ast
from .package_discovery import (
    find_python_packages,
    get_package_name,
    _is_namespace_package,
)
import ast
import tempfile

logger = logging.getLogger(__name__)


def analyze_package(
    source: str,
    version: Optional[str] = None,
    is_local: bool = True,
    config: ChewdocConfig = ChewdocConfig(),
    verbose: bool = False,
) -> dict[str, Any]:
    """Analyze Python package and extract documentation metadata."""
    path = (
        Path(source).resolve()
        if is_local
        else Path(tempfile.gettempdir()) / f"pypi_{source}"
    )
    if not is_local:
        path.mkdir(exist_ok=True)

    if verbose and (start := datetime.now()):
        logger.info(f"🚀 Starting analysis at {start:%H:%M:%S.%f}"[:-3])

    try:
        if verbose:
            logger.info("🔍 Fetching package metadata...")
        package_info = get_package_metadata(source, version, is_local)
        
        # Add fallback package name derivation
        package_name = package_info.get("package") or _derive_package_name(path)
        package_info["package"] = package_name
        package_info.setdefault("python_requires", ">=3.6")
        package_info.setdefault("license", "Proprietary")

        if verbose:
            logger.info(f"📦 Processing package: {package_name}")
            logger.info("🧠 Processing module ASTs...")

        package_info["modules"] = []
        module_paths = process_modules(path, config)

        if not module_paths:
            raise ValueError("No valid modules found in package")

        for module_data in module_paths:
            module_path = Path(module_data["path"])
            if verbose:
                logger.info(f"🔄 Processing: {module_data['name']}")

            with open(module_path, "r") as f:
                module_ast = ast.parse(f.read())

            validate_ast(module_ast)
            module_info = {
                "name": module_data["name"],
                "path": str(module_path),
                "ast": module_ast,
                "docstrings": extract_docstrings(module_ast),
                "type_info": extract_type_info(module_ast, config),
                "constants": {
                    name: {"value": value}
                    for name, value in extract_constant_values(module_ast)
                    if name.isupper()
                },
                "examples": find_usage_examples(module_ast),
                "imports": module_data["imports"],
                "internal_deps": module_data.get("internal_deps", []),
            }
            package_info["modules"].append(module_info)

        package_info["relationships"] = analyze_relationships(
            package_info["modules"], package_name
        )

        if verbose:
            duration = datetime.now() - start
            logger.info(f"🏁 Analysis completed in {duration.total_seconds():.3f}s")
            logger.info(f"📊 Processed {len(package_info['modules'])} modules")

        return package_info
    except SyntaxError as e:
        raise ValueError(f"Syntax error in {path}: {e}") from e
    except Exception as e:
        logger.error(f"Package analysis failed: {str(e)}")
        raise RuntimeError(f"Package analysis failed: {str(e)}") from e

def _derive_package_name(package_path: Path) -> str:
    """Fallback package name derivation from path"""
    path_parts = package_path.resolve().parts
    for part in reversed(path_parts):
        if part in ("src", "site-packages", "dist-packages"):
            continue
        if "-" in part:  # Handle versioned directories like my-pkg-1.2.3
            return part.split("-")[0]
        return part
    return "unknown-package"
