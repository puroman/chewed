from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from chewdoc.utils import get_annotation, infer_responsibilities, format_function_signature
from chewdoc.config import ChewdocConfig

import ast
import click
import fnmatch
import re

from chewdoc.constants import META_TEMPLATE, MODULE_TEMPLATE


class MystWriter:
    def __init__(self, config: Optional[ChewdocConfig] = None):
        self.config = config or ChewdocConfig()
        self.package_data = {}
        self.config.max_example_lines = getattr(self.config, 'max_example_lines', 15)  # Add default

    def generate(self, package_data: dict, output_path: Path, verbose: bool = False) -> None:
        """Generate structured MyST documentation with separate files"""
        if not package_data or "modules" not in package_data:
            raise ValueError("Invalid package data")
        
        # Ensure required fields with safe defaults
        package_data.setdefault("name", "Unknown Package")
        package_data.setdefault("package", package_data["name"])
        package_data.setdefault("version", "0.0.0")
        package_data.setdefault("author", "Unknown")
        package_data.setdefault("license", "Not specified")
        package_data.setdefault("python_requires", ">=3.6")
        
        # Handle directory output path
        output_dir = output_path if output_path.is_dir() else output_path.parent
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Store package data and generate content
        self.package_data = package_data
        
        # Generate module files
        for module in package_data["modules"]:
            module_file = output_dir / f"{module['name']}.md"
            content = self._format_module(module)
            module_file.write_text(content)

        # Generate index file
        index_content = self._format_package_index(package_data)
        (output_dir / "index.md").write_text(index_content)

    def _format_package_index(self, package_data: Dict[str, Any]) -> str:
        """Generate main package index with module links"""
        content = [
            f"# {package_data['name']} Documentation\n",
            "## Package Overview",
            self._format_metadata(package_data),
            "\n## Modules\n"
        ]
        
        for module in package_data["modules"]:
            module.setdefault("internal_deps", [])
            content.append(f"## {module['name']}\n")
            content.append(self._format_module_content(module))
            
        return "\n".join(content)

    def _format_module_content(self, module: dict) -> str:
        """Format module docs with package context"""
        return MODULE_TEMPLATE.format(
            name=module["name"],
            package=self.package_data["package"],
            role_section=self._format_role(module),
            layer_section=self._format_architecture_layer(module),
            imports_section=self._format_imports(module.get("imports", []), self.package_data["package"]),
            description=self._get_module_description(module),
            dependencies=self._format_dependencies(module["internal_deps"]),
            usage_examples=self._format_usage_examples(
                module.get("examples", []), 
                config=self.config
            ),
            api_reference=self._format_api_reference(module.get("type_info", {}))
        )

    def _format_imports(self, imports: list, package_name: str) -> str:
        """Format imports using actual package context"""
        categorized = {"stdlib": [], "internal": [], "external": []}

        for imp in imports:
            # Handle test data format
            if isinstance(imp, str):
                imp = {"name": imp, "full_path": imp, "source": ""}
            
            entry = f"`{imp['name']}`"
            if imp.get("source"):
                entry += f" from `{imp['source']}`"

            if imp["full_path"].startswith(f"{package_name}."):
                categorized["internal"].append(f"- [[{imp['full_path']}|{entry}]]")
            elif "." not in imp["full_path"]:
                categorized["stdlib"].append(f"- {entry}")
            else:
                categorized["external"].append(f"- {entry}")

        sections = []
        if categorized["stdlib"]:
            sections.append("### Standard Library\n" + "\n".join(sorted(categorized["stdlib"])))
        if categorized["internal"]:
            sections.append("### Internal Dependencies\n" + "\n".join(sorted(categorized["internal"])))
        if categorized["external"]:
            sections.append("### External Dependencies\n" + "\n".join(sorted(categorized["external"])))
        
        return "\n\n".join(sections) if sections else "No imports"

    def _format_code_structure(self, ast_data: ast.Module) -> str:
        """Visualize code structure hierarchy"""
        structure = []

        if not isinstance(ast_data, ast.Module):
            return ""

        for item in ast_data.body:
            if isinstance(item, ast.ClassDef):
                class_entry = f"### Class: {item.name}"
                methods = [
                    f"  - Method: {subitem.name}"
                    for subitem in item.body
                    if isinstance(subitem, ast.FunctionDef)
                ]
                if methods:
                    class_entry += "\n" + "\n".join(methods)
                structure.append(class_entry)
            elif isinstance(item, ast.FunctionDef):
                structure.append(f"- Function: {item.name}")

        return "\n".join(structure)

    def _format_api_reference(self, types: Dict[str, Any]) -> str:
        """Format functions and classes with cross-references and docstrings"""
        sections = []
        
        # Handle classes and their methods
        for cls_name, cls_info in types.get("classes", {}).items():
            class_doc = [
                f"## {cls_name}",
                f"[[{cls_name}]]",
                f"**Description**: {cls_info.get('doc', 'No class documentation')}",
            ]
            
            if cls_info.get("methods"):
                class_doc.append("\n### Methods")
                for method, details in cls_info["methods"].items():
                    signature = self._format_function_signature(details)
                    class_doc.append(f"- `{method}{signature}`")
            
            sections.append("\n".join(class_doc))

        # Handle functions
        for func_name, func_info in types.get("functions", {}).items():
            signature = self._format_function_signature(func_info)
            func_doc = [
                f"## `{func_name}{signature}`",
                f"**Description**: {func_info.get('doc', 'No function documentation')}",
            ]
            sections.append("\n".join(func_doc))
        
        return "\n\n".join(sections) if sections else ""

    def _format_metadata(self, package_data: Dict[str, Any]) -> str:
        """Format package metadata with fallback values"""
        return META_TEMPLATE.format(
            name=package_data.get("name", "Unnamed Package"),
            version=package_data.get("version", "0.0.0"),
            author=package_data.get("author", "Unknown Author"),
            license=package_data.get("license", "Not specified"),
            dependencies=", ".join(package_data.get("dependencies", ["None"])),
            python_requires=package_data.get("python_requires", "Not specified")
        )

    def _format_role(self, module: dict) -> str:
        """Format module role description"""
        if "role" in module:
            return f"- **Role**: {module['role']}"
        return "- **Role**: General purpose module"

    def _format_architecture_layer(self, module: dict) -> str:
        """Format module architecture layer information"""
        if "layer" in module:
            return f"- **Architecture Layer**: {module['layer']}"
        return "- **Architecture Layer**: Not specified"

    def _format_dependencies(self, dependencies: list) -> str:
        """Format module dependencies as Mermaid graph"""
        if not dependencies:
            return "No internal dependencies"
        
        connections = []
        seen = set()
        
        for dep in dependencies:
            clean_dep = self._clean_node_name(dep)
            if clean_dep not in seen:
                connections.append(f"{clean_dep}[{dep}]")
                seen.add(clean_dep)
        
        return "\n    ".join(connections[:10])  # Show first 10 deps

    def _clean_node_name(self, name: str) -> str:
        """Sanitize node names for Mermaid compatibility"""
        return name.replace(".", "_").replace("-", "_")

    def _format_modules(self, modules: list) -> str:
        """Format module list for index page"""
        return "\n".join(f"- [[{m['name']}]]" for m in modules)

    def _format_function_signature(self, func_info: dict) -> str:
        """Format function signature with type cross-references"""
        # Handle both raw AST and serialized formats
        args_node = func_info.get('args')
        returns_node = func_info.get('returns')
        
        # Add defensive checks for node types
        if isinstance(args_node, dict):  # Handle serialized format
            try:
                args_node = ast.arguments(
                    posonlyargs=[ast.arg(arg=a['arg']) for a in args_node.get('posonlyargs', [])],
                    args=[ast.arg(arg=a['arg']) for a in args_node.get('args', [])],
                    vararg=ast.arg(arg=args_node['vararg']['arg']) if args_node.get('vararg') else None,
                    kwonlyargs=[ast.arg(arg=a['arg']) for a in args_node.get('kwonlyargs', [])],
                    kw_defaults=args_node.get('kw_defaults', []),
                    kwarg=ast.arg(arg=args_node['kwarg']['arg']) if args_node.get('kwarg') else None,
                    defaults=args_node.get('defaults', [])
                )
            except KeyError as e:
                raise ValueError(f"Malformed arguments node: {e}") from e
            
        if isinstance(returns_node, dict):  # Handle serialized format
            returns_node = ast.parse(returns_node['value']).body[0].value if returns_node else None
        
        # Handle type constants directly
        if isinstance(returns_node, ast.Constant) and isinstance(returns_node.value, type):
            returns_node = ast.Name(id=returns_node.value.__name__)
        
        return format_function_signature(
            args=args_node,
            returns=returns_node,
            config=self.config
        )

    def _format_usage_examples(self, examples: list, config: ChewdocConfig) -> str:
        """Format usage examples section"""
        if not examples:
            return "No usage examples found"
            
        output = ["## Usage Examples"]
        for ex in examples:
            if ex["type"] == "doctest":
                output.append(f"```python\n{ex['content']}\n```")
            elif ex["type"] == "pytest":
                output.append(f"**Test case**: `{ex['name']}`\n```python\n{ex['content']}\n```")
        
        return "\n\n".join(output)

    def extract_docstrings(self, node: ast.AST) -> Dict[str, str]:
        """Enhanced docstring extraction with context tracking"""
        docs = {}
        for child in ast.walk(node):
            if isinstance(child, (ast.Module, ast.ClassDef, ast.FunctionDef)):
                try:
                    docstring = ast.get_docstring(child, clean=True)
                    if docstring:
                        key = f"{type(child).__name__}:{getattr(child, 'name', 'module')}"
                        docs[key] = {
                            "doc": docstring,
                            "line": child.lineno,
                            "context": self._get_code_context(child),
                        }
                except Exception as e:
                    continue
        return docs

    def _get_module_description(self, module: dict) -> str:
        """Extract module description from docstrings"""
        if "docstrings" in module and "module:1" in module["docstrings"]:
            return module["docstrings"]["module:1"]
        return infer_responsibilities(module)

    def _format_module(self, module: dict) -> str:
        """Format a single module's documentation"""
        content = [
            f"# {module['name']}\n",
            f"```{{module}} {module['name']}\n"
        ]
        
        if module.get('docstrings'):
            content.append(f"\n{module['docstrings'].get('module', '')}\n")
        
        if module.get('examples'):
            content.append("\n## Examples\n")
            for example in module['examples']:
                content.append(f"```python\n{example['content']}\n```\n")
        
        # Add API reference section
        if module.get('type_info'):
            content.append("\n## API Reference\n")
            content.append(self._format_api_reference(module['type_info']))
        
        content.append("\n```\n")
        return "\n".join(content)

    def _format_classes(self, classes: dict) -> str:
        output = []
        for class_name, class_info in classes.items():
            output.append(f"## {class_name}\n")
            if class_info.get('docstring'):
                output.append(f"\n{class_info['docstring']}\n")
            
            # Format methods
            if class_info.get('methods'):
                output.append("\n### Methods\n")
                for method_name, method_info in class_info['methods'].items():
                    output.append(f"#### {method_name}{self._format_function_signature(method_info)}\n")
                    if method_info.get('docstring'):
                        output.append(f"\n{method_info['docstring']}\n")
        return "\n".join(output)
