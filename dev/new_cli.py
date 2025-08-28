#!/usr/bin/env python3
"""
Dev CLI (self-describing harness)

This module wraps the existing DevCLI (dev/cli.py) with:
- argparse-based subcommands
- a command registry with metadata
- meta-commands: menu, introspect
- global flags: --json, --explain, --dry-run
- consistent JSON envelope outputs

It does not change DevCLI; it adds agent- and human-friendly discoverability.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Dict, List, Optional

from dev.cli import DevCLI  # Uses the existing implementation

Json = Dict[str, Any]


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
    handler: Optional[Callable[[DevCLI, argparse.Namespace], Json]] = None


# -----------------------
# Helpers
# -----------------------

def envelope_ok(cmd: str, data: Any = None, plan: Any = None, warnings: List[str] | None = None) -> Json:
    return {
        "status": "ok",
        "command": cmd,
        "data": data,
        "plan": plan,
        "warnings": warnings or [],
    }


def envelope_err(cmd: str, error: str, details: Any = None, warnings: List[str] | None = None) -> Json:
    return {
        "status": "error",
        "command": cmd,
        "error": error,
        "details": details,
        "warnings": warnings or [],
    }


def explain_or_dryrun(ns: argparse.Namespace, plan: Json, run: Callable[[], Json]) -> Json:
    # Non-mutating modes: both --explain and --dry-run return plan only
    if getattr(ns, 'explain', False):
        return envelope_ok(ns.command, data=None, plan=plan)
    if getattr(ns, 'dry_run', False):
        return envelope_ok(ns.command, data=None, plan=plan)
    return run()


# -----------------------
# Handlers wrapping DevCLI
# -----------------------

def handle_ready_queue(cli: DevCLI, ns: argparse.Namespace) -> Json:
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


def handle_start(cli: DevCLI, ns: argparse.Namespace) -> Json:
    tid = ns.task_id
    # auto-pick top ready if not provided
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


def handle_context(cli: DevCLI, ns: argparse.Namespace) -> Json:
    tid = ns.task_id
    ctx = cli.get_task_context_data(tid)
    if ctx is None:
        return envelope_err(ns.command, "not_found", {"task_id": tid})
    return envelope_ok(ns.command, data=ctx)


def handle_validate(cli: DevCLI, ns: argparse.Namespace) -> Json:
    tid = ns.task_id
    # Validate and summarize missing fields
    task_file = cli.find_task_file(tid)
    if not task_file or not task_file.exists():
        return envelope_err(ns.command, "not_found", {"task_id": tid})
    data = cli.parse_frontmatter(task_file) or {}
    req = ['id', 'owner', 'estimate', 'story', 'phase', 'acceptance']
    missing = [f for f in req if not data.get(f)]
    if not data.get('dor'):
        missing.append('dor')
    return envelope_ok(ns.command, data={"ok": len(missing) == 0, "missing": missing})


def handle_complete(cli: DevCLI, ns: argparse.Namespace) -> Json:
    tid = ns.task_id
    plan = {"actions": ["run pytest", "print DoD checklist from task frontmatter"], "task_id": tid}

    def run():
        cli.complete_task(tid)
        return envelope_ok(ns.command, data={"task_id": tid})

    return explain_or_dryrun(ns, plan, run)


def handle_cycle_status(cli: DevCLI, ns: argparse.Namespace) -> Json:
    result = {"active_story": None, "active_phase": None}
    if cli.cycles_file.exists():
        txt = cli.cycles_file.read_text(encoding='utf-8')
        import re
        m = re.search(r'Active Story/Phase: (story:[^—\n]+) — (phase:[^\n]+)', txt)
        if m:
            result["active_story"] = m.group(1)
            result["active_phase"] = m.group(2)
        else:
            m2 = re.search(r'Active Story: (story:[^\n]+)', txt)
            if m2:
                result["active_story"] = m2.group(1)
    return envelope_ok(ns.command, data=result)


def handle_next_cycle(cli: DevCLI, ns: argparse.Namespace) -> Json:
    ready = cli.get_ready_queue()
    top = [{"rank": i + 1, "id": t.get('id'), "rice": t.get('rice'), "owner": t.get('owner')} for i, t in enumerate(ready[:5])]
    return envelope_ok(ns.command, data={"top_ready": top})


def handle_merge_safety(cli: DevCLI, ns: argparse.Namespace) -> Json:
    plan = {"actions": ["pick base branch or use override", "git diff", "summarize deletions and risky files"], "base": ns.base}

    def run():
        res = cli.merge_safety(ns.base)
        return envelope_ok(ns.command, data=res)

    return explain_or_dryrun(ns, plan, run)


# -----------------------
# Registry
# -----------------------

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


# -----------------------
# Argparse wiring + introspection
# -----------------------


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

    # dynamic commands from registry
    for spec in COMMANDS:
        sp = sub.add_parser(spec.name, help=spec.summary, description=spec.description)
        # positional args
        for arg in spec.args:
            kwargs: Dict[str, Any] = {}
            if arg.choices:
                kwargs['choices'] = arg.choices
            if arg.default is not None:
                kwargs['default'] = arg.default
            if arg.nargs:
                kwargs['nargs'] = arg.nargs
            sp.add_argument(arg.name, help=arg.help, **kwargs)
        # options
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


def handle_menu(ns: argparse.Namespace) -> Json:
    items = [{
        "name": c.name,
        "summary": c.summary,
        "examples": c.examples,
    } for c in COMMANDS]
    return envelope_ok("menu", data={"commands": items})


def handle_introspect(ns: argparse.Namespace) -> Json:
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


def main() -> None:
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

    # call handler
    result = spec.handler(cli, ns) if spec.handler else envelope_err(ns.command, "no_handler")

    # output formatting
    if getattr(ns, 'json', False):
        print(json.dumps(result, indent=2, default=str))
    else:
        status = result.get('status')
        if status == 'error':
            print(f"❌ {ns.command} failed: {result.get('error')}\n{result.get('details') or ''}")
        elif getattr(ns, 'explain', False) or getattr(ns, 'dry_run', False):
            print(f"📝 Plan for {ns.command}:\n" + json.dumps(result.get('plan'), indent=2))
        else:
            # Human-readable: many DevCLI methods already print richly
            if result.get('data') is not None:
                print(json.dumps(result['data'], indent=2, default=str))


if __name__ == "__main__":
    main()
