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
from typing import Any, Dict, List, Optional, Tuple, Iterable, Callable
import argparse
from dataclasses import dataclass, asdict, field


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
        # Default base to compare merges against (helps keep dev/ results merged across branches)
        self.default_base_branches = [
            os.environ.get('SCIDK_BASE_BRANCH') or '',
            'origin/main', 'main', 'origin/master', 'master'
        ]

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

    def complete_task(self, task_id: str):
        """Mark task as complete and validate DoD (lightweight)"""
        print(f"🎯 Completing task: {task_id}")
        # 1) Run tests
        print("🧪 Running tests (pytest -q)...")
        try:
            res = subprocess.run("pytest -q", shell=True)
            if res.returncode == 0:
                print("✅ Tests passing")
            else:
                print(f"❌ Tests failed (exit {res.returncode}) — fix before completing.")
        except Exception as e:
            print(f"⚠️ Could not run tests: {e}")
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
        risky_paths = ['scidk/app.py', 'scidk/ui/templates', 'scidk/core', 'scidk/interpreters', 'dev/']
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
        print(" - Always ensure dev/ outputs are merged forward to avoid redoing work across branches.")
        return {
            "summary": summary,
            "deleted_files": deleted,
            "file_stats": file_stats,
            "risky_deletions": risky_deletions,
        }


def sh_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# -----------------------
# Self-describing harness (argparse + registry)
# -----------------------

@dataclass
class ArgSpec:
    name: str
    help: str
    required: bool = False
    choices: Optional[List[str]] = None
    default: Optional[str] = None
    nargs: Optional[str] = None  # e.g., '?', '*'


@dataclass
class OptSpec:
    flags: List[str]
    help: str
    action: Optional[str] = None  # 'store', 'store_true', etc.
    dest: Optional[str] = None
    default: Any = None
    choices: Optional[List[str]] = None


@dataclass
class CommandSpec:
    name: str
    summary: str
    description: str
    args: List[ArgSpec] = field(default_factory=list)
    options: List[OptSpec] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    handler: Optional[Callable[[DevCLI, argparse.Namespace], Dict[str, Any]]] = None


# Envelopes

def envelope_ok(cmd: str, data: Any = None, plan: Any = None, warnings: List[str] | None = None) -> Dict[str, Any]:
    return {
        "status": "ok",
        "command": cmd,
        "data": data,
        "plan": plan,
        "warnings": warnings or [],
    }


def envelope_err(cmd: str, error: str, details: Any = None, warnings: List[str] | None = None) -> Dict[str, Any]:
    return {
        "status": "error",
        "command": cmd,
        "error": error,
        "details": details,
        "warnings": warnings or [],
    }


def explain_or_dryrun(ns: argparse.Namespace, plan: Dict[str, Any], run: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    if getattr(ns, 'explain', False):
        return envelope_ok(ns.command, data=None, plan=plan)
    if getattr(ns, 'dry_run', False):
        return envelope_ok(ns.command, data=None, plan=plan)
    return run()


# Handlers wrapping DevCLI

def handle_ready_queue(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    ready = cli.get_ready_queue()
    data = [{
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
    } for t in ready]
    return envelope_ok(ns.command, data=data)


def handle_start(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    tid = ns.task_id
    if not tid:
        ready = cli.get_ready_queue()
        if not ready:
            return envelope_err(ns.command, "no_ready_tasks")
        tid = ready[0].get('id')
    plan = {
        "actions": [
            "validate DoR for task",
            "create or checkout git branch task/<id>",
            "print task context",
        ],
        "task_id": tid,
        "branch": f"task/{str(tid).replace(':', '-')}"
    }
    def run():
        cli.start_task(tid)
        ctx = cli.get_task_context_data(tid) or {}
        return envelope_ok(ns.command, data={"task_id": tid, "branch": plan["branch"], "context": ctx})
    return explain_or_dryrun(ns, plan, run)


def handle_context(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    tid = ns.task_id
    ctx = cli.get_task_context_data(tid)
    if ctx is None:
        return envelope_err(ns.command, "not_found", {"task_id": tid})
    return envelope_ok(ns.command, data=ctx)


def handle_validate(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    tid = ns.task_id
    task_file = cli.find_task_file(tid)
    if not task_file or not task_file.exists():
        return envelope_err(ns.command, "not_found", {"task_id": tid})
    data = cli.parse_frontmatter(task_file) or {}
    req = ['id', 'owner', 'estimate', 'story', 'phase', 'acceptance']
    missing = [f for f in req if not data.get(f)]
    if not data.get('dor'):
        missing.append('dor')
    return envelope_ok(ns.command, data={"ok": len(missing) == 0, "missing": missing})


def handle_complete(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    tid = ns.task_id
    plan = {"actions": ["run pytest", "print DoD checklist from task frontmatter"], "task_id": tid}
    def run():
        cli.complete_task(tid)
        return envelope_ok(ns.command, data={"task_id": tid})
    return explain_or_dryrun(ns, plan, run)


def handle_cycle_status(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
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
    return envelope_ok(ns.command, data=result)


def handle_next_cycle(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    ready = cli.get_ready_queue()
    top = [{"rank": i + 1, "id": t.get('id'), "rice": t.get('rice'), "owner": t.get('owner')} for i, t in enumerate(ready[:5])]
    return envelope_ok(ns.command, data={"top_ready": top})


def handle_merge_safety(cli: DevCLI, ns: argparse.Namespace) -> Dict[str, Any]:
    plan = {"actions": ["pick base branch or use override", "git diff", "summarize deletions and risky files"], "base": ns.base}
    def run():
        res = cli.merge_safety(ns.base)
        return envelope_ok(ns.command, data=res)
    return explain_or_dryrun(ns, plan, run)


# Registry
COMMANDS: List[CommandSpec] = [
    CommandSpec(
        name="ready-queue",
        summary="Show ready tasks sorted by RICE (DoR true)",
        description="Scans dev/tasks for markdown with YAML frontmatter, filters DoR-marked Ready tasks, sorts by RICE.",
        handler=handle_ready_queue,
        side_effects=["reads_files:dev/tasks/**/*.md"],
        preconditions=["tasks_dir_optional"],
        postconditions=[],
        examples=["dev ready-queue", "dev ready-queue --json"],
    ),
    CommandSpec(
        name="start",
        summary="Validate DoR, create/switch branch, print context.",
        description="Validates task DoR, chooses branch task/<id>, attempts git checkout/create, prints task context.",
        args=[ArgSpec("task_id", "Task ID to start (defaults to top ready)", required=False, nargs='?')],
        options=[OptSpec(["--no-git"], "Currently unused placeholder to skip git ops", action="store_true", dest="no_git")],
        handler=handle_start,
        side_effects=["git_checkout_optional"],
        preconditions=["task_exists_or_auto_pick"],
        postconditions=["on_success: branch checked out"],
        examples=["dev start story:foo:bar", "dev start  # auto-pick"],
    ),
    CommandSpec(
        name="context",
        summary="Emit AI context for a task (JSON or text).",
        description="Returns full task context including acceptance criteria and file path.",
        args=[ArgSpec("task_id", "Task ID", required=True)],
        handler=handle_context,
        side_effects=[],
        preconditions=["task_exists"],
        postconditions=[],
        examples=["dev context story:foo:bar --json"],
    ),
    CommandSpec(
        name="validate",
        summary="Validate Definition of Ready (DoR) for a task.",
        description="Checks required fields and dor:true in frontmatter.",
        args=[ArgSpec("task_id", "Task ID", required=True)],
        handler=handle_validate,
        side_effects=["reads_files"],
        preconditions=["task_exists"],
        postconditions=[],
        examples=["dev validate story:foo:bar --json"],
    ),
    CommandSpec(
        name="complete",
        summary="Run tests, print DoD checklist, and next steps.",
        description="Executes pytest and prints a DoD checklist from task frontmatter.",
        args=[ArgSpec("task_id", "Task ID", required=True)],
        handler=handle_complete,
        side_effects=["runs_pytest"],
        preconditions=["python_env_with_pytest"],
        postconditions=["test_results_emitted"],
        examples=["dev complete story:foo:bar", "dev complete story:foo:bar --explain"],
    ),
    CommandSpec(
        name="cycle-status",
        summary="Show current cycle status from dev/cycles.md",
        description="Parses cycles.md to report active story and phase.",
        handler=handle_cycle_status,
        side_effects=["reads_file:dev/cycles.md"],
        preconditions=["cycles_file_optional"],
        postconditions=[],
        examples=["dev cycle-status --json"],
    ),
    CommandSpec(
        name="next-cycle",
        summary="Propose the next cycle using top Ready tasks.",
        description="Lists top RICE-scored ready tasks.",
        handler=handle_next_cycle,
        side_effects=["reads_tasks"],
        preconditions=[],
        postconditions=[],
        examples=["dev next-cycle", "dev next-cycle --json"],
    ),
    CommandSpec(
        name="merge-safety",
        summary="Report potentially risky deletions vs base branch.",
        description="Diffs against a base branch to summarize deletions and risky files.",
        options=[OptSpec(["--base"], "Base branch to compare", dest="base")],
        handler=handle_merge_safety,
        side_effects=["git_diff"],
        preconditions=["git_repo"],
        postconditions=["report_emitted"],
        examples=["dev merge-safety", "dev merge-safety --base origin/main --json"],
    ),
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dev", description="Dev CLI (self-describing)")
    p.add_argument('--json', action='store_true', help='Emit structured JSON envelope')
    p.add_argument('--explain', action='store_true', help='Explain what would happen')
    p.add_argument('--dry-run', action='store_true', help='Simulate without side-effects')
    sub = p.add_subparsers(dest='command')
    # meta: menu
    menu_parser = sub.add_parser('menu', help='List commands (human) or JSON menu (agents)')
    menu_parser.add_argument('--json', action='store_true', help='Emit JSON menu')
    # meta: introspect
    sub.add_parser('introspect', help='Emit full command registry as JSON')
    # dynamic commands
    for spec in COMMANDS:
        sp = sub.add_parser(spec.name, help=spec.summary, description=spec.description)
        for arg in spec.args:
            kwargs: Dict[str, Any] = {}
            if arg.choices:
                kwargs['choices'] = arg.choices
            if arg.default is not None:
                kwargs['default'] = arg.default
            if arg.nargs:
                kwargs['nargs'] = arg.nargs
            sp.add_argument(arg.name, help=arg.help, **kwargs)
        for opt in spec.options:
            o_kwargs: Dict[str, Any] = {'help': opt.help}
            if opt.action:
                o_kwargs['action'] = opt.action
            if opt.dest:
                o_kwargs['dest'] = opt.dest
            if opt.default is not None:
                o_kwargs['default'] = opt.default
            if opt.choices:
                o_kwargs['choices'] = opt.choices
            sp.add_argument(*opt.flags, **o_kwargs)
    return p


def handle_menu(ns: argparse.Namespace) -> Dict[str, Any]:
    items = [{
        "name": c.name,
        "summary": c.summary,
        "examples": c.examples,
    } for c in COMMANDS]
    return envelope_ok("menu", data={"commands": items})


def handle_introspect(ns: argparse.Namespace) -> Dict[str, Any]:
    full: List[Dict[str, Any]] = []
    for c in COMMANDS:
        d = asdict(c)
        d.pop('handler', None)
        full.append(d)
    env = {
        "version": "1.0",
        "env": {
            "SCIDK_BASE_BRANCH": os.environ.get('SCIDK_BASE_BRANCH'),
        },
        "commands": full,
        "conventions": {
            "json_envelope": {
                "status": "ok|error",
                "command": "<name>",
                "data": {},
                "plan": {},
                "warnings": []
            },
            "global_flags": ["--json", "--explain", "--dry-run"],
        }
    }
    return envelope_ok("introspect", data=env)


def main():
    parser = build_parser()
    ns = parser.parse_args()

    # meta commands first
    if ns.command == 'menu':
        result = handle_menu(ns)
        if getattr(ns, 'json', False):
            print(json.dumps(result, indent=2))
        else:
            for item in result['data']['commands']:
                print(f"{item['name']}: {item['summary']}")
                if item['examples']:
                    print("  e.g., " + "; ".join(item['examples']))
        return

    if ns.command == 'introspect':
        result = handle_introspect(ns)
        print(json.dumps(result, indent=2))
        return

    # regular commands (from registry)
    cli = DevCLI()
    spec_map = {c.name: c for c in COMMANDS}
    spec = spec_map.get(ns.command)

    if not spec:
        parser.print_help()
        return

    result = spec.handler(cli, ns) if spec.handler else envelope_err(ns.command, "no_handler")

    if getattr(ns, 'json', False):
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get('status')
        if status == 'error':
            print(f"❌ {ns.command} failed: {result.get('error')}\n{result.get('details') or ''}")
        elif getattr(ns, 'explain', False) or getattr(ns, 'dry_run', False):
            print(f"📝 Plan for {ns.command}:\n" + json.dumps(result.get('plan'), indent=2))
        else:
            if result.get('data') is not None:
                print(json.dumps(result['data'], indent=2, default=str))


if __name__ == "__main__":
    main()
