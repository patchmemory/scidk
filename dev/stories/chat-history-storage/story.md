id: story:chat-history-storage
title: Chat History Storage (Persist, Search, Retrieve)
status: Proposed
owner: agent
created: 2025-08-21
updated: 2025-08-21
success: Users can persist, search, and retrieve prior chats to restore context.
scope_in: [crud, pagination, keyword-search, export]
scope_out: [vector-search, advanced-rbac, attachments]
links:
  phases: []
  related_features: []
  cycles: [dev/cycles.md]

Narrative
- Introduce durable storage for historical chat conversations so users (and the assistant) can view, search, and reuse prior context. Initial focus: reliable CRUD for conversations/messages, pagination, simple keyword search, and basic export.

Notes
- See legacy draft: dev/stories/story-chat-history-storage.md
