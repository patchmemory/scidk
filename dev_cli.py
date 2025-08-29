#!/usr/bin/env python3
"""
Dev CLI wrapper
Usage: python3 dev_cli.py <command> [args]
This wrapper executes dev/cli.py as __main__ so the documented command works.
Tip (fish): Prefer `python3 -m dev.cli <subcommand>` or `python3 dev_cli.py <command>`.
When dev/ is a Git submodule and cli.py is missing, this wrapper will attempt to
synchronize the submodule automatically.
"""
import os
import runpy
import subprocess
import sys


def _try_submodule_sync(repo_root: str) -> bool:
    """Attempt to initialize/update the dev submodule safely.
    Returns True if the dev/ folder exists after the attempt.
    Uses subprocess without shell so it's fish-compatible.
    """
    dev_path = os.path.join(repo_root, 'dev')
    # Ensure git is available
    try:
        r = subprocess.run(['git', 'rev-parse', '--is-inside-work-tree'], cwd=repo_root, capture_output=True, text=True)
        if r.returncode != 0:
            return False
    except Exception:
        return False
    # Initialize submodules if needed
    try:
        subprocess.run(['git', 'submodule', 'update', '--init', '--recursive'], cwd=repo_root, check=False)
        # Try pulling latest for dev, if it exists
        if os.path.isdir(dev_path):
            subprocess.run(['git', 'submodule', 'update', '--remote', '--merge', 'dev'], cwd=repo_root, check=False)
    except Exception:
        return False
    return os.path.isdir(dev_path)


def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    cli_path = os.path.join(repo_root, 'dev', 'cli.py')
    if not os.path.exists(cli_path):
        # Attempt to sync submodule automatically
        synced = _try_submodule_sync(repo_root)
        if synced and os.path.exists(cli_path):
            # proceed
            pass
        else:
            print('Error: dev/cli.py not found. If dev/ is a submodule, sync it first:')
            print('  (fish) git submodule update --init --remote --merge dev')
            print('Alternatively run commands as a module once dev is present:')
            print('  (fish) python3 -m dev.cli ready-queue')
            sys.exit(1)
    # Execute the CLI script as if called directly
    runpy.run_path(cli_path, run_name='__main__')


if __name__ == '__main__':
    main()
