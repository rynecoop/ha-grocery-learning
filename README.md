# Local Grocery Assistant

Local Grocery Assistant is a Home Assistant custom integration for grocery routing, review, and auto-learning.

It is designed for users moving away from Alexa Shopping List while keeping fast voice add flows and gaining better control over category routing.

## Features
- Local-first grocery routing by category
- Auto-learning from review decisions
- Duplicate-prevention flow with pending confirmation + Add Anyway/Skip actions
- Duplicate context: who added it, when it was added, and source (typed/voice/automation)
- Dedicated `Grocery Completed` list with quick undo support (unchecked items return to original category list)
- Auto-provisioning of grocery todo lists
- Self-contained custom Grocery app UI served by the integration (`/api/grocery_learning/app`)
- Auto-generated `Grocery` and `Grocery Admin` dashboards embed the custom app shell
- One-tap Review & Learn category action buttons directly in dashboards
- Includes default `pharmacy` category for hygiene/medicine items
- Configurable categories and category order

## Install
### HACS (Recommended)
1. In HACS, add this repo as a Custom Repository (`Integration`) if it is not yet in the default index.
2. Install `Local Grocery Assistant`.
3. Restart Home Assistant.
4. Add integration in `Settings -> Devices & Services`.
5. In setup wizard:
   - keep `auto_provision` enabled
   - keep `auto_dashboard` enabled
   - set your categories in store-walk order

### Manual
1. Copy `custom_components/grocery_learning` to your Home Assistant config at `custom_components/grocery_learning`.
2. Restart Home Assistant.
3. Add integration in `Settings -> Devices & Services`.
4. Complete setup wizard.

## Upgrade
1. Update integration in HACS (or copy updated files manually).
2. Restart Home Assistant.
3. Open integration options and confirm:
   - categories and order
   - inbox entity
   - auto-provision and auto-dashboard toggles
4. Hard refresh mobile/web frontend if old dashboard cards are cached.

## Usage
- Add items via voice or Quick Add.
- Integration routes items by learned terms + keyword fallback.
- Unknown items land in `Other` and can be reviewed/learned.
- Duplicate items trigger a confirmation card with context before adding again.

Core services:
- `grocery_learning.route_item`
- `grocery_learning.apply_review`
- `grocery_learning.confirm_duplicate`
- `grocery_learning.learn_term`
- `grocery_learning.forget_term`
- `grocery_learning.sync_helpers`

## Troubleshooting
- `Action grocery_learning.route_item not found`
  - Confirm integration is added in Devices & Services.
  - Restart Home Assistant after install/update.
- Quick Add or inbox item not removed after routing
  - Ensure source list is your configured inbox entity.
  - Retry once after restart (removal includes short retries for race conditions).
- Dashboard not updating after category changes
  - Confirm `auto_dashboard` is enabled in integration options.
  - Reload integration and refresh frontend cache.
- Item routes to `Other` unexpectedly
  - Use review flow once to teach it.
  - Re-test the same term.

## FAQ
- Do I need YAML edits for normal setup?
  - No. The integration runs zero-touch through UI setup and auto-provisions the helper entities it needs.
- Can I add/reorder categories later?
  - Yes. Change categories in integration options; routing and dashboard order follow that list.
- Will this break existing `grocery_learning.*` automations?
  - No. Domain and service names remain `grocery_learning` for compatibility.
- Why doesn’t a custom icon always show in HACS immediately?
  - Branding comes from Home Assistant Brands and can take time after merge/update.

## Publishing Notes
- HACS default listing is done through PR to `hacs/default` `integration` file.
- Integration branding icon/logo is submitted to Home Assistant Brands for domain `grocery_learning`.
- Starter branding assets: `brands/README.md`.

## Repo Layout
- Integration: `custom_components/grocery_learning`
- HACS metadata: `hacs.json`
- Examples: `examples/`
- Changelog: `CHANGELOG.md`
