#!/usr/bin/env python3
import sys

OLD = "        lsjson_args = ['lsjson', '--recursive', '--no-modtime-dirs',\n                       '--links', '--stat', target]"
NEW = "        lsjson_args = ['lsjson', '--recursive', '--no-modtime', target]"

def fix(filepath):
    with open(filepath) as f:
        src = f.read()
    if OLD not in src:
        print("Pattern not found.")
        sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    with open(filepath, 'w') as f:
        f.write(src)
    print("Fixed lsjson flags.")

fix(sys.argv[1] if len(sys.argv) > 1 else '/home/patch/PycharmProjects/scidk/scidk_scanner_opt.py')
