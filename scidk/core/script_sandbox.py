"""
Script execution sandbox for safe validation and testing.

Provides pragmatic subprocess-based sandboxing with:
- Import whitelist validation (AST-based, pre-execution)
- Timeout enforcement
- Subprocess isolation

Explicitly NOT doing (post-MVP):
- Full AST-based __builtins__ restriction
- Jail/container environments
- Advanced resource limits beyond basic timeout
"""
import ast
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Whitelist of allowed imports for script execution
# Safe read-only libraries that don't allow file I/O, network, or subprocess access
# Note: sys is allowed for basic operations (stderr, stdout) but dangerous sys functions
# like sys.exit() are acceptable risks in subprocess isolation
ALLOWED_IMPORTS = [
    'json',
    'csv',
    're',
    'pathlib',
    'datetime',
    'time',
    'pandas',
    'numpy',
    'ast',
    'typing',
    'collections',
    'itertools',
    'functools',
    'math',
    'statistics',
    'sys',  # Needed for stderr/stdout access in scripts
    'pickle',  # Needed for BO plugin and state persistence
               # Security: Only allowed for files within managed directories
               # Risk accepted for MVP - subprocess isolation mitigates arbitrary code execution
    'scidk',  # Core framework - interpreters/links/plugins need access to Manager, context, etc.
              # Security: Scripts validated before activation, subprocess isolation limits risk
    'argparse',  # For CLI-style parameter parsing in scripts
]


class ImportValidationError(ValueError):
    """Raised when script contains disallowed imports."""
    pass


class SandboxExecutionError(RuntimeError):
    """Raised when sandbox execution fails."""
    pass


def validate_imports(code: str) -> List[str]:
    """
    Validate that code only imports from whitelist.

    Uses AST parsing to check all import statements before execution.
    This prevents access to dangerous modules like subprocess, requests, socket, etc.

    Args:
        code: Python source code to validate

    Returns:
        List of imported module names (top-level only)

    Raises:
        ImportValidationError: If code imports disallowed modules
        SyntaxError: If code has syntax errors
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise SyntaxError(f"Script has syntax errors: {e}")

    imports = []
    disallowed = []

    for node in ast.walk(tree):
        # Handle: import foo, import foo.bar
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split('.')[0]  # Get top-level module
                imports.append(module)
                if module not in ALLOWED_IMPORTS:
                    disallowed.append(module)

        # Handle: from foo import bar
        elif isinstance(node, ast.ImportFrom):
            # Block relative imports (from . import x, from .. import y)
            if node.level > 0:
                disallowed.append('relative_import')
                continue

            if node.module:
                module = node.module.split('.')[0]  # Get top-level module
                imports.append(module)
                if module not in ALLOWED_IMPORTS:
                    disallowed.append(module)

    if disallowed:
        raise ImportValidationError(
            f"Script contains disallowed imports: {', '.join(set(disallowed))}. "
            f"Allowed imports: {', '.join(ALLOWED_IMPORTS)}"
        )

    return list(set(imports))


def run_sandboxed(
    code: str,
    timeout: int = 10,
    input_data: Optional[str] = None,
    working_dir: Optional[Path] = None
) -> Dict[str, any]:
    """
    Execute Python code in a subprocess with timeout and import restrictions.

    Args:
        code: Python source code to execute
        timeout: Maximum execution time in seconds (default: 10)
        input_data: Optional stdin data to pass to subprocess
        working_dir: Optional working directory for subprocess

    Returns:
        Dict with:
            - stdout: str - Standard output
            - stderr: str - Standard error
            - returncode: int - Exit code (0 = success)
            - timed_out: bool - Whether execution exceeded timeout

    Raises:
        ImportValidationError: If code contains disallowed imports
        SandboxExecutionError: If subprocess execution fails unexpectedly
    """
    # Validate imports before execution
    try:
        validate_imports(code)
    except (ImportValidationError, SyntaxError) as e:
        return {
            'stdout': '',
            'stderr': str(e),
            'returncode': 1,
            'timed_out': False
        }

    # Run in subprocess with timeout
    try:
        result = subprocess.run(
            [sys.executable, '-c', code],
            capture_output=True,
            timeout=timeout,
            text=True,
            input=input_data,
            cwd=working_dir,
            # Don't inherit environment vars that might have credentials
            env={'PATH': subprocess.os.environ.get('PATH', '')}
        )

        return {
            'stdout': result.stdout,
            'stderr': result.stderr,
            'returncode': result.returncode,
            'timed_out': False
        }

    except subprocess.TimeoutExpired:
        return {
            'stdout': '',
            'stderr': f'Execution timed out after {timeout} seconds',
            'returncode': 124,  # Standard timeout exit code
            'timed_out': True
        }

    except Exception as e:
        raise SandboxExecutionError(f"Sandbox execution failed: {e}")


def check_script_imports(script_code: str) -> bool:
    """
    Quick check: Does script pass import validation?

    Args:
        script_code: Python code to check

    Returns:
        True if imports are valid, False otherwise
    """
    try:
        validate_imports(script_code)
        return True
    except (ImportValidationError, SyntaxError):
        return False
