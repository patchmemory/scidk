"""
scidk/schema/generate_stubs.py

Generates Python stub classes from Label YAML definitions.

Run with:
    python -m scidk.schema.generate_stubs
    # or
    scidk labels generate-stubs

Generated files are written to scidk/schema/generated/ and imported
by scidk/schema/__init__.py.

Generated classes:
  - Extend SciDKNode
  - Have typed attributes for tab-complete and type checking
  - Have docstrings showing sanitization rules as inline warnings
  - Are NOT meant to be edited manually (they are overwritten on regeneration)

The generated __init__.py re-exports all classes so modules can do:
    from scidk.schema import Sample, ImagingDataset, Study
"""

from __future__ import annotations
import os
import sys
from typing import Dict, List

from scidk.schema.registry import LabelRegistry, LabelDefinition, PropertyDefinition


# Python type mapping from Label YAML types
PYTHON_TYPES = {
    'string': 'str',
    'integer': 'int',
    'float': 'float',
    'boolean': 'bool',
    'list': 'list',
}

SANITIZE_DISPLAY = {
    'none': None,
    'redact': '⚠️  REDACTED — never written to graph',
    'hash': 'one-way hashed before storage',
    'bin': 'binned to range before storage e.g. 45 → "40-50 years"',
    'encode': 'encoded to controlled vocabulary before storage',
    'truncate': 'rounded to reduce precision before storage',
}


def generate_stub_class(label_def: LabelDefinition) -> str:
    """Generate Python source code for a single Label stub class."""
    lines = []

    # Class header
    lines.append(f"class {label_def.neo4j_label}(SciDKNode):")

    # Docstring
    lines.append('    """')
    if label_def.description:
        # Wrap description at 80 chars
        desc_lines = _wrap_text(label_def.description.strip(), 76)
        for dl in desc_lines:
            lines.append(f"    {dl}")
        lines.append("")

    # Properties section
    lines.append("    Properties:")
    for prop_name, prop_def in label_def.properties.items():
        py_type = PYTHON_TYPES.get(prop_def.type, 'Any')
        flags = []
        if prop_def.required:
            flags.append("required")
        if prop_def.key:
            flags.append("key")
        flag_str = f", {', '.join(flags)}" if flags else ""

        sanitize_note = SANITIZE_DISPLAY.get(prop_def.sanitize)
        if prop_def.sanitize == 'bin' and prop_def.sanitize_config:
            bin_size = prop_def.sanitize_config.get('bin_size', '?')
            units = prop_def.sanitize_config.get('units', '')
            sanitize_note = f"binned to {bin_size}-unit ranges" + (f" ({units})" if units else "")
        elif prop_def.sanitize == 'encode' and prop_def.sanitize_config:
            vocab = prop_def.sanitize_config.get('vocabulary', '?')
            sanitize_note = f"encoded to {vocab} vocabulary"

        desc = prop_def.description or ""
        if sanitize_note:
            desc = f"{desc} — {sanitize_note}".lstrip(" — ")

        lines.append(f"        {prop_name} ({py_type}{flag_str}): {desc}")

    # Relationships section
    if label_def.relationships:
        lines.append("")
        lines.append("    Relationships:")
        for rel in label_def.relationships:
            if rel.direction == 'incoming':
                lines.append(f"        ← {rel.type} ← {rel.to_label}")
            else:
                lines.append(f"        {rel.type} → {rel.to_label}")

    # Example
    key_prop = label_def.key_property
    if key_prop:
        key_type = label_def.properties[key_prop].type if key_prop in label_def.properties else 'string'
        example_val = '"example_id"' if key_type == 'string' else '1'
        lines.append("")
        lines.append("    Example:")
        lines.append(f"        node = {label_def.neo4j_label}({key_prop}={example_val})")
        # Show sanitization example if any properties are sanitized
        sanitized_props = [
            (name, prop) for name, prop in label_def.properties.items()
            if prop.sanitize not in ('none',) and not prop.key
        ]
        if sanitized_props:
            ex_name, ex_prop = sanitized_props[0]
            lines.append(f"        # {ex_name} is {SANITIZE_DISPLAY.get(ex_prop.sanitize, ex_prop.sanitize)}")

    lines.append('    """')
    lines.append("")

    # Class metadata attributes
    lines.append(f"    _label = {label_def.neo4j_label!r}")
    lines.append(f"    _key_property = {label_def.key_property!r}")

    # Sanitization rules dict
    rules = label_def.sanitization_rules
    if rules:
        lines.append(f"    _sanitization = {rules!r}")
    else:
        lines.append("    _sanitization = {}")

    # Allowed values dict
    allowed = {
        name: prop.allowed_values
        for name, prop in label_def.properties.items()
        if prop.allowed_values
    }
    if allowed:
        lines.append(f"    _allowed_values = {allowed!r}")
    else:
        lines.append("    _allowed_values = {}")

    # Required properties list
    required = label_def.required_properties
    lines.append(f"    _required = {required!r}")
    lines.append("")

    # Typed attribute declarations (for tab-complete and type checking)
    for prop_name, prop_def in label_def.properties.items():
        py_type = PYTHON_TYPES.get(prop_def.type, 'Any')
        sanitize_note = SANITIZE_DISPLAY.get(prop_def.sanitize)

        comment_parts = []
        if prop_def.required:
            comment_parts.append("required")
        if prop_def.key:
            comment_parts.append("unique key")
        if sanitize_note:
            comment_parts.append(f"sanitize: {prop_def.sanitize}")
        if prop_def.allowed_values:
            shown = prop_def.allowed_values[:3]
            more = f"...+{len(prop_def.allowed_values)-3}" if len(prop_def.allowed_values) > 3 else ""
            comment_parts.append(f"allowed: [{', '.join(repr(v) for v in shown)}{more}]")

        comment = f"  # {', '.join(comment_parts)}" if comment_parts else ""

        if prop_def.required and prop_def.key:
            lines.append(f"    {prop_name}: {py_type}{comment}")
        else:
            lines.append(f"    {prop_name}: Optional[{py_type}] = None{comment}")

    lines.append("")

    return "\n".join(lines)


def generate_all_stubs(output_dir: str) -> List[str]:
    """
    Generate stub classes for all registered Labels.

    Args:
        output_dir: Directory to write generated files to.

    Returns:
        List of generated class names.
    """
    os.makedirs(output_dir, exist_ok=True)

    all_labels = LabelRegistry.all()
    class_names = []

    for neo4j_label, label_def in sorted(all_labels.items()):
        class_names.append(neo4j_label)
        stub_content = _build_stub_file(label_def)
        output_path = os.path.join(output_dir, f"{neo4j_label.lower()}.py")

        with open(output_path, 'w') as f:
            f.write(stub_content)

        print(f"  Generated: {neo4j_label} → {output_path}")

    # Generate __init__.py that re-exports all classes
    _write_init(output_dir, class_names)

    return class_names


def _build_stub_file(label_def: LabelDefinition) -> str:
    """Build the full Python source for a single Label stub file."""
    header = f'''\
# Auto-generated from {os.path.basename(label_def.source_path)} — DO NOT EDIT MANUALLY
# Regenerate with: scidk labels generate-stubs
# Label version: {label_def.version}
# Content hash: {label_def.content_hash[:12]}

from __future__ import annotations
from typing import Any, Optional
from scidk.schema.base import SciDKNode


'''
    return header + generate_stub_class(label_def)


def _write_init(output_dir: str, class_names: List[str]):
    """Write __init__.py that imports and re-exports all generated classes."""
    lines = [
        "# Auto-generated — DO NOT EDIT MANUALLY",
        "# Regenerate with: scidk labels generate-stubs",
        "",
        "# All SciDK node classes, importable as:",
        "#   from scidk.schema import Sample, ImagingDataset, Study",
        "",
    ]

    for class_name in sorted(class_names):
        module_name = class_name.lower()
        lines.append(f"from scidk.schema.generated.{module_name} import {class_name}")

    lines.append("")
    lines.append(f"__all__ = {sorted(class_names)!r}")
    lines.append("")

    init_path = os.path.join(output_dir, '__init__.py')
    with open(init_path, 'w') as f:
        f.write("\n".join(lines))

    print(f"  Generated: __init__.py with {len(class_names)} classes")


def _wrap_text(text: str, width: int) -> List[str]:
    """Simple word-wrap."""
    words = text.split()
    lines = []
    current = []
    current_len = 0

    for word in words:
        if current_len + len(word) + 1 > width and current:
            lines.append(" ".join(current))
            current = [word]
            current_len = len(word)
        else:
            current.append(word)
            current_len += len(word) + 1

    if current:
        lines.append(" ".join(current))

    return lines


if __name__ == "__main__":
    """Run as: python -m scidk.schema.generate_stubs"""
    import argparse

    parser = argparse.ArgumentParser(description="Generate SciDK schema stub classes from Label YAML")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "generated"),
        help="Output directory for generated stubs"
    )
    parser.add_argument(
        "--labels-dir",
        help="Override default labels directory"
    )
    args = parser.parse_args()

    if args.labels_dir:
        LabelRegistry.load([args.labels_dir])
    else:
        LabelRegistry.load()

    print(f"Generating stubs for {len(LabelRegistry.all())} labels...")
    class_names = generate_all_stubs(args.output_dir)
    print(f"\nDone. {len(class_names)} classes generated in {args.output_dir}")
    print("\nUsage:")
    print("    from scidk.schema import " + ", ".join(sorted(class_names)[:3]) + ", ...")
