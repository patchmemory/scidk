"""
Entry point for running scidk as a module: python -m scidk

This ensures the package is run from the installed location rather than
the current directory, avoiding issues with local test stubs shadowing
real packages (e.g., the local neo4j/ stub shadowing the real neo4j driver).
"""
import sys
from pathlib import Path

# Remove current directory from sys.path to avoid shadowing installed packages
# This is added by default when using `python -m` but can cause issues
cwd = str(Path.cwd())
if cwd in sys.path:
    sys.path.remove(cwd)

# Also remove empty string which represents cwd
if '' in sys.path:
    sys.path.remove('')

# Now import and run the main function
from scidk.app import main

if __name__ == '__main__':
    main()
