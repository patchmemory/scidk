# RO-Crate Viewer Embedding Plan

This document outlines how to embed a RO-Crate viewer (Crate-O) into the UI with minimal changes.

Artifacts:
- Canonical: dev/features/ui/feature-rocrate-viewer-embedding.md

Plan highlights:
- Add conditional link from dataset detail to a viewer when a RO-Crate is detected
- Consider Jinja flags and lightweight JS to embed external viewer
- Defer heavy integration and keep this as an optional enhancement for later cycles
