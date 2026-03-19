# Voice Guide

## Supported Voice Intake
- common list-name phrases like `shopping list` and `grocery list` can still be routed into Local List Assist
- the integration also exposes a direct internal add path:
  - `grocery_learning.add_to_list`
- a first-class Assist intent handler is registered as:
  - `LocalListAssistAddItem`

## Recommended Setup
- best compatibility: keep the legacy bridge behavior available as a fallback
- best long-term path: route Assist directly into `LocalListAssistAddItem` or `grocery_learning.add_to_list`
- easiest setup path in the app:
  - `App Settings -> Install Voice Phrases`

## Recommended Phrases
- `Add milk to shopping list`
- `Add eggs to grocery list`
- `Add ibuprofen to shopping list`
- `Add batteries to Ryne list`
- `Add paper towels to test`

## Verification Checklist
1. speak an add command
2. open `Local List Assist`
3. confirm the item appears in the expected category or in `Other`
4. confirm the item is not stranded in a generic todo list

## If Voice Items Do Not Route
1. open `App Settings`
2. click `Install Voice Phrases`
3. run `Repair Local Setup` if required helpers/lists are missing
4. restart Home Assistant if Assist still has stale sentence data
5. retest the voice add
6. if you use custom Assist sentences, confirm they target `LocalListAssistAddItem` or `grocery_learning.add_to_list`

## Notes
- voice behavior stays fully inside Home Assistant
- list aliases and internal list naming still matter for accurate routing in multi-list mode
