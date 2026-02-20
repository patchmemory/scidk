"""
Script validators for contract testing and validation.

Implements compositional validation hierarchy where:
- BaseValidator: Plugin contract (returns valid SciDK data object)
- InterpreterValidator: Extends Plugin + interpret(Path) signature
- LinkValidator: Extends Plugin + create_links() signature

Each validators runs contract tests in sandbox and returns ValidationResult.
"""
import ast
import time
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

from .script_sandbox import run_sandboxed

if TYPE_CHECKING:
    from .scripts import Script


def extract_docstring(code: str) -> str:
    """
    Extract module-level docstring from Python code.

    Uses AST parsing to get the first string literal in the module,
    which is the docstring by Python convention.

    Args:
        code: Python source code

    Returns:
        Extracted docstring or empty string if none found
    """
    try:
        tree = ast.parse(code)
        # Get module docstring (first Expr node with a Str/Constant value)
        if (tree.body and
            isinstance(tree.body[0], ast.Expr) and
            isinstance(tree.body[0].value, (ast.Str, ast.Constant))):

            # Handle both ast.Str (Python <3.8) and ast.Constant (Python >=3.8)
            if isinstance(tree.body[0].value, ast.Str):
                return tree.body[0].value.s
            elif isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
                return tree.body[0].value.value

        return ''
    except (SyntaxError, AttributeError):
        # If code has syntax errors or unexpected structure, return empty string
        return ''


class ValidationResult:
    """Result of validation tests with compositional merge support."""

    def __init__(
        self,
        passed: bool,
        errors: List[str],
        test_results: Dict[str, bool],
        warnings: Optional[List[str]] = None
    ):
        """
        Initialize validation result.

        Args:
            passed: Overall pass/fail status
            errors: List of error messages (for failed tests)
            test_results: Dict mapping test name to bool result
            warnings: Optional list of warnings (doesn't affect pass/fail)
        """
        self.passed = passed
        self.errors = errors or []
        self.test_results = test_results or {}
        self.warnings = warnings or []

    def merge(self, other: 'ValidationResult') -> 'ValidationResult':
        """
        Merge two validation results (for compositional validators).

        Used when a derived validator extends a base validator - combines
        the test results from both.

        Args:
            other: Another ValidationResult to merge

        Returns:
            New ValidationResult with combined results
        """
        return ValidationResult(
            passed=self.passed and other.passed,
            errors=self.errors + other.errors,
            test_results={**self.test_results, **other.test_results},
            warnings=self.warnings + other.warnings
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'passed': self.passed,
            'errors': self.errors,
            'test_results': self.test_results,
            'warnings': self.warnings,
            'test_count': len(self.test_results),
            'passed_count': sum(1 for v in self.test_results.values() if v),
            'failed_count': sum(1 for v in self.test_results.values() if not v)
        }


class BaseValidator:
    """
    Base validator for Plugin contract.

    Tests that script returns valid SciDK data object and handles errors gracefully.
    All other validators (Interpreter, Link) extend this base contract.
    """

    def __init__(self):
        """Initialize base validator."""
        self.timeout = 10  # Default timeout for validation tests

    def validate(self, script: 'Script') -> ValidationResult:
        """
        Run base contract tests on script.

        Args:
            script: Script object to validate

        Returns:
            ValidationResult with test results
        """
        tests = {}
        errors = []
        warnings = []

        # Test 1: Has required function (base: just checks syntax)
        try:
            ast.parse(script.code)
            tests['valid_syntax'] = True
        except SyntaxError as e:
            tests['valid_syntax'] = False
            errors.append(f"Syntax error: {e}")

        # Test 2: Can execute without crashing (in sandbox)
        # For Scripts page scripts, provide minimal execution context
        if tests.get('valid_syntax', False):
            # Wrap script with minimal execution environment
            wrapped_code = f"""
import json
import pandas as pd
from pathlib import Path

# Provide minimal context that scripts expect
parameters = {{}}
neo4j_driver = None
results = []
__file__ = '<script>'  # Provide __file__ for scripts that need it

# Execute the script
{script.code}
"""
            result = run_sandboxed(wrapped_code, timeout=self.timeout)
            tests['executes_without_error'] = result['returncode'] == 0
            if result['returncode'] != 0:
                errors.append(f"Script execution failed: {result['stderr'][:200]}")
            if result['timed_out']:
                warnings.append(f"Execution took longer than {self.timeout}s (timeout)")
        else:
            tests['executes_without_error'] = False

        # Overall pass: all tests must pass
        passed = all(tests.values())

        return ValidationResult(
            passed=passed,
            errors=errors,
            test_results=tests,
            warnings=warnings
        )

    def _check_function_exists(self, code: str, function_name: str) -> bool:
        """
        Helper: Check if function exists in code via AST.

        Args:
            code: Python source code
            function_name: Name of function to find

        Returns:
            True if function defined, False otherwise
        """
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == function_name:
                    return True
            return False
        except SyntaxError:
            return False


class InterpreterValidator(BaseValidator):
    """
    Validator for Interpreter contract.

    Extends Plugin contract + requires:
    - interpret(file_path: Path) function signature
    - Returns Dict with 'status' key
    - Handles missing files gracefully
    - Handles corrupt files gracefully
    """

    def validate(self, script: 'Script') -> ValidationResult:
        """
        Run Interpreter contract tests.

        Inherits Plugin tests + adds Interpreter-specific tests.

        Args:
            script: Script object to validate

        Returns:
            ValidationResult with combined base + interpreter tests
        """
        # Run base tests first
        base_result = super().validate(script)

        # Interpreter-specific tests
        tests = {}
        errors = []
        warnings = []

        # Test 1: Has interpret() function
        has_interpret = self._check_function_exists(script.code, 'interpret')
        tests['has_interpret_function'] = has_interpret
        if not has_interpret:
            errors.append("Missing required function: interpret(file_path)")

        # Test 2: interpret() signature accepts Path parameter
        if has_interpret:
            # Check function signature via AST
            try:
                tree = ast.parse(script.code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == 'interpret':
                        # Check has at least one parameter
                        has_param = len(node.args.args) >= 1
                        tests['interpret_has_parameter'] = has_param
                        if not has_param:
                            errors.append("interpret() must accept file_path parameter")
                        break
            except SyntaxError:
                tests['interpret_has_parameter'] = False
        else:
            tests['interpret_has_parameter'] = False

        # Test 3: Returns dict (check via sample execution)
        if tests.get('has_interpret_function') and base_result.passed:
            test_code = f"""
{script.code}

from pathlib import Path
result = interpret(Path('/nonexistent/file.txt'))
print(type(result).__name__)
"""
            result = run_sandboxed(test_code, timeout=self.timeout)
            returns_dict = 'dict' in result['stdout'].lower()
            tests['returns_dict'] = returns_dict
            if not returns_dict:
                errors.append(f"interpret() must return dict, got: {result['stdout'][:100]}")
        else:
            tests['returns_dict'] = False

        # Test 4: Returns dict with 'status' key
        if tests.get('returns_dict'):
            test_code = f"""
{script.code}

from pathlib import Path
result = interpret(Path('/nonexistent/file.txt'))
print('status' in result)
"""
            result = run_sandboxed(test_code, timeout=self.timeout)
            has_status = 'true' in result['stdout'].lower()
            tests['returns_status_key'] = has_status
            if not has_status:
                errors.append("interpret() must return dict with 'status' key")
        else:
            tests['returns_status_key'] = False

        # Test 5: Handles missing file gracefully
        if tests.get('has_interpret_function'):
            test_code = f"""
{script.code}

from pathlib import Path
result = interpret(Path('/nonexistent/missing_file.txt'))
if result.get('status') == 'error':
    print('handles_missing_file: True')
else:
    print('handles_missing_file: False')
"""
            result = run_sandboxed(test_code, timeout=self.timeout)
            handles_missing = 'true' in result['stdout'].lower()
            tests['handles_missing_file'] = handles_missing
            if not handles_missing:
                errors.append("interpret() must return {'status': 'error'} for missing files")
        else:
            tests['handles_missing_file'] = False

        # Build interpreter result
        interpreter_passed = all(tests.values())
        interpreter_result = ValidationResult(
            passed=interpreter_passed,
            errors=errors,
            test_results=tests,
            warnings=warnings
        )

        # Merge with base result
        return base_result.merge(interpreter_result)


class LinkValidator(BaseValidator):
    """
    Validator for Link contract.

    Extends Plugin contract + requires:
    - create_links(source_nodes, target_nodes) function signature
    - Returns list of tuples/dicts (triples)
    - Handles empty inputs gracefully
    - Returns valid relationship types (strings)
    """

    def validate(self, script: 'Script') -> ValidationResult:
        """
        Run Link contract tests.

        Inherits Plugin tests + adds Link-specific tests.

        Args:
            script: Script object to validate

        Returns:
            ValidationResult with combined base + link tests
        """
        # Run base tests first
        base_result = super().validate(script)

        # Link-specific tests
        tests = {}
        errors = []
        warnings = []

        # Test 1: Has create_links() function
        has_create_links = self._check_function_exists(script.code, 'create_links')
        tests['has_create_links_function'] = has_create_links
        if not has_create_links:
            errors.append("Missing required function: create_links(source_nodes, target_nodes)")

        # Test 2: create_links() accepts two parameters
        if has_create_links:
            try:
                tree = ast.parse(script.code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == 'create_links':
                        has_two_params = len(node.args.args) >= 2
                        tests['create_links_has_two_parameters'] = has_two_params
                        if not has_two_params:
                            errors.append("create_links() must accept source_nodes and target_nodes parameters")
                        break
            except SyntaxError:
                tests['create_links_has_two_parameters'] = False
        else:
            tests['create_links_has_two_parameters'] = False

        # Test 3: Returns list
        if tests.get('has_create_links_function') and base_result.passed:
            test_code = f"""
{script.code}

result = create_links([], [])
print(type(result).__name__)
"""
            result = run_sandboxed(test_code, timeout=self.timeout)
            returns_list = 'list' in result['stdout'].lower()
            tests['returns_list'] = returns_list
            if not returns_list:
                errors.append(f"create_links() must return list, got: {result['stdout'][:100]}")
        else:
            tests['returns_list'] = False

        # Test 4: Handles empty inputs
        if tests.get('returns_list'):
            test_code = f"""
{script.code}

result = create_links([], [])
print(f'length: {{len(result)}}')
"""
            result = run_sandboxed(test_code, timeout=self.timeout)
            handles_empty = 'length:' in result['stdout'].lower()
            tests['handles_empty_inputs'] = handles_empty
            if not handles_empty:
                warnings.append("create_links() should handle empty inputs gracefully")
        else:
            tests['handles_empty_inputs'] = False

        # Build link result
        link_passed = all(tests.values())
        link_result = ValidationResult(
            passed=link_passed,
            errors=errors,
            test_results=tests,
            warnings=warnings
        )

        # Merge with base result
        return base_result.merge(link_result)


def get_validator_for_category(category: str) -> BaseValidator:
    """
    Get appropriate validator for script category.

    Args:
        category: Script category (e.g., 'interpreters', 'links', 'plugins')

    Returns:
        Validator instance for that category
    """
    if category == 'interpreters' or 'interpreter' in category:
        return InterpreterValidator()
    elif category == 'links' or 'link' in category:
        return LinkValidator()
    else:
        # Default to base validator for plugins and unknown categories
        return BaseValidator()
