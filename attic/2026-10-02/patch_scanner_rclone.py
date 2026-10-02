#!/usr/bin/env python3
"""
Patch scidk_scanner_opt.py to add:
  1. import socket + shutil at top
  2. Inline rclone path helpers (_rc_depth, _rc_parent, _rc_join)
  3. walk_rclone() function
  4. --provider {local,rclone} argparse argument
  5. Fix remote=None -> socket.getfqdn() in local scan rows
  6. Dispatch in main() based on --provider

Run:
    python3 patch_scanner_rclone.py ~/PycharmProjects/scidk/scidk_scanner_opt.py
"""
import sys
import re

RCLONE_HELPERS = '''

# ─────────────────────────────────────────────────────────────────────────────
# rclone provider — optional code path, activated by --provider rclone
# rclone is a binary (not a Python package), so there is no import to guard.
# The only stdlib functions used are subprocess, json, shutil, socket, time.
# ─────────────────────────────────────────────────────────────────────────────

def _rc_depth(path: str) -> int:
    """Depth of an rclone path like 'dropbox:Photos/2024' or 'remote:/a/b'."""
    if ':' in path:
        suffix = path.split(':', 1)[1].strip('/')
        return 0 if not suffix else suffix.count('/') + 1
    return _depth(path)


def _rc_parent(path: str) -> str:
    """Parent of an rclone path. Root returns itself."""
    if ':' in path:
        remote_prefix, rest = path.split(':', 1)
        rest = rest.strip('/')
        if not rest or '/' not in rest:
            return remote_prefix + ':'
        return remote_prefix + ':' + rest.rsplit('/', 1)[0]
    p = str(Path(path).parent)
    return p if p != path else path


def _rc_join(base: str, name: str) -> str:
    """Join an rclone base path with a child name."""
    if ':' in base:
        remote_prefix, rest = base.split(':', 1)
        rest = rest.strip('/')
        return remote_prefix + ':' + (rest + '/' + name if rest else name)
    return str(Path(base) / name)


def _rclone_run(args: List[str]) -> str:
    """Run rclone with args, return stdout. Raises RuntimeError on failure."""
    import shutil as _shutil
    import subprocess as _subprocess
    exe = _shutil.which('rclone')
    if not exe:
        raise RuntimeError("rclone not found on PATH — install rclone or use --provider local")
    proc = _subprocess.run(
        [exe] + args,
        stdout=_subprocess.PIPE, stderr=_subprocess.PIPE,
        text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"rclone exited {proc.returncode}")
    return proc.stdout


def walk_rclone(
    target: str,
    scan_id: str,
    conn: sqlite3.Connection,
    *,
    max_depth: Optional[int] = None,
    do_hash: bool = False,          # rclone etags replace hashes; hashing disabled by default
    quiet: bool = False,
) -> Dict:
    """Walk an rclone remote (e.g. 'dropbox:' or 'ki-preclinical-data:Images')
    and write file + folder rows into *conn* using the same 16-column schema as
    walk_path().  Returns a stats dict compatible with the local scanner.

    Implementation notes
    ────────────────────
    • rclone lsjson --recursive returns a flat JSON array — no subtree splitting.
      A single writer thread is sufficient; rclone itself handles the concurrency.
    • Folders are emitted in a first pass (sorted by depth so parents precede
      children); files in a second pass.  This avoids a dependency on insertion
      order in downstream queries that walk parent_path.
    • etag is populated from rclone's "ID" field when present (Drive/Dropbox
      object IDs), or from the "Hashes" dict (MD5/SHA1) otherwise.
    • interpreted_as / interpretation_json are populated by the same helpers as
      the local scanner.
    • remote column = the remote name prefix (e.g. 'dropbox', 'ki-preclinical-data').
    """
    import json as _json
    import subprocess as _subprocess
    import shutil as _shutil

    remote_name = target.split(':', 1)[0] if ':' in target else target

    stats: Dict = {"files": 0, "dirs": 0, "bytes": 0,
                   "gaps": 0, "identified": 0, "errors": 0}
    stats_lock = threading.Lock()
    writer_error: List[BaseException] = []
    write_q: "queue.Queue" = queue.Queue(maxsize=16000)

    writer = threading.Thread(
        target=_writer_thread,
        args=(write_q, conn, scan_id, stats, stats_lock, quiet, writer_error),
        daemon=True,
        name="scidk-rclone-writer",
    )
    writer.start()

    mimetypes.init()

    try:
        lsjson_args = ['lsjson', '--recursive', '--no-modtime-dirs',
                       '--links', '--stat', target]
        if max_depth is not None:
            lsjson_args += ['--max-depth', str(max_depth)]

        if not quiet:
            print(f"  [rclone] listing {target} …", flush=True)

        raw = _rclone_run(lsjson_args)
        items: List[Dict] = _json.loads(raw) if raw.strip() else []

        if not quiet:
            print(f"  [rclone] {len(items):,} items received, indexing…", flush=True)

        # Separate and sort: folders first (by depth so parents before children)
        folders = sorted(
            [it for it in items if it.get('IsDir', False)],
            key=lambda it: it.get('Path', '').count('/'),
        )
        files = [it for it in items if not it.get('IsDir', False)]

        # Emit root directory row
        rmtime_str = None  # lsjson --no-modtime-dirs omits mtime for dirs
        rmtime = None
        root_pattern = _detect_dir_pattern([it.get('Name', '') for it in items
                                            if '/' not in it.get('Path', '')])
        root_extra  = _json.dumps({"pattern": root_pattern}) if root_pattern else None
        root_interp = interpreter_for_dir_pattern(root_pattern)
        root_depth  = _rc_depth(target)
        root_parent = _rc_parent(target)
        root_name   = target.split(':', 1)[1].strip('/').rsplit('/', 1)[-1] if ':' in target else target
        if not root_name:
            root_name = remote_name

        write_q.put((
            (target, root_parent, root_name, root_depth, "folder",
             0, rmtime, None, None, None, None, remote_name,
             scan_id, root_extra, root_interp, None),
            (scan_id, target, "folder", 0, rmtime,
             None, None, None, None, root_extra),
        ))
        with stats_lock:
            stats["dirs"] += 1

        # Folder rows
        for it in folders:
            rel_path = it.get('Path', '')
            full_path = _rc_join(target, rel_path) if rel_path else target
            parent_path = _rc_parent(full_path)
            name = it.get('Name', rel_path.rsplit('/', 1)[-1])
            depth = _rc_depth(full_path)

            # Detect pattern from children in the same flat listing
            # (only direct children whose path starts with rel_path + '/')
            child_names = []
            prefix = (rel_path + '/') if rel_path else ''
            for child in items:
                cp = child.get('Path', '')
                if cp.startswith(prefix):
                    remainder = cp[len(prefix):]
                    if '/' not in remainder:
                        child_names.append(child.get('Name', remainder))
            pattern = _detect_dir_pattern(child_names)
            extra   = _json.dumps({"pattern": pattern}) if pattern else None
            interp  = interpreter_for_dir_pattern(pattern)

            # mtime: rclone may omit it for dirs even without --no-modtime-dirs
            mtime_str = it.get('ModTime')
            try:
                from datetime import datetime as _dt
                mtime = _dt.fromisoformat(
                    mtime_str.replace('Z', '+00:00')).timestamp() if mtime_str else None
            except Exception:
                mtime = None

            write_q.put((
                (full_path, parent_path, name, depth, "folder",
                 0, mtime, None, None, None, None, remote_name,
                 scan_id, extra, interp, None),
                (scan_id, full_path, "folder", 0, mtime,
                 None, None, None, None, extra),
            ))
            with stats_lock:
                stats["dirs"] += 1

        # File rows
        for it in files:
            rel_path = it.get('Path', '')
            full_path = _rc_join(target, rel_path) if rel_path else target
            parent_path = _rc_parent(full_path)
            name = it.get('Name', rel_path.rsplit('/', 1)[-1])
            depth = _rc_depth(full_path)
            size = it.get('Size', 0) or 0
            fext = Path(name).suffix.lower()
            fmime, _ = mimetypes.guess_type(name)

            mtime_str = it.get('ModTime')
            try:
                from datetime import datetime as _dt
                mtime = _dt.fromisoformat(
                    mtime_str.replace('Z', '+00:00')).timestamp() if mtime_str else None
            except Exception:
                mtime = None

            # etag: prefer object ID (stable across renames in Dropbox/Drive),
            # fall back to hash from Hashes dict
            etag = it.get('ID') or None
            ahash = None
            hashes = it.get('Hashes') or {}
            if not etag:
                # no object ID — use first available hash as etag
                etag = next(iter(hashes.values()), None)
            else:
                # have object ID; pick a hash if present
                ahash = hashes.get('MD5') or hashes.get('SHA-1') or next(iter(hashes.values()), None)

            # interpreter detection (no magic bytes possible for remote files)
            interp = _detect_interpreter(fext, None, None)
            ij = None

            with stats_lock:
                stats["files"] += 1
                stats["bytes"] += size
                if interp:
                    stats["identified"] += 1
                else:
                    stats["gaps"] += 1

            write_q.put((
                (full_path, parent_path, name, depth, "file",
                 size, mtime, fext, fmime, etag, ahash, remote_name,
                 scan_id, None, interp, ij),
                (scan_id, full_path, "file", size, mtime,
                 fext, fmime, etag, ahash, None),
            ))

    except Exception as exc:
        print(f"\\n[fatal] rclone walk failed: {exc}", file=sys.stderr)
        writer_error.append(exc)
    finally:
        write_q.put(_STOP)
        writer.join()

    _abort_on_writer_error(writer_error)
    return stats

'''

PROVIDER_ARG = '''
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


def apply_patch(filepath: str) -> None:
    with open(filepath) as f:
        src = f.read()

    original = src
    changes = []

    # ── 1. Add stdlib imports: socket, shutil ──────────────────────────────
    if 'import socket' not in src:
        src = src.replace('import os\n', 'import os\nimport shutil\nimport socket\n', 1)
        if 'import socket' not in src:
            src = re.sub(r'^(import \w+\n)', r'\1import shutil\nimport socket\n',
                         src, count=1, flags=re.MULTILINE)
        changes.append('+ import socket, shutil')

    # ── 2. Fix remote=None → socket.getfqdn() in local file_row ──────────
    # _make_file_rows builds file_row with remote=None at position 11
    OLD_FILE_ROW = (
        '    file_row = (fpath, dir_path, fname, fdepth, "file", fsize, fmtime,\n'
        '                fext, fmime, None, fhash, None, scan_id, None, interp, ij)'
    )
    NEW_FILE_ROW = (
        '    _local_remote = socket.getfqdn()\n'
        '    file_row = (fpath, dir_path, fname, fdepth, "file", fsize, fmtime,\n'
        '                fext, fmime, None, fhash, _local_remote, scan_id, None, interp, ij)'
    )
    if 'None, fhash, None, scan_id' in src and '_local_remote' not in src:
        src = src.replace(OLD_FILE_ROW, NEW_FILE_ROW, 1)
        changes.append('+ remote=socket.getfqdn() in _make_file_rows file_row')

    # ── 3. Fix remote=None in folder rows inside _walk_subtree ────────────
    # Two occurrences: one in _walk_subtree, one in walk_path (root dir row)
    OLD_FOLDER_ROW = (
        '        write_q.put((\n'
        '            (dp, dparent, dname, ddepth, "folder", 0, dmtime,\n'
        '             None, None, None, None, None, scan_id, dextra, dinterp, None),\n'
        '            (scan_id, dp, "folder", 0, dmtime, None, None, None, None, dextra),\n'
        '        ))'
    )
    NEW_FOLDER_ROW = (
        '        write_q.put((\n'
        '            (dp, dparent, dname, ddepth, "folder", 0, dmtime,\n'
        '             None, None, None, None, socket.getfqdn(), scan_id, dextra, dinterp, None),\n'
        '            (scan_id, dp, "folder", 0, dmtime, None, None, None, None, dextra),\n'
        '        ))'
    )
    if OLD_FOLDER_ROW in src:
        src = src.replace(OLD_FOLDER_ROW, NEW_FOLDER_ROW, 1)
        changes.append('+ remote=socket.getfqdn() in _walk_subtree folder row')

    # ── 4. Fix remote=None in root directory row inside walk_path ─────────
    OLD_ROOT_ROW = (
        '    write_q.put((\n'
        '        (root_str, str(root_path.parent), root_path.name or root_str,\n'
        '         root_depth, "folder", 0, rmtime,\n'
        '         None, None, None, None, None, scan_id, root_extra, root_interp, None),\n'
        '        (scan_id, root_str, "folder", 0, rmtime,\n'
        '         None, None, None, None, root_extra),\n'
        '    ))'
    )
    NEW_ROOT_ROW = (
        '    write_q.put((\n'
        '        (root_str, str(root_path.parent), root_path.name or root_str,\n'
        '         root_depth, "folder", 0, rmtime,\n'
        '         None, None, None, None, socket.getfqdn(), scan_id, root_extra, root_interp, None),\n'
        '        (scan_id, root_str, "folder", 0, rmtime,\n'
        '         None, None, None, None, root_extra),\n'
        '    ))'
    )
    if OLD_ROOT_ROW in src:
        src = src.replace(OLD_ROOT_ROW, NEW_ROOT_ROW, 1)
        changes.append('+ remote=socket.getfqdn() in walk_path root folder row')

    # ── 5. Insert rclone helpers + walk_rclone() before the Gap report ────
    if 'def walk_rclone(' not in src:
        insertion_marker = '# ─────────────────────────────────────────────────────────────────────────────\n# Gap report'
        if insertion_marker in src:
            src = src.replace(insertion_marker,
                              RCLONE_HELPERS + insertion_marker, 1)
            changes.append('+ _rc_depth/_rc_parent/_rc_join/_rclone_run/walk_rclone()')
        else:
            print("WARNING: could not find gap-report section to insert walk_rclone(); add manually.")

    # ── 6. Add --provider argument to argparse (after --quiet) ────────────
    if '--provider' not in src:
        src = src.replace(
            "    parser.add_argument('--quiet', action='store_true')",
            "    parser.add_argument('--quiet', action='store_true')" + PROVIDER_ARG,
            1,
        )
        # argparse may use double quotes
        if '--provider' not in src:
            src = src.replace(
                '    parser.add_argument("--quiet", action="store_true")',
                '    parser.add_argument("--quiet", action="store_true")' + PROVIDER_ARG,
                1,
            )
        if '--provider' not in src:
            print("WARNING: could not find --quiet argument; add --provider manually near other add_argument calls.")
        else:
            changes.append('+ --provider {local,rclone} argparse argument')

    # ── 7. Dispatch in main() based on --provider ─────────────────────────
    # Replace the existing block that calls walk_path() so rclone branches
    DISPATCH_OLD = (
        '    t0 = time.time()\n'
        '    try:\n'
        '        stats = walk_path(\n'
        '            root, scan_id, conn,\n'
        '            workers=args.workers,\n'
        '            do_hash=not args.no_hash,\n'
        '            hash_limit_bytes=args.hash_limit * 1024 * 1024,\n'
        '            magic_limit_bytes=args.magic_limit * 1024 * 1024,\n'
        '            max_depth=args.depth,\n'
        '            excludes=args.exclude,\n'
        '            follow_symlinks=args.follow_symlinks,\n'
        '            quiet=args.quiet,\n'
        '        )'
    )
    DISPATCH_NEW = (
        '    t0 = time.time()\n'
        '    try:\n'
        '        if getattr(args, "provider", "local") == "rclone":\n'
        '            # rclone path: args.root is the rclone target (e.g. dropbox:)\n'
        '            stats = walk_rclone(\n'
        '                args.root, scan_id, conn,\n'
        '                max_depth=args.depth,\n'
        '                do_hash=not args.no_hash,\n'
        '                quiet=args.quiet,\n'
        '            )\n'
        '        else:\n'
        '            stats = walk_path(\n'
        '                root, scan_id, conn,\n'
        '                workers=args.workers,\n'
        '                do_hash=not args.no_hash,\n'
        '                hash_limit_bytes=args.hash_limit * 1024 * 1024,\n'
        '                magic_limit_bytes=args.magic_limit * 1024 * 1024,\n'
        '                max_depth=args.depth,\n'
        '                excludes=args.exclude,\n'
        '                follow_symlinks=args.follow_symlinks,\n'
        '                quiet=args.quiet,\n'
        '            )'
    )
    if 'walk_rclone' not in src or 'getattr(args, "provider"' not in src:
        if DISPATCH_OLD in src:
            src = src.replace(DISPATCH_OLD, DISPATCH_NEW, 1)
            changes.append('+ provider dispatch in main()')
        else:
            print("WARNING: could not find walk_path() call block in main() to add dispatch; add manually.")

    # ── 8. Fix validation: rclone target doesn't need to be a local dir ───
    OLD_DIR_CHECK = (
        '    root = str(Path(args.root).resolve())\n'
        '    if not os.path.isdir(root):\n'
        '        print(f"Error: \'{root}\' is not a directory.", file=sys.stderr)\n'
        '        sys.exit(1)'
    )
    NEW_DIR_CHECK = (
        '    if getattr(args, "provider", "local") == "rclone":\n'
        '        root = args.root  # rclone target, not a local path\n'
        '        # Verify rclone binary present\n'
        '        if not shutil.which("rclone"):\n'
        '            print("Error: rclone not found on PATH.", file=sys.stderr)\n'
        '            sys.exit(1)\n'
        '    else:\n'
        '        root = str(Path(args.root).resolve())\n'
        '        if not os.path.isdir(root):\n'
        '            print(f"Error: \'{root}\' is not a directory.", file=sys.stderr)\n'
        '            sys.exit(1)'
    )
    if OLD_DIR_CHECK in src and 'rclone not found on PATH' not in src:
        src = src.replace(OLD_DIR_CHECK, NEW_DIR_CHECK, 1)
        changes.append('+ rclone target validation / skip local dir check')

    # ── 9. Show provider in startup banner ────────────────────────────────
    OLD_BANNER = '        print(f"\\nSciDK Filesystem Scanner")'
    NEW_BANNER = (
        '        provider_label = getattr(args, "provider", "local")\n'
        '        print(f"\\nSciDK Filesystem Scanner  [{provider_label}]")'
    )
    if OLD_BANNER in src and 'provider_label' not in src:
        src = src.replace(OLD_BANNER, NEW_BANNER, 1)
        changes.append('+ provider label in startup banner')

    # ── Write result ───────────────────────────────────────────────────────
    if src == original:
        print("No changes made — file may already be patched, or patterns did not match.")
        return

    with open(filepath, 'w') as f:
        f.write(src)

    print(f"Patched {filepath} successfully.")
    print("Changes applied:")
    for c in changes:
        print(f"  {c}")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"Usage: python3 {sys.argv[0]} /path/to/scidk_scanner_opt.py")
        sys.exit(1)
    apply_patch(sys.argv[1])
