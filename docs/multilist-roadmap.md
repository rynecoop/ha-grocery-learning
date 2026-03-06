# Multi-List Roadmap (vNext)

This plan keeps current behavior stable while we build multi-list support.

## Strategy
- Keep current single-list flow as the default path.
- Add multi-list behind `experimental_multilist` (default OFF).
- Ship in phases to reduce risk and simplify rollback.

## Phase 1: Guardrails (current)
- Add `experimental_multilist` option in config/options flow.
- Keep runtime defaults and payload aware of the flag.
- Maintain a regression checklist for legacy single-list behavior.

## Phase 2: Data Model
- Add integration-managed storage schema for:
  - Lists
  - Categories per list (ordered)
  - Items per list
  - Per-list learning/routing rules
- Add schema versioning + migration from current model.

## Phase 3: API + App Shell
- Add list management APIs: create, rename, archive, delete.
- Add list switcher UI and per-list category settings.
- Keep existing actions backward-compatible.

## Phase 4: Voice + Automations
- Add list-targeting support in service calls/intents.
- Ensure duplicate handling remains source-aware (typed vs voice).

## Phase 5: Security + Ops
- Enforce auth for all app APIs.
- Add export/import and backup paths.
- Add audit metadata for list/item changes.

## Phase 6: Optional Cloud Sync (later)
- Keep local data as source of truth.
- Add optional encrypted sync log for cloud replication.
- Maintain full offline capability when cloud is unavailable.
