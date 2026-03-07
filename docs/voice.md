# Voice Guide

## Supported Voice Intake Behavior
- Legacy voice adds from common list names like `shopping list` and `grocery list` are still routed into Local List Assist.
- Local List Assist now also exposes a direct internal add path: `grocery_learning.add_to_list`.
- A first-class Assist intent handler is registered as `LocalListAssistAddItem` for direct/internal Assist flows.
- To use the direct intent path, Assist still needs sentence mapping that targets `LocalListAssistAddItem` or a sentence-trigger automation that calls `grocery_learning.add_to_list`.

## Recommended Phrases
- "Add milk to shopping list"
- "Add eggs to grocery list"
- "Add ibuprofen to shopping list"

## Recommended Architecture
- Best compatibility: keep the legacy bridge enabled as a fallback.
- Best long-term path: route Assist directly into `LocalListAssistAddItem` or `grocery_learning.add_to_list` so voice no longer depends on Home Assistant `todo` bridge variability.
- In internal multi-list mode, direct Assist routing should target logical list names like `Grocery List`, `Costco List`, or `Ryne List`.
- The easiest setup path is now: `Configure -> Install Voice Phrases`.

## Verification Checklist
1. Speak add command.
2. Open `Local List Assist`.
3. Confirm item appears in expected category (or `Other` if unknown).
4. Confirm item is not stranded in generic todo list.

## If Voice Items Do Not Route
1. Open `Configure` and click `Install Voice Phrases`.
2. Click `Repair/Provision`.
3. Restart Home Assistant if Assist still has stale sentence data.
4. Re-test voice add.
5. If you are using your own custom Assist sentences, confirm they target `LocalListAssistAddItem` or `grocery_learning.add_to_list`.
