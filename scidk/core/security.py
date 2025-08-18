import signal
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Optional


class TimeoutException(Exception):
    pass


@contextmanager
def _timeout(seconds: int):
    def handler(signum, frame):
        raise TimeoutException("Operation timed out")
    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


class SecureInterpreterExecutor:
    """MVP stub.
    - Provides a safe-ish way to run certain interpreters with a timeout.
    - For Python inline interpreters, the interpreter itself should be safe.
    - For shell/bash, use subprocess with disabled network/etc (not fully implemented here).
    """

    def __init__(self, default_timeout: int = 5):
        self.default_timeout = default_timeout

    def run_python_inline(self, callable_fn, *args, timeout: Optional[int] = None, **kwargs) -> Any:
        t = timeout or self.default_timeout
        with _timeout(t):
            return callable_fn(*args, **kwargs)

    def run_bash(self, script: str, cwd: Optional[Path] = None, timeout: Optional[int] = None) -> Dict:
        t = timeout or self.default_timeout
        # NOTE: This is a placeholder. In real MVP we should disable env, limit PATH, no network, etc.
        try:
            out = subprocess.run(
                ["bash", "-lc", script],
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=t,
                check=False,
                env={}
            )
            return {
                'returncode': out.returncode,
                'stdout': out.stdout,
                'stderr': out.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': 'timeout'
            }
