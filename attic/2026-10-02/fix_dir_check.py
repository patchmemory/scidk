#!/usr/bin/env python3
"""Fix the os.path.isdir() guard so rclone targets skip it."""
import sys

OLD = '''    root = str(Path(args.root).resolve())
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a directory.", file=sys.stderr)
        sys.exit(1)'''

NEW = '''    if args.provider == "rclone":
        root = args.root  # rclone target, not a local path
        if not shutil.which("rclone"):
            print("Error: rclone not found on PATH.", file=sys.stderr)
            sys.exit(1)
    else:
        root = str(Path(args.root).resolve())
        if not os.path.isdir(root):
            print(f"Error: '{root}' is not a directory.", file=sys.stderr)
            sys.exit(1)'''

def fix(filepath):
    with open(filepath) as f:
        src = f.read()
    if OLD not in src:
        print("Pattern not found — already patched or file differs.")
        print("Looking for isdir...")
        idx = src.find('isdir')
        if idx >= 0:
            print(repr(src[max(0,idx-200):idx+100]))
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    with open(filepath, 'w') as f:
        f.write(src)
    print(f"Fixed dir check in {filepath}")

if __name__ == '__main__':
    fix(sys.argv[1] if len(sys.argv) > 1 else
        '/home/patch/PycharmProjects/scidk/scidk_scanner_opt.py')
