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
    # Intercept wrapper-provided helpers before delegating to submodule
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd in ("doctor", "sync-dev"):
            dev_path = os.path.join(repo_root, 'dev')
            # Ensure submodule exists/initialized
            _try_submodule_sync(repo_root)
            if cmd == "sync-dev":
                try:
                    r = subprocess.run(['git', 'submodule', 'update', '--init', '--remote', '--merge', 'dev'], cwd=repo_root)
                    if r.returncode == 0:
                        print("✅ dev submodule updated to latest remote (pointer not auto-committed).")
                    else:
                        print("⚠️ Failed to update dev submodule; try: git submodule sync && git submodule update --init --remote --merge dev")
                except Exception as e:
                    print(f"⚠️ sync-dev error: {e}")
                return
            if cmd == "doctor":
                info = {"dev_present": os.path.isdir(dev_path), "dev_is_git": False, "branch": None, "detached": None, "unpushed": None}
                if info["dev_present"]:
                    try:
                        chk = subprocess.run(['git', '-C', dev_path, 'rev-parse', '--is-inside-work-tree'], capture_output=True, text=True)
                        info["dev_is_git"] = (chk.returncode == 0 and (chk.stdout or '').strip() == 'true')
                        if info["dev_is_git"]:
                            b = subprocess.run(['git', '-C', dev_path, 'rev-parse', '--abbrev-ref', 'HEAD'], capture_output=True, text=True)
                            info["branch"] = (b.stdout or '').strip()
                            info["detached"] = (info["branch"] == 'HEAD')
                            subprocess.run(['git', '-C', dev_path, 'remote', 'update'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            ch = subprocess.run(['git', '-C', dev_path, 'cherry', '-v'], capture_output=True, text=True)
                            info["unpushed"] = bool((ch.stdout or '').strip())
                    except Exception:
                        pass
                print("🔎 dev/ doctor:\n" + __import__('json').dumps(info, indent=2))
                if info.get("dev_is_git") and info.get("detached"):
                    print("Hint: git -C dev checkout main && git -C dev pull --ff-only")
                if info.get("dev_is_git") and info.get("unpushed"):
                    print("Hint: git -C dev push")
                return
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
