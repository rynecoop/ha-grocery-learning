# Troubleshooting

## Integration Not Found or Services Missing
- symptom: `grocery_learning.route_item not found`
- fix:
1. confirm the integration is added in `Settings -> Devices & Services`
2. restart Home Assistant

## App Shows an Error Card
1. update to the latest release
2. restart Home Assistant
3. hard refresh the browser
4. if the error persists, capture the full message from the card and Home Assistant logs

## Another Device Is Not Updating
1. confirm both devices are on the latest integration version
2. confirm both devices are looking at the same Home Assistant instance
3. wait a short moment for the live revision signal to propagate
4. if one device is in an open editor or modal, close it so the deferred refresh can apply
5. if needed, use the panel refresh button once and retest

## Category Rename Did Not Stick
1. open `List Settings`
2. use the category edit control
3. click `Save`
4. if the category was renamed to a duplicate existing category, the rename will be ignored

## Item Routes to `Other` Unexpectedly
1. use the review action once to teach the category
2. add the same item again and verify routing
3. confirm the category still exists in that list's current category set

## Voice Add Goes to the Wrong Place
1. confirm the latest integration version
2. open `App Settings`
3. run `Install Voice Phrases`
4. run `Repair Local Setup` if required entities are missing
5. retest with the voice phrase you expect users to say

