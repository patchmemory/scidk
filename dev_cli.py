#!/usr/bin/env python3
"""
Dev CLI wrapper
Usage: python dev_cli.py <command> [args]
This wrapper executes dev/cli.py as __main__ so the documented command works.
"""
import os
import runpy
import sys


def main():
    repo_root = os.path.dirname(os.path.abspath(__file__))
    cli_path = os.path.join(repo_root, 'dev', 'cli.py')
    if not os.path.exists(cli_path):
        print('Error: dev/cli.py not found')
        sys.exit(1)
    # Execute the CLI script as if called directly
    runpy.run_path(cli_path, run_name='__main__')


if __name__ == '__main__':
    main()
