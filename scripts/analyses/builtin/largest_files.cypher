"""
---
id: builtin-largest-files
name: Largest Files
description: Find the largest files in the knowledge graph by size. Helps identify storage-heavy files.
language: cypher
category: analyses/builtin
tags: [files, size, storage]
parameters:
  - name: limit
    type: integer
    default: 50
    label: Max files
    required: false
---
"""
MATCH (f:File)
WHERE f.size_bytes IS NOT NULL
RETURN f.path as path,
       f.size_bytes as size_bytes,
       f.extension as extension,
       f.modified as modified
ORDER BY f.size_bytes DESC
LIMIT $limit
