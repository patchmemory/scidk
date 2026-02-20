# Scripts Directory

This directory contains all user-extensible scripts for SciDK.

## Structure

```
scripts/
├── analyses/          # Ad-hoc analysis scripts
│   ├── builtin/      # Built-in analyses (shipped with SciDK)
│   └── custom/       # User-created analyses
├── interpreters/     # File interpretation logic
├── plugins/          # Plugin implementations
├── integrations/     # External service integrations
└── api/             # Custom API endpoints
```

## Script Format

Scripts use YAML frontmatter for metadata:

```python
"""
---
id: my-script
name: My Script
description: Does something useful
language: python
category: analyses/custom
tags: [example, demo]
parameters:
  - name: limit
    type: integer
    default: 100
    label: Max results
    required: false
---
"""
# Your code here
```

## Categories

### 📊 Analyses
Ad-hoc queries and reports. Run button executes and shows results.

### 🔧 Interpreters
File parsing/interpretation logic. Must implement `interpret(file_path)` function.

### 🔌 Plugins
Modular extensions with `__init__.py`. Can define custom labels, routes, settings UI.

### 🔗 Integrations
External service connectors. OAuth/API key configuration, webhook handlers.

### 🌐 API Endpoints
Custom REST API routes. Auto-registered from Python functions with decorators.

## Usage

1. Create a new script file in the appropriate category directory
2. Add YAML frontmatter with metadata
3. Write your code
4. Save the file - SciDK will hot-reload automatically
5. Access from the Scripts page at `/scripts`

## Version Control

All scripts are version controlled via git. The `custom/` directories are gitignored by default.
