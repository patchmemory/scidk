# Prompting Junie with Dev CLI

## Setup Prompt (One Time)
```
You have access to a dev CLI tool that manages our development workflow. The repository uses a file-based planning system in the dev/ folder. Here are the key commands:

- `python dev_cli.py ready-queue` - Show prioritized ready tasks
- `python dev_cli.py start <task-id>` - Start a task (creates branch, shows context)  
- `python dev_cli.py context <task-id>` - Get full implementation context
- `python dev_cli.py validate <task-id>` - Check if task meets Definition of Ready

Always use the CLI to understand task requirements before implementing.
```

## "Turn the Crank" Prompts

### Starting Work
```
Please check the ready queue and start work on the highest priority task:

1. Run `python dev_cli.py ready-queue` to see available tasks
2. Run `python dev_cli.py start <task-id>` for the top task
3. Implement according to the acceptance criteria
4. Run tests and ensure DoD is met

Let me know if you need clarification on any requirements.
```

### Specific Task Implementation  
```
Please implement task:core-architecture/mvp/search-index:

1. Run `python dev_cli.py context task:core-architecture/mvp/search-index`
2. Review the acceptance criteria and implementation hints
3. Implement the /api/search endpoint with the specified fields
4. Write tests for filename and interpreter matching
5. Ensure idempotent scan behavior

Update me when complete or if you hit blockers.
```

### Cycle Planning Assistance
```
Help me plan the next development cycle:

1. Run `python dev_cli.py cycle-status` to see current progress
2. Run `python dev_cli.py next-cycle` to see proposed tasks
3. Review the top 5 tasks and check their dependencies
4. Recommend any adjustments based on the e2e objective

Focus on maintaining GUI acceptance and demoable increments.
```

## The "Turn the Crank" Workflow

### Human Role (Product Direction)
1. Define stories and acceptance criteria
2. Break down into tasks in ready queue
3. Set priorities using RICE scoring
4. Review cycle outcomes and adjust

### AI Role (Implementation)  
1. `python dev_cli.py ready-queue` → Pick next task
2. `python dev_cli.py start <task>` → Get context and branch
3. Implement according to acceptance criteria
4. Run tests and validate DoD
5. `python dev_cli.py complete <task>` → Merge and update

### Continuous Loop
```
Human: "I want search functionality for the MVP"
↓
Human: Creates/prioritizes search tasks in ready queue
↓  
AI: `dev_cli.py start task:core-architecture/mvp/search-index`
↓
AI: Implements API endpoint with tests
↓
AI: `dev_cli.py start task:ui/mvp/home-search-ui` 
↓
AI: Implements UI components
↓
Human: Reviews demo, provides feedback
↓
Human: Adjusts next cycle priorities
```

## Benefits of This Approach

✅ **Clear handoffs** - CLI provides structured task context
✅ **Self-documenting** - All planning decisions captured in files  
✅ **Traceable** - Git branches tied to task IDs
✅ **Scalable** - Multiple AI agents can work independently
✅ **Human oversight** - Product direction stays with humans
✅ **Turn the crank** - AI picks up tasks and implements without micromanagement
