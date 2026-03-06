# Regression Checklist (Legacy Single-List Stability)

Use this checklist before and after every release while `experimental_multilist` is OFF.

## Test Account Setup
- Verify at least two Home Assistant users exist (for attribution checks).
- Verify one voice assistant path is available (Assist, Alexa bridge, etc.).

## Core Flows
- Quick Add typed item appears in the correct category list.
- Duplicate typed add shows the in-app duplicate decision card.
- Choosing `Add Anyway` adds one additional item only.
- Choosing `Skip` does not add a duplicate.
- Voice duplicate behavior is voice-only (no in-app duplicate card appears).

## Metadata
- Typed item subtitle shows `Added by <Display Name>`.
- Voice item subtitle shows `Added by Voice Assistant`.
- Relative time updates from `Just now` to minutes/hours/days correctly.

## Item State
- Checking an item moves it to `Completed`.
- Unchecking in `Completed` restores it to original category.
- `Clear Completed` removes completed items only.

## Routing and Learning
- Unknown item routes to `Other` and creates review workflow.
- Review action reassigns item and learns category.
- Future same term routes to learned category.

## Safety
- Existing setup/options still load with no migration prompts.
- Sidebar app opens without API/auth errors.
- No `AttributeError`/`NotImplementedError` in HA logs during normal flows.

## Release Gate
- Do not release if any item above fails.
- If a failure affects existing users, patch before adding new features.
