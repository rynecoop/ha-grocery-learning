# Setup Guide

## Prerequisites
- Home Assistant installed and running.
- HACS installed (recommended for updates).
- Integration added from HACS or manually copied into `custom_components`.

## Initial Install (HACS)
1. Open HACS.
2. Add repository as custom Integration if needed.
3. Install `Local Grocery Assistant`.
4. Restart Home Assistant.
5. Add the integration in `Settings -> Devices & Services`.

## First Run Wizard
1. Open `Grocery List` from the Home Assistant sidebar.
2. Click `Configure`.
3. Set `Categories` in store walking order.
4. Confirm `Inbox Entity` (default `todo.grocery_inbox`).
5. Leave `Auto route` and `Auto provision` enabled unless you have a specific reason not to.
6. Click `Repair/Provision`.
7. Click `Complete Setup`.

## Reconfigure Later
1. Open `Grocery List`.
2. Click `Configure`.
3. Update categories/order or inbox settings.
4. Click `Save`.

## Notes
- Category order controls display order in the app and your in-store flow.
- If required lists are missing, `Repair/Provision` recreates them.
