"""
---
id: builtin-scan-timeline
name: Scan Timeline & Volume
description: Show scan history with file counts and timestamps. Useful for tracking data ingestion over time.
language: cypher
category: builtin
tags: [scans, timeline, history]
parameters:
  - name: limit
    type: integer
    default: 50
    label: Max scans
    required: false
---
"""
MATCH (s:Scan)
RETURN s.id as scan_id,
       s.started as started,
       s.completed as completed,
       s.root as path,
       s.file_count as file_count
ORDER BY s.started DESC
LIMIT $limit
