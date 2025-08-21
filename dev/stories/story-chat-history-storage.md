# Story: Chat History Storage (Persist, Search, Retrieve)

id: story:chat-history-storage
status: Draft
owner: agent
created: 2025-08-21

Overview
- Introduce durable storage for historical chat conversations so users (and the assistant) can view, search, and reuse prior context.
- Initial focus: reliable CRUD for conversations/messages, pagination, simple keyword search, and basic export.

Motivation
- Enable continuity across sessions, auditing, and collaboration features in future increments.

Goals (Initial Increment)
- CRUD for conversations and messages with ACID semantics.
- Pagination by time/id (keyset), filtering by date and status.
- Keyword search across titles and message text.
- API to retrieve last N messages for context restoration.
- Basic export endpoint to download a conversation transcript (JSON/NDJSON).

Non-Goals (for this increment)
- Semantic vector search, embeddings, and hybrid ranking.
- Full RBAC and sharing UI; advanced retention lifecycles.
- Attachments upload flow (can be stubbed for now).

Scope (In)
- DB schema/migrations for conversations and messages.
- Minimal REST endpoints: create/list/get/patch/delete conversations; add/list messages.
- Simple FTS (depending on chosen DB) or substring search fallback.
- Soft delete with status flags (active/archived/deleted).

Scope (Out)
- Background summarization and archival tiers.
- Multi-tenant RBAC enforcement beyond basic scoping.

Acceptance Criteria (TBD for approval)
- [ ] Can create a conversation, add messages, retrieve paginated message history.
- [ ] Can search conversations/messages by keyword.
- [ ] Can export a conversation transcript.
- [ ] Soft delete respected by list/get endpoints.

API Sketch (proposed)
- POST /conversations → { id }
- GET /conversations?status=active&limit=50&cursor=...
- GET /conversations/{id}
- PATCH /conversations/{id} (rename, archive)
- DELETE /conversations/{id} (soft delete)
- POST /conversations/{id}/messages → { id }
- GET /conversations/{id}/messages?limit=100&cursor=...
- POST /search { query, mode: keyword }
- POST /export { conversation_id }

Data Model Sketch
- conversations(id, org_id?, owner_user_id?, title, status, summary json?, tags json?, last_message_at, created_at, updated_at)
- messages(id, conversation_id, sender_type, role, content json, tokens int?, parent_message_id?, ordering bigserial, created_at)

Risks & Considerations
- Large transcripts: enforce limits and pagination.
- PII: avoid logging raw content; consider redaction toggles later.

Open Questions
- Primary DB choice (PostgreSQL vs existing store) for this project?
- Is multi-tenant isolation required in the first increment?
- Do we need attachments in the first cut, or only metadata hooks?

Traceability
- Related initiative: Historical Chat Storage plan (previous discussion/notes).
- Will link PRs and cycles once scheduled.

Notes
- This is a placeholder draft to be refined upon approval. Add/adjust Acceptance Criteria and Scope as needed before implementation.
