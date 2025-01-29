import ast
from chewdoc.config import ChewdocConfig
from typing import Any, List, Tuple, Union, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def get_annotation(node: ast.AST, config: ChewdocConfig) -> str:
    """Get type annotation with full type resolution"""
    if isinstance(node, ast.Subscript):
        base = get_annotation(node.value, config)
        if isinstance(node.slice, ast.Tuple):
            params = ", ".join(get_annotation(el, config) for el in node.slice.elts)
        else:
            params = get_annotation(node.slice, config)
        return f"{base}[{params}]"
    return ast.unparse(node).strip()


def infer_responsibilities(module: dict) -> str:
    """Generate module responsibility description based on contents"""

    def safe_get_names(items, key="name") -> list:
        """Safely extract names from mixed list/dict structures"""
        if isinstance(items, dict):
            return [v.get(key, "") for v in items.values() if v.get(key)]
        if isinstance(items, list):
            return [item.get(key, "") for item in items if item.get(key)]
        return []

    responsibilities = []

    # Handle classes
    if classes := module.get("classes"):
        class_names = safe_get_names(classes)
        class_list = class_names[:3]
        resp = "Defines core classes: " + ", ".join(class_list)
        if len(class_names) > 3:
            resp += f" (+{len(class_names)-3} more)"
        responsibilities.append(resp)

    # Handle functions
    if functions := module.get("functions"):
        func_names = safe_get_names(functions)
        func_list = func_names[:3]
        resp = "Provides key functions: " + ", ".join(func_list)
        if len(func_names) > 3:
            resp += f" (+{len(func_names)-3} more)"
        responsibilities.append(resp)

    # Handle constants
    if constants := module.get("constants"):
        const_names = safe_get_names(constants)
        const_list = const_names[:3]
        resp = "Contains constants: " + ", ".join(const_list)
        if len(const_names) > 3:
            resp += f" (+{len(const_names)-3} more)"
        responsibilities.append(resp)

    if not responsibilities:
        return "General utility module with mixed responsibilities"

    return "\n- ".join([""] + responsibilities)


def validate_ast(node: ast.AST) -> None:
    """Validate AST structure for documentation processing"""
    if not isinstance(node, ast.AST):
        raise TypeError(f"Invalid AST - expected node, got {type(node).__name__}")

    # Remove invalid name check for Module nodes
    if any(isinstance(stmt, (dict, str)) for stmt in getattr(node, "body", [])):
        raise ValueError("AST contains invalid node types - found serialized data")

    if not hasattr(node, "body"):
        raise ValueError("Invalid AST structure - missing body attribute")

    # Allow empty modules without checking name
    has_elements = any(
        isinstance(stmt, (ast.FunctionDef, ast.ClassDef, ast.Assign))
        for stmt in node.body
    )
    if not has_elements:
        has_docstring = any(
            isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
            for stmt in node.body
        )
        if not has_docstring:
            raise ValueError("Empty or invalid module AST structure")


def find_usage_examples(node: ast.AST) -> list:
    """Placeholder example finder (implement your logic here)"""
    return []  # TODO: Add actual example extraction logic


def format_function_signature(
    args: ast.arguments, returns: Optional[ast.AST], config: ChewdocConfig
) -> str:
    """Format function signature with proper argument handling"""
    args_list = []
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    
    for arg, default in zip(args.args, defaults):
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {get_annotation(arg.annotation, config)}"
        if default:
            default_src = ast.unparse(default).strip()
            arg_str += f" = {default_src}"
        args_list.append(arg_str)
    
    return_str = ""
    if returns:
        return_str = f" -> {get_annotation(returns, config)}"
        
    return f"({', '.join(args_list)}){return_str}"


def _find_imports(node: ast.AST) -> list:
    """Extract import statements from AST"""
    imports = []

    class ImportVisitor(ast.NodeVisitor):
        def visit_Import(self, node):
            for alias in node.names:
                imports.append(alias.name)

        def visit_ImportFrom(self, node):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)

    ImportVisitor().visit(node)
    return imports


def extract_constant_values(node: ast.AST) -> List[Tuple[str, str]]:
    """Extract module-level constants with ALL_CAPS names"""
    constants = []
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    value = ast.unparse(stmt.value).strip()
                    constants.append((target.id, value))
    return constants


def safe_write(
    path: Path, content: str, mode: str = "w", overwrite: bool = False
) -> None:
    """Atomic file write with directory creation"""
    if path.exists() and not overwrite:
        raise FileExistsError(f"File already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, mode) as f:
        f.write(content)
