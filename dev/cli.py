#!/usr/bin/env python3
"""
Dev CLI - Turn the crank development workflow
Usage: python dev_cli.py <command> [args]
"""
import sys
import os
import re
import yaml
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Iterable


def _is_yaml_kv_line(line: str) -> bool:
    # Accept key: value or key: (block start) ignoring leading spaces
    # Empty lines are NOT considered part of the YAML header sentinel for our parser
    if not line.strip():
        return False
    if line.lstrip().startswith('#'):
        return False
    return bool(re.match(r"^[A-Za-z0-9_\-]+:\s*.*$", line.strip()))


class DevCLI:
    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root).resolve()
        self.dev_dir = self.repo_root / "dev"
        self.tasks_dir = self.dev_dir / "tasks"
        self.cycles_file = self.dev_dir / "cycles.md"
        # Default base to compare merges against
        self.default_base_branches = [
            os.environ.get('SCIDK_BASE_BRANCH') or '',
            'origin/main', 'main', 'origin/master', 'master'
        ]

    def _pick_base_branch(self) -> Optional[str]:
        """Pick the first base branch that exists locally or remotely."""
        try:
            # fetch refs quietly (ignore errors if offline)
            subprocess.run("git fetch --all --prune -q", shell=True)
        except Exception:
            pass
        for cand in self.default_base_branches:
            if not cand:
                continue
            res = subprocess.run(f"git rev-parse --verify {sh_quote(cand)}", shell=True)
            if res.returncode == 0:
                return cand
        return None

    def merge_safety(self, base: Optional[str] = None) -> Dict:
        """Report potentially destructive changes versus a base branch.
        Returns a dict with summary and detailed lists (also printed human-readable).
        """
        base_branch = base or self._pick_base_branch()
        if not base_branch:
            print("⚠️ Could not determine a base branch (try setting SCIDK_BASE_BRANCH).")
            return {"error": "no_base"}
        print(f"🔎 Comparing against base: {base_branch}")
        # Deleted files
        try:
            res = subprocess.run(f"git diff --name-status {sh_quote(base_branch)}...HEAD", shell=True, capture_output=True, text=True)
            lines = res.stdout.strip().splitlines() if res.stdout else []
        except Exception as e:
            print(f"⚠️ git diff failed: {e}")
            return {"error": "git_diff_failed"}
        deleted = [ln.split('\t', 1)[1] for ln in lines if ln.startswith('D\t') and '\t' in ln]
        # Count added/removed lines overall and by file
        try:
            res2 = subprocess.run(f"git diff --numstat {sh_quote(base_branch)}...HEAD", shell=True, capture_output=True, text=True)
            stats_lines = res2.stdout.strip().splitlines() if res2.stdout else []
        except Exception:
            stats_lines = []
        file_stats = []
        total_add = 0
        total_del = 0
        for ln in stats_lines:
            parts = ln.split('\t')
            if len(parts) >= 3:
                try:
                    add = int(parts[0]) if parts[0].isdigit() else 0
                    dele = int(parts[1]) if parts[1].isdigit() else 0
                except Exception:
                    add = 0; dele = 0
                path = parts[2]
                total_add += add
                total_del += dele
                file_stats.append({"path": path, "added": add, "deleted": dele})
        risky_paths = ['scidk/app.py', 'scidk/ui/templates', 'scidk/core', 'scidk/interpreters']
        risky_deletions = [fs for fs in file_stats if fs['deleted'] >= 50 or any(fs['path'].startswith(p) for p in risky_paths)]
        summary = {
            "base": base_branch,
            "deleted_files": len(deleted),
            "total_added": total_add,
            "total_deleted": total_del,
            "risky_files": len(risky_deletions),
        }
        # Print human-readable report
        print("\n🛡️ Merge Safety Report")
        print("=" * 40)
        print(f"Base: {base_branch}")
        print(f"Deleted files: {len(deleted)}")
        if deleted:
            for p in deleted[:25]:
                print(f"  D {p}")
            if len(deleted) > 25:
                print(f"  ... and {len(deleted) - 25} more")
        print(f"Total lines: +{total_add} / -{total_del}")
        if risky_deletions:
            print("\nPotentially risky deletions (threshold 50 lines or key paths):")
            for fs in risky_deletions[:25]:
                print(f"  - {fs['path']}: -{fs['deleted']} (+{fs['added']})")
            if len(risky_deletions) > 25:
                print(f"  ... and {len(risky_deletions) - 25} more")
        print("\nGuidance:")
        print(" - If you see unexpected deletions, review other active branches for those files.")
        print(" - Use 'git log --oneline -- <path>' on base and current to trace recent additions.")
        print(" - Prefer cherry-pick of granular commits rather than bulk conflict resolution that deletes blocks.")
        print(" - Ask a reviewer before removing large blocks in app/core/ui/interpreters.")
        return {
            "summary": summary,
            "deleted_files": deleted,
            "file_stats": file_stats,
            "risky_deletions": risky_deletions,
        }

    def parse_frontmatter(self, file_path: Path) -> Dict:
        """Parse YAML frontmatter or top-of-file YAML from markdown files.
        Supports both fenced '---' blocks and unfenced YAML headers at top of file.
        """
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return {}

        if not content:
            return {}

        # Case 1: fenced YAML frontmatter
        if content.startswith('---'):
            try:
                # Split only on first two '---' occurrences
                parts = content.split('\n')
                fm_lines: List[str] = []
                if parts and parts[0].strip() == '---':
                    # collect until next ---
                    for i in range(1, len(parts)):
                        if parts[i].strip() == '---':
                            break
                        fm_lines.append(parts[i])
                    fm_text = '\n'.join(fm_lines)
                    data = yaml.safe_load(fm_text) or {}
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass

        # Case 2: unfenced top-of-file YAML block
        try:
            lines = content.splitlines()
            header_lines: List[str] = []
            in_block = True
            for line in lines:
                # Stop if we hit a markdown heading/code fence that likely ends metadata
                if line.startswith('```') or line.startswith('~~~'):
                    break
                if in_block and (_is_yaml_kv_line(line) or (header_lines and line.startswith((' ', '\t', '-')))):
                    header_lines.append(line)
                else:
                    # Stop at first non YAML-ish line after we started header
                    if header_lines:
                        break
                    else:
                        # If very first line isn't YAML-like, give up
                        in_block = False
                        break
            if header_lines:
                # Try to load just the header block
                data = yaml.safe_load('\n'.join(header_lines)) or {}
                if isinstance(data, dict):
                    return data
        except Exception:
            pass

        # Case 3: attempt to parse whole file as YAML (many task files are fully YAML-like)
        try:
            data = yaml.safe_load(content) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        return {}

    # ------------------------
    # Python-native task scan
    # ------------------------
    def _iter_task_files(self) -> Iterable[Path]:
        if not self.tasks_dir.exists():
            return []
        return self.tasks_dir.rglob("*.md")

    def find_task_file(self, task_id: str) -> Optional[Path]:
        """Find task file by ID by scanning and parsing frontmatter."""
        for md in self._iter_task_files():
            data = self.parse_frontmatter(md)
            if isinstance(data, dict) and data.get('id') == task_id:
                return md
        return None

    def get_ready_queue(self) -> List[Dict]:
        """Get tasks with status: Ready, sorted by RICE descending and dor true"""
        ready_tasks: List[Dict] = []
        for md in self._iter_task_files():
            data = self.parse_frontmatter(md)
            if not isinstance(data, dict) or not data:
                continue
            # normalize status
            status_raw = str(data.get('status', '')).strip()
            status = status_raw.lower()
            dor_val = str(data.get('dor', '')).strip().lower() in ('true', '1', 'yes', 'y')
            if status == 'ready' and dor_val:
                data['file_path'] = md
                ready_tasks.append(data)
        # Sort by RICE descending
        def rice_value(x: Dict):
            try:
                return float(x.get('rice', 0))
            except Exception:
                return 0.0
        return sorted(ready_tasks, key=rice_value, reverse=True)

    def validate_dor(self, task_id: str) -> bool:
        """Validate Definition of Ready for a task"""
        task_file = self.find_task_file(task_id)
        if not task_file or not task_file.exists():
            print(f"❌ Task {task_id} not found")
            return False

        task_data = self.parse_frontmatter(task_file)
        if not task_data:
            print(f"❌ Could not parse task file: {task_file}")
            return False

        required_fields = ['id', 'owner', 'estimate', 'story', 'phase', 'acceptance']
        missing = [field for field in required_fields if not task_data.get(field)]

        if missing:
            print(f"❌ DoR Failed - Missing: {', '.join(missing)}")
            return False

        if not task_data.get('dor'):
            print(f"❌ DoR not marked as true")
            return False

        print(f"✅ DoR Validated for {task_id}")
        return True

    def get_task_context_data(self, task_id: str) -> Optional[Dict]:
        task_file = self.find_task_file(task_id)
        if not task_file:
            return None
        data = self.parse_frontmatter(task_file)
        try:
            task_content = task_file.read_text(encoding="utf-8")
        except Exception:
            task_content = "(could not read task file)"
        return {
            "id": task_id,
            "owner": data.get('owner') if isinstance(data, dict) else None,
            "story": data.get('story') if isinstance(data, dict) else None,
            "phase": data.get('phase') if isinstance(data, dict) else None,
            "estimate": data.get('estimate') if isinstance(data, dict) else None,
            "acceptance": data.get('acceptance') if isinstance(data, dict) else None,
            "file_path": str(task_file),
            "content": task_content,
            "branch": f"task/{task_id.replace(':', '-')}"
        }

    def get_task_context(self, task_id: str) -> str:
        """Generate context for AI agent prompting (text)"""
        ctx = self.get_task_context_data(task_id)
        if not ctx:
            return f"Task {task_id} not found"
        context = f"""
TASK: {ctx['id']}
OWNER: {ctx.get('owner')}
STORY: {ctx.get('story')}
PHASE: {ctx.get('phase')}
ESTIMATE: {ctx.get('estimate')}

ACCEPTANCE CRITERIA:
{ctx.get('acceptance')}

FULL TASK SPECIFICATION:
{ctx.get('content')}

CURRENT REPO STATE:
- Branch: {ctx.get('branch')}
- Ready to implement
"""
        return context

    def start_task(self, task_id: str):
        """Start working on a task: validate DoR, create/switch branch, and print context."""
        # 1) Locate task file
        task_file = self.find_task_file(task_id)
        if not task_file or not task_file.exists():
            print(f"❌ Task {task_id} not found")
            return
        # 2) Validate DoR
        if not self.validate_dor(task_id):
            # validate_dor() already prints details
            return
        # 3) Determine branch name
        branch = f"task/{task_id.replace(':', '-')}"
        print(f"🌿 Target branch: {branch}")
        # 4) Try to create/switch branch if this is a git repo
        try:
            # Check if inside a git repo
            res = subprocess.run("git rev-parse --is-inside-work-tree", shell=True, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip() == 'true':
                # Check if branch exists
                chk = subprocess.run(f"git rev-parse --verify {sh_quote(branch)}", shell=True)
                if chk.returncode == 0:
                    subprocess.run(f"git checkout {sh_quote(branch)}", shell=True)
                    print(f"✅ Switched to existing branch {branch}")
                else:
                    subprocess.run(f"git checkout -b {sh_quote(branch)}", shell=True)
                    print(f"✅ Created and switched to {branch}")
            else:
                print("ℹ️ Not a git repository; skipping branch creation.")
        except Exception as e:
            print(f"⚠️ Git operation skipped due to error: {e}")
        # 5) Show context
        print("\n🧭 TASK CONTEXT\n" + "=" * 40)
        print(self.get_task_context(task_id))

        # Mark as In Progress with started_at
        try:
            now = datetime.utcnow().isoformat() + "Z"
            self.update_task_frontmatter(task_id, {"status": "In Progress", "started_at": now}, git_commit=True)
            print(f"\n✍️  Updated task {task_id} → status: In Progress")
        except Exception as e:
            print(f"⚠️ Could not update task status: {e}")

    def complete_task(self, task_id: str):
        """Mark task as complete and validate DoD (lightweight)"""
        print(f"🎯 Completing task: {task_id}")
        # 1) Run tests
        print("🧪 Running tests with project virtual environment preference...")
        try:
            cmds = []
            venv_py = Path('.venv') / 'bin' / 'python'
            if venv_py.exists():
                cmds.append([str(venv_py), '-m', 'pytest', '-q'])
            # Always consider current interpreter next
            cmds.append([sys.executable, '-m', 'pytest', '-q'])
            # As last resort, try pytest from PATH
            cmds.append(['pytest', '-q'])

            last_rc = None
            last_err = None
            for cmd in cmds:
                try:
                    print(f"→ Trying: {' '.join(cmd)}")
                    res = subprocess.run(cmd)
                    last_rc = res.returncode
                    if res.returncode == 0:
                        print("✅ Tests passing")
                        break
                    else:
                        print(f"ℹ️ Command exited with {res.returncode}, trying next fallback if any...")
                except FileNotFoundError as fnf:
                    last_err = str(fnf)
                    print(f"ℹ️ Command not found: {' '.join(cmd)}; trying next fallback...")
                    continue
            else:
                # If loop didn't break (no success)
                if last_rc is not None:
                    print(f"❌ Tests failed (exit {last_rc}) — fix before completing.")
                else:
                    print(f"⚠️ Could not run tests — no suitable interpreter/pytest found. Last error: {last_err}")
        except Exception as e:
            print(f"⚠️ Unexpected error running tests: {e}")
        # 2) Show DoD checklist
        task_file = self.find_task_file(task_id)
        task_data = self.parse_frontmatter(task_file) if task_file else {}
        dod = task_data.get('dod') if isinstance(task_data, dict) else None
        print("\n📋 DoD Checklist (from task frontmatter):")
        if isinstance(dod, list) and dod:
            for item in dod:
                print(f" - [ ] {item}")
        else:
            print(" - [ ] tests\n - [ ] docs\n - [ ] demo_steps")
        print("\nℹ️ Next steps (manual): create PR, ensure demo steps are documented, merge when CI is green.")

        # If tests passed, mark Done
        try:
            tests_ok = False
            # rely on a quick rerun to assert tests are passing now
            try:
                res = subprocess.run([sys.executable, '-m', 'pytest', '-q'])
                tests_ok = (res.returncode == 0)
            except Exception:
                tests_ok = False
            if tests_ok:
                now = datetime.utcnow().isoformat() + "Z"
                self.update_task_frontmatter(task_id, {"status": "Done", "completed_at": now}, git_commit=True)
                print(f"\n✅ Marked task {task_id} as Done.")
            else:
                print("\n⏸️  Skipping status update to Done because tests did not pass just now.")
        except Exception as e:
            print(f"⚠️ Could not update task status: {e}")

    def cycle_status(self):
        """Show current cycle status (lightweight)"""
        if not self.cycles_file.exists():
            print("cycles.md not found")
            return
        cycles_content = self.cycles_file.read_text(encoding="utf-8")

        print("📊 CURRENT CYCLE STATUS")
        print("=" * 40)

        story_match = re.search(r'Active Story/Phase: (story:[^—\n]+) — (phase:[^\n]+)', cycles_content)
        if story_match:
            print(f"📖 Active Story: {story_match.group(1)}")
            print(f"🧩 Active Phase: {story_match.group(2)}")
        else:
            story_only = re.search(r'Active Story: (story:[^\n]+)', cycles_content)
            if story_only:
                print(f"📖 Active Story: {story_only.group(1)}")

        print("\n🎯 SELECTED TASKS: (see cycles.md)")

    def next_cycle(self):
        """Propose next cycle from ready queue"""
        ready = self.get_ready_queue()

        print("🔄 PROPOSED NEXT CYCLE")
        print("=" * 40)

        print("\nTop 5 Ready Tasks:")
        for i, task in enumerate(ready[:5], 1):
            rid = task.get('id', '(unknown)')
            rice = task.get('rice', 0)
            print(f"{i}. {rid} (RICE: {rice})")
            acc = task.get('acceptance', 'No acceptance criteria')
            acc_str = str(acc)
            print(f"   {acc_str[:80]}...")
            print()

    # ------------------------
    # Frontmatter write helper
    # ------------------------
    def update_task_frontmatter(self, task_id: str, updates: Dict, git_commit: bool = True) -> None:
        """Safely merge and rewrite YAML frontmatter for a task file.
        Always writes a fenced YAML frontmatter at top and preserves the rest of the file body.
        """
        task_file = self.find_task_file(task_id)
        if not task_file or not task_file.exists():
            raise FileNotFoundError(f"Task {task_id} not found")

        text = task_file.read_text(encoding="utf-8")

        def dump_yaml(d: Dict) -> str:
            return yaml.safe_dump(d or {}, sort_keys=False).strip() + "\n"

        # Parse existing metadata using reader (robust to styles)
        try:
            cur = self.parse_frontmatter(task_file) or {}
        except Exception:
            cur = {}
        if not isinstance(cur, dict):
            cur = {}
        cur.update(updates or {})

        # Compute the remaining body content by stripping any existing frontmatter/header
        body = text
        if text.startswith('---'):
            lines = text.splitlines()
            end_idx = None
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    end_idx = i
                    break
            body = "\n".join(lines[end_idx+1:]) if (end_idx is not None and end_idx + 1 < len(lines)) else ""
        else:
            # Try to detect unfenced header and cut it off
            lines = text.splitlines()
            header_lines = []
            body_start = 0
            in_header = True
            for idx, line in enumerate(lines):
                if line.startswith('```') or line.startswith('~~~'):
                    body_start = idx
                    break
                if in_header and (_is_yaml_kv_line(line) or (header_lines and line.startswith((' ', '\t', '-')))):
                    header_lines.append(line)
                    continue
                if header_lines:
                    body_start = idx
                    break
                else:
                    in_header = False
                    body_start = 0
                    break
            if header_lines:
                # If the whole file is YAML-like (no clear boundary), treat it as pure metadata
                if body_start == 0 and len(header_lines) == len(lines):
                    body = ""
                else:
                    body = "\n".join(lines[body_start:])
            else:
                body = text

        new_fm = dump_yaml(cur)
        new_text = f"---\n{new_fm}---\n" + body.lstrip('\n')
        task_file.write_text(new_text, encoding="utf-8")

        if git_commit:
            try:
                res = subprocess.run("git rev-parse --is-inside-work-tree", shell=True, capture_output=True, text=True)
                if res.returncode == 0 and (res.stdout or '').strip() == 'true':
                    rel = os.path.relpath(str(task_file), start=str(self.repo_root))
                    subprocess.run(f"git add {sh_quote(rel)}", shell=True)
                    msg = f"chore(task): update frontmatter {task_id}"
                    subprocess.run(f"git commit -m {sh_quote(msg)}", shell=True)
            except Exception:
                pass


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def main():
    if len(sys.argv) < 2:
        print("Usage: python dev_cli.py <command> [args]")
        print("\nCommands:")
        print("  ready-queue      - Show ready tasks sorted by RICE")
        print("  start [<task>]   - Start working on a task (defaults to top Ready)")
        print("  context <task>   - Get AI context for a task")
        print("  validate <task>  - Validate DoR for a task")
        print("  complete <task>  - Run DoD checks and summarize next steps")
        print("  cycle-status     - Show current cycle")
        print("  next-cycle       - Propose next cycle")
        print("  merge-safety     - Report potentially risky deletions vs base (use --base <branch> to override)")
        return

    # Extract global flags (very light parser)
    argv = sys.argv[:]
    command = argv[1]
    json_flag = False
    base_override = None
    if '--json' in argv:
        json_flag = True
        argv.remove('--json')
    # simple flag parse for --base <branch>
    if '--base' in argv:
        try:
            idx = argv.index('--base')
            base_override = argv[idx + 1]
            del argv[idx:idx + 2]
        except Exception:
            base_override = None

    cli = DevCLI()

    if command == "ready-queue":
        ready = cli.get_ready_queue()
        if json_flag:
            out = []
            for t in ready:
                out.append({
                    "id": t.get('id'),
                    "title": t.get('title'),
                    "status": t.get('status'),
                    "rice": t.get('rice'),
                    "estimate": t.get('estimate'),
                    "owner": t.get('owner'),
                    "story": t.get('story'),
                    "phase": t.get('phase'),
                    "file_path": str(t.get('file_path')) if t.get('file_path') else None,
                    "tags": t.get('tags'),
                })
            print(json.dumps(out, indent=2))
        else:
            print("📋 READY QUEUE (DoR ✅)")
            print("=" * 40)
            for i, task in enumerate(ready, 1):
                rid = task.get('id', '(unknown)')
                rice = task.get('rice', 0)
                owner = task.get('owner')
                est = task.get('estimate')
                print(f"{i}. {rid} (RICE: {rice})")
                print(f"   Owner: {owner} | Est: {est}")
                acc = task.get('acceptance', '')
                print(f"   {str(acc)[:80]}...")
                print()

    elif command == "start":
        # Allow start without explicit task id -> pick top Ready
        task_id = None
        if len(argv) > 2:
            task_id = argv[2]
        else:
            ready = cli.get_ready_queue()
            if not ready:
                print("No Ready tasks found.")
                return
            task_id = ready[0].get('id')
            print(f"(auto-selected top Ready task) -> {task_id}")
        cli.start_task(task_id)

    elif command == "context" and len(argv) > 2:
        tid = argv[2]
        if json_flag:
            ctx = cli.get_task_context_data(tid)
            if ctx is None:
                print(json.dumps({"error": f"Task {tid} not found"}))
            else:
                print(json.dumps(ctx, indent=2))
        else:
            context = cli.get_task_context(tid)
            print(context)

    elif command == "validate" and len(argv) > 2:
        tid = argv[2]
        if json_flag:
            # Re-run checks but emit structured response
            task_file = cli.find_task_file(tid)
            ok = False
            missing = []
            error = None
            if not task_file or not task_file.exists():
                error = "not_found"
            else:
                data = cli.parse_frontmatter(task_file)
                if not data:
                    error = "parse_error"
                else:
                    req = ['id', 'owner', 'estimate', 'story', 'phase', 'acceptance']
                    missing = [f for f in req if not data.get(f)]
                    if not data.get('dor'):
                        missing.append('dor')
                    ok = len(missing) == 0
            print(json.dumps({"id": tid, "ok": ok, "missing": missing, "error": error}, indent=2))
        else:
            cli.validate_dor(tid)

    elif command == "cycle-status":
        if json_flag:
            # Minimal JSON: parse active story/phase from cycles.md
            result = {"active_story": None, "active_phase": None}
            if cli.cycles_file.exists():
                txt = cli.cycles_file.read_text(encoding='utf-8')
                m = re.search(r'Active Story/Phase: (story:[^—\n]+) — (phase:[^\n]+)', txt)
                if m:
                    result["active_story"] = m.group(1)
                    result["active_phase"] = m.group(2)
                else:
                    m2 = re.search(r'Active Story: (story:[^\n]+)', txt)
                    if m2:
                        result["active_story"] = m2.group(1)
            print(json.dumps(result, indent=2))
        else:
            cli.cycle_status()

    elif command == "next-cycle":
        ready = cli.get_ready_queue()
        if json_flag:
            top = []
            for i, t in enumerate(ready[:5], 1):
                top.append({
                    "rank": i,
                    "id": t.get('id'),
                    "rice": t.get('rice'),
                    "owner": t.get('owner'),
                })
            print(json.dumps({"top_ready": top}, indent=2))
        else:
            cli.next_cycle()

    elif command == "complete" and len(argv) > 2:
        cli.complete_task(argv[2])

    elif command == "merge-safety":
        res = cli.merge_safety(base_override)
        if json_flag:
            print(json.dumps(res, indent=2, default=str))

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
