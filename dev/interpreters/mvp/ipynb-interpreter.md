# Task: Jupyter Notebook Interpreter (MVP)

## Metadata
- ID: task:interpreters/mvp/ipynb-interpreter
- Vision: vision:interpreters
- Phase: phase:interpreters/mvp
- Status: planned
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-09-05
- Labels: [interpreter, ipynb]

## Goal
Provide a notebook interpreter for .ipynb files that extracts lightweight metadata: kernel, language, cell counts by type, and the first few markdown headings/code cell imports.

## Requirements
- Map *.ipynb to ipynb interpreter via InterpreterRegistry.
- Parse JSON safely without executing code.
- Return InterpretationResult fields:
  {
    "type": "ipynb",
    "kernel": "python3",
    "language": "python",
    "cells": {"code": 12, "markdown": 7, "raw": 1},
    "first_headings": ["## Introduction", "## Methods"],
    "imports": ["numpy", "pandas"]
  }
- File size limit (e.g., <= 5 MB for MVP) with error path if exceeded.
- Unit tests: small fixture notebook and error path for oversized file.

## Plan
1. Implement IpynbInterpreter in scidk/interpreters/ reading JSON and summarizing content.
2. Register rule for *.ipynb with reasonable priority.
3. Update dataset detail renderer to show notebook summary sections (reuse JSON pretty-print).
4. Add tests and fixtures in tests/.

## DoD
- For a sample .ipynb, interpreter returns kernel, counts, headings, and imports; appears in UI.
- Oversized notebooks handled gracefully with error state.
