# Troubleshooting

## Integration Not Found or Services Missing
- Symptom: `grocery_learning.route_item not found`
- Fix:
1. Confirm integration is added in `Settings -> Devices & Services`.
2. Restart Home Assistant.

## App Shows Error Card
- Open Home Assistant logs and capture the full error text.
- Common fix path:
1. Update to latest release.
2. Restart Home Assistant.
3. Hard refresh browser (`Ctrl+F5`).

## Item Routes to Other Unexpectedly
- Use review action once to teach category.
- Add same item again and verify routing.

## Voice Add Goes to Raw Todo List
1. Confirm latest integration version.
2. Confirm auto-route setting is enabled.
3. Run `Repair/Provision`.
4. Re-test with phrase "Add milk to shopping list".

## Category Changes Not Reflected
1. Save settings from Configure panel.
2. Restart Home Assistant if needed.
3. Hard refresh browser.
