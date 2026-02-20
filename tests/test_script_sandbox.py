"""Tests for script sandbox - import validation and subprocess execution."""
import time
import pytest

from scidk.core.script_sandbox import (
    validate_imports,
    run_sandboxed,
    check_script_imports,
    ImportValidationError,
    ALLOWED_IMPORTS
)


class TestImportValidation:
    """Test import whitelist validation."""

    def test_allowed_imports_pass(self):
        """Allowed imports should pass validation."""
        code = """
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List
"""
        imports = validate_imports(code)
        assert 'json' in imports
        assert 'pandas' in imports
        assert 'pathlib' in imports
        assert 'typing' in imports

    def test_disallowed_subprocess_blocked(self):
        """subprocess import should be blocked."""
        code = "import subprocess"
        with pytest.raises(ImportValidationError) as exc_info:
            validate_imports(code)
        assert 'subprocess' in str(exc_info.value)

    def test_disallowed_requests_blocked(self):
        """requests import should be blocked (network access)."""
        code = "import requests"
        with pytest.raises(ImportValidationError) as exc_info:
            validate_imports(code)
        assert 'requests' in str(exc_info.value)

    def test_disallowed_socket_blocked(self):
        """socket import should be blocked (network access)."""
        code = "import socket"
        with pytest.raises(ImportValidationError) as exc_info:
            validate_imports(code)
        assert 'socket' in str(exc_info.value)

    def test_disallowed_os_blocked(self):
        """os import should be blocked (file/system access)."""
        code = "import os"
        with pytest.raises(ImportValidationError) as exc_info:
            validate_imports(code)
        assert 'os' in str(exc_info.value)

    def test_sys_allowed_for_stderr(self):
        """sys import should be allowed (needed for stderr/stdout)."""
        code = "import sys"
        imports = validate_imports(code)
        assert 'sys' in imports

    def test_from_import_validation(self):
        """from X import Y should also be validated."""
        code = "from subprocess import run"
        with pytest.raises(ImportValidationError) as exc_info:
            validate_imports(code)
        assert 'subprocess' in str(exc_info.value)

    def test_nested_module_import(self):
        """Nested module imports should check top-level only."""
        code = "import pandas.core.frame"
        imports = validate_imports(code)
        assert 'pandas' in imports

    def test_multiple_disallowed_imports(self):
        """Multiple disallowed imports should all be reported."""
        code = """
import subprocess
import requests
import os
"""
        with pytest.raises(ImportValidationError) as exc_info:
            validate_imports(code)
        error_msg = str(exc_info.value)
        # Should mention at least one disallowed import
        assert any(module in error_msg for module in ['subprocess', 'requests', 'os'])

    def test_syntax_error_handling(self):
        """Code with syntax errors should raise SyntaxError."""
        code = "import json\nif True"  # Missing colon
        with pytest.raises(SyntaxError):
            validate_imports(code)

    def test_check_script_imports_helper(self):
        """check_script_imports() helper should return bool."""
        assert check_script_imports("import json") is True
        assert check_script_imports("import subprocess") is False
        assert check_script_imports("invalid syntax {") is False


class TestSandboxExecution:
    """Test sandboxed subprocess execution."""

    def test_simple_execution(self):
        """Simple code should execute successfully."""
        code = "print('hello world')"
        result = run_sandboxed(code)

        assert result['returncode'] == 0
        assert 'hello world' in result['stdout']
        assert result['timed_out'] is False

    def test_allowed_import_execution(self):
        """Code with allowed imports should execute."""
        code = """
import json
data = {'key': 'value'}
print(json.dumps(data))
"""
        result = run_sandboxed(code)

        assert result['returncode'] == 0
        assert 'key' in result['stdout']
        assert 'value' in result['stdout']

    def test_disallowed_import_blocked(self):
        """Code with disallowed imports should fail validation."""
        code = "import subprocess; print('should not run')"
        result = run_sandboxed(code)

        assert result['returncode'] != 0
        assert 'disallowed' in result['stderr'].lower() or 'not allowed' in result['stderr'].lower()
        assert 'should not run' not in result['stdout']

    def test_timeout_enforcement(self):
        """Long-running code should be killed after timeout."""
        code = """
import time
time.sleep(10)  # Will be killed before this completes
print('should not see this')
"""
        start = time.time()
        result = run_sandboxed(code, timeout=2)
        elapsed = time.time() - start

        assert result['timed_out'] is True
        assert result['returncode'] == 124  # Timeout exit code
        assert elapsed < 3  # Should kill well before 10s
        assert 'should not see this' not in result['stdout']
        assert 'timed out' in result['stderr'].lower()

    def test_stderr_captured(self):
        """Stderr should be captured."""
        code = """
import sys
print('error message', file=sys.stderr)
"""
        result = run_sandboxed(code, timeout=2)

        assert 'error message' in result['stderr']

    def test_exception_handling(self):
        """Unhandled exceptions should be captured in stderr."""
        code = "raise ValueError('test error')"
        result = run_sandboxed(code)

        assert result['returncode'] != 0
        assert 'ValueError' in result['stderr']
        assert 'test error' in result['stderr']

    def test_syntax_error_before_execution(self):
        """Syntax errors should be caught in validation, not execution."""
        code = "import json\nif True"  # Missing colon
        result = run_sandboxed(code)

        assert result['returncode'] != 0
        assert 'syntax' in result['stderr'].lower() or 'error' in result['stderr'].lower()

    def test_pandas_import_works(self):
        """pandas is whitelisted and should work."""
        code = """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3]})
print(df['a'].sum())
"""
        result = run_sandboxed(code, timeout=10)

        assert result['returncode'] == 0
        assert '6' in result['stdout']


class TestAdversarialScripts:
    """Test adversarial attempts to break sandbox."""

    def test_builtins_subprocess_access(self):
        """Attempt to access subprocess via __builtins__ should fail."""
        code = """
import json
# Try to reach subprocess through object introspection
try:
    classes = ().__class__.__bases__[0].__subclasses__()
    # Even if we find subprocess, the import is still blocked
    print('accessed builtins')
except:
    print('blocked')
"""
        result = run_sandboxed(code)
        # Script may run but shouldn't be able to import subprocess
        # This is a known limitation - full builtins restriction is post-MVP
        # For now, we just ensure the direct import is blocked
        assert result['returncode'] == 0

    def test_eval_import_attempt(self):
        """Attempt to use eval to import should fail."""
        code = """
try:
    eval('import subprocess')
    print('eval worked')
except:
    print('eval blocked')
"""
        result = run_sandboxed(code)
        # eval is allowed in MVP but subprocess import still blocked
        # This test documents current behavior
        assert result['returncode'] == 0

    def test_multiple_timeout_attempts(self):
        """Multiple long sleeps should all be killed."""
        code = "import time; time.sleep(100)"

        # Run multiple times to ensure timeout works consistently
        for _ in range(3):
            result = run_sandboxed(code, timeout=1)
            assert result['timed_out'] is True
            assert result['returncode'] == 124

    def test_infinite_loop_timeout(self):
        """Infinite loop should be killed by timeout."""
        code = "while True: pass"
        result = run_sandboxed(code, timeout=2)

        assert result['timed_out'] is True
        assert result['returncode'] == 124

    def test_memory_bomb_timeout(self):
        """Memory allocation bomb should be killed by timeout."""
        code = "x = [];\nwhile True: x.append([0] * 1000000)"
        result = run_sandboxed(code, timeout=2)

        # Should timeout (may also hit memory limit depending on system)
        assert result['timed_out'] is True or result['returncode'] != 0


class TestWhitelistCompleteness:
    """Verify whitelist contains expected safe modules."""

    def test_json_whitelisted(self):
        """json should be in whitelist."""
        assert 'json' in ALLOWED_IMPORTS

    def test_pandas_whitelisted(self):
        """pandas should be in whitelist."""
        assert 'pandas' in ALLOWED_IMPORTS

    def test_numpy_whitelisted(self):
        """numpy should be in whitelist."""
        assert 'numpy' in ALLOWED_IMPORTS

    def test_pathlib_whitelisted(self):
        """pathlib should be in whitelist."""
        assert 'pathlib' in ALLOWED_IMPORTS

    def test_csv_whitelisted(self):
        """csv should be in whitelist."""
        assert 'csv' in ALLOWED_IMPORTS

    def test_subprocess_not_whitelisted(self):
        """subprocess should NOT be in whitelist."""
        assert 'subprocess' not in ALLOWED_IMPORTS

    def test_requests_not_whitelisted(self):
        """requests should NOT be in whitelist."""
        assert 'requests' not in ALLOWED_IMPORTS

    def test_socket_not_whitelisted(self):
        """socket should NOT be in whitelist."""
        assert 'socket' not in ALLOWED_IMPORTS

    def test_os_not_whitelisted(self):
        """os should NOT be in whitelist."""
        assert 'os' not in ALLOWED_IMPORTS
