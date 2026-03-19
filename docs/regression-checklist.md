# Regression Checklist

Use this checklist before and after each Home Assistant release candidate.

## Test Setup
- verify at least two Home Assistant users exist for attribution checks
- verify at least two HA client sessions are open for live refresh checks
- verify one voice assistant path is available if voice routing is part of the test

## Core Flows
- Quick Add typed item appears in the correct list
- duplicate typed add shows the in-app duplicate decision card
- `Add anyway` adds one additional item only
- `Skip` does not add a duplicate
- completed items move into `Completed`
- restoring from `Completed` returns the item to the correct category

## List Management
- create a new list with the `+` button
- open `List Settings` from the active list chip
- rename the list and verify the new name persists
- change list color and verify the header/list styling updates
- add categories and verify sections render in the same order
- reorder categories and verify section order updates
- edit a category name in place and verify existing items keep that category
- remove a category and verify unsupported items fall back safely

## Activity and Tools
- open `App Settings`
- open `Activity` from `Tools`
- verify recent actions appear there
- run `Repair Local Setup` only if the environment is missing helpers/lists

## Routing and Learning
- unknown item routes to `Other`
- review action reassigns the item and learns the category
- future same term routes to the learned category

## Attribution and Metadata
- typed item subtitle shows the user when Home Assistant provides that context
- metadata survives category review and item edits

## Multi-Device Refresh
- open the panel on two HA devices or browser sessions
- add an item on device A and verify it appears on device B shortly after
- complete an item on device A and verify device B updates shortly after
- while a modal/editor is open on device B, make a change on device A and verify device B refreshes after the modal/editor closes

## Safety
- integration options still load cleanly from `Devices & Services`
- sidebar app opens without API or frontend errors
- no unexpected traceback appears in Home Assistant logs during normal flows

## Release Gate
- do not release if any item above fails

