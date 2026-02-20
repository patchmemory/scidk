"""
---
id: builtin-file-distribution
name: File Distribution by Extension
description: Analyze file types across all scans. Shows count of files per extension as a table and bar chart.
language: cypher
category: builtin
tags: [files, statistics, distribution]
parameters:
  - name: limit
    type: integer
    default: 100
    label: Max results
    required: false
---
"""
MATCH (f:File)
RETURN f.extension as extension,
       count(*) as count
ORDER BY count DESC
LIMIT $limit
