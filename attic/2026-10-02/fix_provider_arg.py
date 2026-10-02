#!/usr/bin/env python3
"""
Minimal fix: inject --provider argument and dir-check guard into scidk_scanner_opt.py.
Run after patch_scanner_rclone.py has already been applied.
"""
import sys, re

def fix(filepath):
    with open(filepath) as f:
        src = f.read()

    if '--provider' in src:
        print("--provider already present, nothing to do.")
        return

    PROVIDER_BLOCK = '''
    parser.add_argument(
        '--provider',
        choices=['local', 'rclone'],
        default='local',
        help=(
            "Filesystem provider: 'local' (default) walks a local/NFS path; "
            "'rclone' calls 'rclone lsjson --recursive' on an rclone remote "
            "(e.g. 'dropbox:' or 'ki-preclinical-data:Images'). "
            "rclone must be on PATH when using --provider rclone."
        ),
    )'''

    # Find --quiet argument regardless of quote style, insert provider after it
    # Pattern: parser.add_argument(   ['\"]--quiet['\"]  ...  )
    # We match the whole add_argument call spanning potentially multiple lines.
    pattern = r"(parser\.add_argument\(['\"]--quiet['\"][^)]*\))"
    match = re.search(pattern, src, re.DOTALL)
    if not match:
        print("ERROR: could not find --quiet argument. Aborting.")
        sys.exit(1)

    end = match.end()
    src = src[:end] + PROVIDER_BLOCK + src[end:]
    print("  + --provider argument injected after --quiet")

    with open(filepath, 'w') as f:
        f.write(src)
    print(f"Fixed {filepath}.")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} /path/to/scidk_scanner_opt.py")
        sys.exit(1)
    fix(sys.argv[1])
