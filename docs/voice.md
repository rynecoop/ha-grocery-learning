# Voice Guide

## Supported Voice Intake Behavior
- Adds from common list names like `shopping list` and `grocery list` are routed into Grocery List app categories.
- Source alias list item is removed after routing.

## Recommended Phrases
- "Add milk to shopping list"
- "Add eggs to grocery list"
- "Add ibuprofen to shopping list"

## Verification Checklist
1. Speak add command.
2. Open `Grocery List` app.
3. Confirm item appears in expected category (or `Other` if unknown).
4. Confirm item is not stranded in generic todo list.

## If Voice Items Do Not Route
1. Open `Configure` and verify `Auto route inbox/voice intake` is enabled.
2. Click `Repair/Provision`.
3. Restart Home Assistant.
4. Re-test voice add.
