"""
Auto-discovery for SciDK interpreters.

Each interpreter declares its extensions and metadata as class attributes.
Adding a new interpreter requires only:
1. Create the interpreter class file
2. Add import and class to INTERPRETERS list
3. Define extensions = [...] on the class
"""

from .python_code import PythonCodeInterpreter
from .csv_interpreter import CsvInterpreter
from .json_interpreter import JsonInterpreter
from .yaml_interpreter import YamlInterpreter
from .ipynb_interpreter import IpynbInterpreter
from .txt_interpreter import TxtInterpreter
from .xlsx_interpreter import XlsxInterpreter

# Centralized interpreter registry
INTERPRETERS = [
    PythonCodeInterpreter,
    CsvInterpreter,
    JsonInterpreter,
    YamlInterpreter,
    IpynbInterpreter,
    TxtInterpreter,
    XlsxInterpreter,
]


def register_all(registry):
    """
    Register all interpreters with their extensions and rules.

    This replaces ~60 lines of manual registration code in app.py.
    Each interpreter is:
    1. Instantiated
    2. Registered for each of its extensions
    3. Auto-assigned rules for pattern matching

    Args:
        registry: InterpreterRegistry instance to register with
    """
    from ..core.pattern_matcher import Rule

    for interp_class in INTERPRETERS:
        instance = interp_class()

        # Get extensions from class metadata
        extensions = getattr(interp_class, 'extensions', [])

        # Register by each extension
        for ext in extensions:
            registry.register_extension(ext, instance)

        # Auto-create default rules for each extension
        for ext in extensions:
            pattern = f"*{ext}"
            # Convert '.py' → 'py' for rule id
            ext_name = ext.lstrip('.')
            rule_id = f"rule.{ext_name}.default"

            registry.register_rule(Rule(
                id=rule_id,
                interpreter_id=instance.id,
                pattern=pattern,
                priority=10,
                conditions={"ext": ext}
            ))
