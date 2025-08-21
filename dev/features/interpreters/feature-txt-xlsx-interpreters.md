id: feature:interpreters/txt-xlsx
title: TXT and XLSX Interpreters
status: Draft
owner: agent
created: 2025-08-21
updated: 2025-08-21
goal: Provide basic summaries for .txt and .xlsx files in dataset detail.
scope:
  - TxtInterpreter with preview and line_count
  - XlsxInterpreter with sheet names, rows, cols, macros flag
out_of_scope:
  - ipynb interpreter (tracked separately)
success_metrics:
  - Datasets with these extensions show summaries reliably
links:
  stories: [story:providers-mvp-multi-source-files]
  tasks: []
