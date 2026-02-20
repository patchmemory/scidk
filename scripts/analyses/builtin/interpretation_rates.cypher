"""
---
id: builtin-interpretation-rates
name: Interpretation Success Rates
description: Analyze interpreter performance by type. Shows success vs failure rates for each interpreter.
language: cypher
category: builtin
tags: [interpreters, statistics, quality]
---
"""
MATCH (f:File)
WHERE f.interpreter_type IS NOT NULL
WITH f.interpreter_type as interpreter,
     count(*) as total,
     sum(CASE WHEN f.interpretation_success = true THEN 1 ELSE 0 END) as successes
RETURN interpreter,
       total,
       successes,
       total - successes as failures,
       round(100.0 * successes / total, 2) as success_rate
ORDER BY total DESC
