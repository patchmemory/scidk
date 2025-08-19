# Task: Chat UI (MVP)

## Metadata
- ID: task:ui/mvp/chat-ui
- Vision: vision:ux
- Phase: phase:ui/mvp
- Status: done
- Priority: P1
- Owner: agent
- Created: 2025-08-18
- ETA: 2025-08-28
- Labels: [frontend, ux, chat]

## Goal
Add a minimal Chat UI to the Home page that talks to POST /api/chat and renders conversation history stored in-memory by the app.

## Context
Backend stub exists: POST /api/chat echoes messages and stores in-memory history on the app. We need a simple UI to interact with it.

## Requirements
- UI elements on Home page (index):
  - Text input and Send button.
  - Scrollable conversation history (user/assistant turns) persisted for the app lifetime.
- Client-side behavior:
  - Submit to /api/chat; on success, append both user and assistant messages to the conversation window.
  - Basic loading state and error display.
- Accessibility:
  - Keyboard submit (Enter) and focus management.

## Implementation Plan
- Template updates: scidk/ui/templates/index.html
  - Add Chat section with messages container and form.
- Minimal JS inline or separate file (inline for MVP) to POST and update DOM.
- Add route wiring if needed (ensure /api/chat present; it is stubbed already per cycles).

## DoD
- Manually verified: can send a message and see assistant echo.
- Basic error handling works (network error shows a message).
- Rendered nicely within existing base template.

## Progress Log
- 2025-08-18: Drafted task and acceptance; pending implementation next cycle.
- 2025-08-18: Implemented chat widget on Home page using /api/chat; basic JS for submit and rendering history; added API test; DoD met.
