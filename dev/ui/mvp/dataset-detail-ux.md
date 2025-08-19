# Task: Dataset Detail UX Improvements (MVP)

## Metadata
- ID: task:ui/mvp/dataset-detail-ux
- Vision: vision:ux
- Phase: phase:ui/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-29
- Labels: [frontend, ux]

## Goal
Make dataset detail page readable and resilient by rendering interpretation sections with friendly formatting and clear error states.

## Requirements
- Group interpretation results by interpreter with heading and small badge (status: ok/error/timeout).
- Pretty-print JSON values for small payloads; collapse large payloads with a toggle.
- Show errors inline with icon and short message; keep raw details in a collapsible block.
- Link to specialized viewers when available (e.g., workbook.html for .xlsx).

## Implementation Plan
- Update scidk/ui/templates/dataset_detail.html:
  - Section per interpretation with interpreter name and status badge.
  - JSON pretty-print via <pre> with safe escaping; collapse logic via simple JavaScript.
  - Error rendering path when interpretation contains error fields.
- Minor styling using base template classes.

## DoD
- Example .py interpretation renders as readable keyed sections.
- Error simulation shows badge and collapsible details.
- No JS errors in console.

## Progress Log
- 2025-08-18: Drafted UX requirements and plan; implementation scheduled for next cycle.
- 2025-08-18: Implemented status badges, friendly sections for python and csv, and error details; DoD met.
