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
    if not line.strip():
        return True
    if line.lstrip().startswith('#'):
        return False
    return bool(re.match(r"^[A-Za-z0-9_\-]+:\s*.*$", line.strip()))


class DevCLI:
    def __init__(self, repo_root: str = "."):
        self.repo_root = Path(repo_root).resolve()
        self.dev_dir = self.repo_root / "dev"
        self.tasks_dir = self.dev_dir / "tasks"
        self.cycles_file = self.dev_dir / "cycles.md"

    # ------------------------
    # Frontmatter read/write
    # ------------------------
    def _detect_frontmatter_block(self, content: str) -> Tuple[Optional[int], Optional[int], bool]:
        """Return (start_line, end_line, fenced) for existing frontmatter block.
        - fenced: content starts with '---' and ends at the next '---' line (exclusive end index).
        - unfenced: best-effort detection of top-of-file YAML-ish lines.
        If not found, returns (None, None, False).
        """
        lines = content.splitlines()
        if not lines:
            return None, None, False
        # Case 1: fenced
        if lines[0].strip() == '---':
            for i in range(1, len(lines)):
                if lines[i].strip() == '---':
                    return 0, i, True
            # Unclosed fence: treat as no block
        # Case 2: unfenced top-of-file YAML-ish
        header_lines: List[str] = []
        started = False
        for idx, line in enumerate(lines):
            if line.startswith('```') or line.startswith('~~~'):
                break
            if _is_yaml_kv_line(line) or (header_lines and line.startswith((' ', '\t', '-'))):
                header_lines.append(line)
                started = True
            else:
                if started:
                    end = idx - 1
                    if end >= 0 and header_lines:
                        return 0, end, False
                break
        if header_lines:
            return 0, len(header_lines) - 1, False
        return None, None, False

    def update_frontmatter(self, file_path: Path, updates: Dict, create_if_missing: bool = True) -> bool:
        """Update or create a frontmatter block with provided key/values.
        Preserves the rest of the file content. Returns True on success.
        """
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception:
            return False
        start, end, fenced = self._detect_frontmatter_block(content)
        lines = content.splitlines()
        existing: Dict = {}
        if start is not None and end is not None:
            fm_text = '\n'.join(lines[start + (1 if fenced else 0): end + 1]) if (end >= start) else ''
            try:
                existing = yaml.safe_load(fm_text) or {}
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}
        # Merge
        merged = dict(existing)
        merged.update(updates or {})
        # Stable YAML dump (no aliases, reasonable formatting)
        new_yaml = yaml.safe_dump(merged, sort_keys=False).strip() + '\n'
        if start is None or end is None:
            if not create_if_missing:
                return False
            new_block = ['---', new_yaml.rstrip('\n'), '---', '']
            new_content = '\n'.join(new_block + lines)
        else:
            if fenced:
                new_block = ['---', new_yaml.rstrip('\n'), '---']
                new_content = '\n'.join(lines[:start] + new_block + lines[end + 1:])
            else:
                # Replace lines[start:end]
                new_block_lines = new_yaml.rstrip('\n').splitlines()
                new_content = '\n'.join(lines[:start] + new_block_lines + lines[end + 1:])
        try:
            file_path.write_text(new_content, encoding='utf-8')
            return True
        except Exception:
            return False

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
        """Get tasks with status: Ready, sorted by RICE descending and dor true.
        If none found, fall back to dev/tasks/index.md ready_queue ordering.
        """
        ready_tasks: List[Dict] = []
        for md in self._iter_task_files():
            data = self.parse_frontmatter(md)
            if not isinstance(data, dict) or not data:
                continue
            status = str(data.get('status', '')).strip()
            dor_val = str(data.get('dor', '')).strip().lower() in ('true', '1', 'yes', 'y')
            if status == 'Ready' and dor_val:
                data['file_path'] = md
                ready_tasks.append(data)
        # Sort by RICE descending
        def rice_value(x: Dict):
            try:
                return float(x.get('rice', 0))
            except Exception:
                return 0.0
        sorted_ready = sorted(ready_tasks, key=rice_value, reverse=True)
        if sorted_ready:
            return sorted_ready
        # Fallback: parse dev/tasks/index.md ready_queue
        index_md = self.tasks_dir / 'index.md'
        if not index_md.exists():
            return []
        try:
            txt = index_md.read_text(encoding='utf-8')
        except Exception:
            return []
        # Extract YAML code block fenced with ```yaml ... ```
        m = re.search(r"```yaml\n(.*?)\n```", txt, re.DOTALL | re.IGNORECASE)
        if not m:
            return []
        try:
            block = yaml.safe_load(m.group(1)) or {}
        except Exception:
            return []
        rq = block.get('ready_queue') if isinstance(block, dict) else None
        if not isinstance(rq, list):
            return []
        # Build list, preserving order from index.md
        fallback_tasks: List[Dict] = []
        for item in rq:
            if not isinstance(item, dict):
                continue
            tid = item.get('id')
            if not tid:
                continue
            tdata: Dict = {'id': tid}
            # try enrich from actual task file if exists
            tf = self.find_task_file(tid)
            if tf:
                pdata = self.parse_frontmatter(tf) or {}
                if isinstance(pdata, dict):
                    tdata.update(pdata)
                    tdata['file_path'] = tf
            # rice from index has priority for ordering
            if 'rice' not in tdata and 'rice' in item:
                tdata['rice'] = item.get('rice')
            else:
                # still prefer index value when present
                if 'rice' in item:
                    tdata['rice'] = item.get('rice')
            fallback_tasks.append(tdata)
        return fallback_tasks

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
        """Start working on a task: validate DoR, create/switch branch, persist status, and print context."""
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
        # 5) Persist status to frontmatter
        ts = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        ok = self.update_frontmatter(task_file, {
            'status': 'In Progress',
            'started_at': ts,
            'branch': branch,
        }, create_if_missing=True)
        if ok:
            print(f"📝 Updated task frontmatter: status=In Progress, started_at={ts}, branch={branch}")
        else:
            print("⚠️ Failed to update task frontmatter")
        # 6) Show context
        print("\n🧭 TASK CONTEXT\n" + "=" * 40)
        print(self.get_task_context(task_id))

    def complete_task(self, task_id: str):
        """Mark task as complete: run tests, persist status, and show DoD checklist."""
        print(f"🎯 Completing task: {task_id}")
        # 1) Run tests
        print("🧪 Running tests (pytest -q)...")
        tests_passed = False
        try:
            res = subprocess.run("pytest -q", shell=True)
            tests_passed = (res.returncode == 0)
            if tests_passed:
                print("✅ Tests passing")
            else:
                print(f"❌ Tests failed (exit {res.returncode}) — fix before completing.")
        except Exception as e:
            print(f"⚠️ Could not run tests: {e}")
        # 2) Persist status to frontmatter
        task_file = self.find_task_file(task_id)
        if not task_file:
            print("❌ Task file not found; cannot update status")
        else:
            ts = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
            updates = {
                'status': 'Done',
                'completed_at': ts,
                'tests_passed': bool(tests_passed),
            }
            ok = self.update_frontmatter(task_file, updates, create_if_missing=True)
            if ok:
                print(f"📝 Updated task frontmatter: status=Done, completed_at={ts}, tests_passed={tests_passed}")
            else:
                print("⚠️ Failed to update task frontmatter")
        # 3) Show DoD checklist
        task_data = self.parse_frontmatter(task_file) if task_file else {}
        dod = task_data.get('dod') if isinstance(task_data, dict) else None
        print("\n📋 DoD Checklist (from task frontmatter):")
        if isinstance(dod, list) and dod:
            for item in dod:
                print(f" - [ ] {item}")
        else:
            print(" - [ ] tests\n - [ ] docs\n - [ ] demo_steps")
        print("\nℹ️ Next steps (manual): create PR, ensure demo steps are documented, merge when CI is green.")

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


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def main():
    if len(sys.argv) < 2:
        print("Usage: python dev_cli.py <command> [args]")
        print("\nCommands:")
        print("  ready-queue            - Show ready tasks sorted by RICE")
        print("  start [<task>]         - Start working on a task; persists status=In Progress")
        print("  context <task>         - Get AI context for a task")
        print("  validate <task>        - Validate DoR for a task")
        print("  complete <task>        - Run tests and mark status=Done with timestamps")
        print("  mark <task> <status>   - Manually set task status (adds timestamps for Done/In Progress)")
        print("  backfill-status        - Add default status to tasks missing it (Ready/Backlog/Draft)")
        print("  cycle-status           - Show current cycle")
        print("  next-cycle             - Propose next cycle")
        return

    # Extract global flags (very light parser)
    argv = sys.argv[:]
    command = argv[1]
    json_flag = False
    if '--json' in argv:
        json_flag = True
        argv.remove('--json')

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

    elif command == "mark" and len(argv) > 3:
        tid = argv[2]
        status = ' '.join(argv[3:]).strip()
        task_file = cli.find_task_file(tid)
        if not task_file:
            print(f"❌ Task {tid} not found")
            return
        updates = {'status': status}
        now = datetime.utcnow().isoformat(timespec='seconds') + 'Z'
        # convenience timestamps
        if status.lower() in ('in progress', 'in-progress', 'started'):
            updates['status'] = 'In Progress'
            updates['started_at'] = now
        elif status.lower() in ('done', 'complete', 'completed'):
            updates['status'] = 'Done'
            updates['completed_at'] = now
        ok = cli.update_frontmatter(task_file, updates, create_if_missing=True)
        if ok:
            print(f"📝 Updated {tid}: {updates}")
        else:
            print("⚠️ Failed to update task frontmatter")

    elif command == "backfill-status":
        changed = 0
        scanned = 0
        for md in cli._iter_task_files():
            scanned += 1
            data = cli.parse_frontmatter(md) or {}
            status = str(data.get('status', '')).strip()
            if not status:
                # Heuristics to set defaults
                if str(data.get('dor', '')).strip().lower() in ('true', '1', 'yes', 'y'):
                    new_status = 'Ready'
                elif all(data.get(k) for k in ('id', 'owner', 'estimate', 'story', 'phase')):
                    new_status = 'Backlog'
                else:
                    new_status = 'Draft'
                if cli.update_frontmatter(md, {'status': new_status}, create_if_missing=True):
                    changed += 1
                    print(f"📝 Backfilled status={new_status} in {md}")
        print(f"✅ Backfill complete: changed {changed} of {scanned} task files")

    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
