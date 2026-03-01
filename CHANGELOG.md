# Changelog

## 0.2.2
- Fixed Home Assistant options flow crash (`AttributeError: property 'config_entry' has no setter`) by removing manual assignment in `GroceryLearningOptionsFlow`.

## 0.2.1
- Fixed startup crash (`NotImplementedError` in Home Assistant storage loader) by keeping storage schema version at `1` while using backward-compatible data handling.

## 0.2.0
- Added item-level metadata tracking for routing decisions (`added by`, `added when`, `source`) persisted in integration storage.
- Added duplicate context helpers and dashboard UI cards that show existing item context before confirming duplicate adds.
- Added new `grocery_learning.confirm_duplicate` service with `add`/`skip` decisions.
- Improved inbox auto-route context propagation so typed entries retain user attribution.

## 0.1.9
- Moved in-repo branding assets from `branding/` to `brands/` for HACS brand validation compatibility.
- Normalized `brands/icon.png` and `brands/logo.png` to `256x256`.
- Added `custom_components/grocery_learning/brand/icon.png` and `logo.png` for HACS action brand-path validation.
- Updated documentation links to reference `brands/README.md`.

## 0.1.7
- Restored duplicate-prevention flow in `route_item` with pending confirmation support.
- Added `allow_duplicate` service option for explicit duplicate adds.
- Improved inbox/quick-add source item removal reliability with normalized matching + short retries.
- Updated auto-generated Quick Add dashboard card to helper-based input/button layout to avoid empty-state text.

## 0.1.6
- Improved keyword routing to handle common plural forms, fixing basics like `bananas` and `grapes`.
- Added branding starter assets and docs in `branding/` for Home Assistant brands submission.
- Updated docs with icon/branding publication notes.

## 0.1.5
- Rebranded user-facing integration name to `Local Grocery Assistant`.
- Updated manifest/HACS/config-flow labels and docs to use the new name.
- Kept integration domain (`grocery_learning`) and service names unchanged for backwards compatibility.

## 0.1.4
- Added auto-dashboard generation for `Grocery` and `Grocery Admin` storage dashboards.
- Dashboard category cards are now generated from configured categories and preserve user-entered order.
- Changing categories in integration options now updates routing order and dashboard card order on reload.
- Added setup/options toggle to enable or disable integration-managed dashboards.

## 0.1.3
- Added category customization in setup/options flow (comma/newline input, normalized slugs).
- Added auto-provision option and runtime provisioning of missing `local_todo` grocery lists:
  - inbox list
  - one list per selected category
  - `other` list
- Refactored routing/learning to use runtime categories from config entry instead of fixed constants.
- Updated services to accept custom categories (text selectors).
- Added options-update reload listener so changes apply cleanly.
- Updated docs for no-YAML install path via Devices & Services.

## 0.1.2
- Expanded README positioning to clearly document Alexa Shopping List replacement use case.
- Clarified local-first voice assistant migration goal and advantages over Alexa list behavior.

## 0.1.1
- Added setup wizard fields in config flow:
  - auto-route inbox toggle
  - inbox entity selection
  - optional notify service
- Added integration-managed inbox routing listener (reduces required YAML automations).
- Added optional notification dispatch from integration when review is needed.
- Improved config-flow labels/translations for beginner setup clarity.

## 0.1.0
- Initial custom integration scaffold (`grocery_learning`).
- Added persistent learned-term storage.
- Added services:
  - `grocery_learning.learn_term`
  - `grocery_learning.forget_term`
  - `grocery_learning.sync_helpers`
  - `grocery_learning.route_item`
  - `grocery_learning.apply_review`
- Added shareable dashboard examples:
  - `examples/dashboards/lovelace.grocery.json`
  - `examples/dashboards/lovelace.grocery_admin.json`
- Added example YAML snippets for helpers, automations, and scripts.
