id: phase:providers-mvp-multi-source-files/01-txt-xlsx-interpreters
story: story:providers-mvp-multi-source-files
order: 1
status: Done
owner: agent
created: 2025-08-20
updated: 2025-08-21
e2e_objective: TXT and XLSX interpreters produce summaries in dataset detail
acceptance:
  - TxtInterpreter maps .txt with preview and line_count
  - XlsxInterpreter maps .xlsx and shows sheet summaries
  - Dataset detail renders interpreter summaries
scope_in: [txt, xlsx, ui-dataset]
scope_out: [ipynb]
selected_tasks: []
dependencies: []
demo_checklist:
  - Scan folder with txt and xlsx; open dataset detail; verify summaries
links:
  cycle: dev/cycles.md
