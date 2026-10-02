#!/usr/bin/env python3
"""
Surgical fix: insert --provider add_argument call between --quiet and args = parser.parse_args()
"""
import sys

def fix(filepath):
    with open(filepath) as f:
        src = f.read()

    OLD = '    parser.add_argument("--quiet", action="store_true")\n    args = parser.parse_args()'
    NEW = '''    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["local", "rclone"],
        default="local",
        help=(
            "Filesystem provider: 'local' (default) walks a local/NFS path; "
            "'rclone' calls 'rclone lsjson --recursive' on an rclone remote "
            "(e.g. 'dropbox:' or 'ki-preclinical-data:Images'). "
            "rclone must be on PATH when using --provider rclone."
        ),
    )
    args = parser.parse_args()'''

    if '--provider' in src and 'choices' in src:
        print("--provider with choices already present — checking if it's in main()...")
        if 'parser.add_argument(\n        "--provider"' in src or "parser.add_argument(\n        '--provider'" in src:
            print("Already correctly placed. Nothing to do.")
            return

    if OLD not in src:
        # Try single-quote variant
        OLD = "    parser.add_argument('--quiet', action='store_true')\n    args = parser.parse_args()"
        NEW = NEW.replace('"--quiet"', "'--quiet'").replace('"--provider"', "'--provider'").replace('"local"', "'local'").replace('"rclone"', "'rclone'")

    if OLD not in src:
        print("ERROR: could not find the --quiet / parse_args() boundary. Showing context:")
        idx = src.find('parse_args()')
        print(repr(src[max(0,idx-200):idx+50]))
        sys.exit(1)

    src = src.replace(OLD, NEW, 1)
    with open(filepath, 'w') as f:
        f.write(src)
    print(f"Fixed: --provider argument inserted into main() argparse block in {filepath}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} /path/to/scidk_scanner_opt.py")
        sys.exit(1)
    fix(sys.argv[1])
