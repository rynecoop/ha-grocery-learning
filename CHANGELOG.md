# Changelog

## 0.4.3
- Replaced nested dashboard iframe usage with a full-height Home Assistant sidebar panel (`/grocery-app`) for proper mobile scrolling and large-list usability.
- Hardened custom app API endpoints with exception handling to avoid opaque 500 responses and surface actionable errors.
- Grocery and Grocery Admin dashboards now provide clean launch buttons into the dedicated app panel.

## 0.4.2
- Fixed iframe app-shell `401 Unauthorized` issue by allowing embedded Grocery app endpoints to load inside Lovelace iframe cards.

## 0.4.1
- Added missing Home Assistant manifest dependency declaration for `http` required by the custom Grocery app API views.

## 0.4.0
- Introduced a self-contained custom Grocery web app served by the integration at `/api/grocery_learning/app` (no native todo-card dependency for core UX).
- Switched Grocery and Grocery Admin dashboards to embedded app-shell views.
- Added app API endpoints for dashboard data and actions (`add`, `recategorize`, `complete`, `undo`, review, duplicate resolution).
- Added robust one-list style grouped UI with top-of-screen attention queues for duplicates/review to prevent missed routing decisions.
- Added default `pharmacy` category and preserved completed-list move/restore workflow.

## 0.3.5
- Added new default `pharmacy` category with starter keywords.
- Added dedicated `Grocery Completed` list flow: checked items move out of active category cards into a completed card, and unchecking in completed restores the item to its original category.
- Improved self-contained event handling for `todo.update_item` so completion and restore behavior work without extra YAML automations.

## 0.3.4
- Replaced dashboard review/duplicate status display with integration-managed sensor entities so UI remains functional even if helper YAML/entities are removed.
- Added fallback review behavior: category action buttons now pull the next uncategorized item from `Other` when pending state is missing.
- Improved review/duplicate status synchronization for a more reliable self-contained flow.

## 0.3.3
- Made uncategorized review flow fully actionable in dashboards with direct category action buttons (no fragile input-select dependency).
- Added in-memory pending-review state so Review & Learn remains functional even if helper entities are temporarily unavailable.
- Tuned todo list cards to keep completed items visible for easy undo after accidental check-offs.

## 0.3.2
- Added item `description` metadata on all add paths so todo entries can show "added by/source" secondary text in compatible Home Assistant todo UIs.

## 0.3.1
- Added automatic helper provisioning (review, duplicate, and learned-term helpers) so the integration is self-contained without manual helper YAML setup.
- Fixed admin dashboard missing/unavailable controls by ensuring required helper entities are created during setup.

## 0.3.0
- Introduced a polished in-HA app shell layout for both Grocery and Grocery Admin dashboards.
- Added status tile grids, cleaner section structure, and an operations-center style admin view.
- Kept core app behavior helper-optional while preserving advanced duplicate/review controls when helper entities are present.

## 0.2.5
- Fixed inbox auto-route listener to detect `todo.add_item` entity targets from both `service_data` and top-level `target` payload shapes (restores reliable Quick Add routing and duplicate checks).
- Improved Grocery Admin dashboard to show out-of-box operational cards (overview + list status) even when optional helper entities are not configured.

## 0.2.4
- Removed helper-dependent Quick Add mode from auto dashboard; Quick Add now always uses inbox `todo-list` create flow.
- Made duplicate/review dashboard cards render only when required helper entities exist, preventing missing-helper UI/runtime issues.

## 0.2.3
- Fixed Home Assistant options flow initialization (`TypeError: GroceryLearningOptionsFlow() takes no arguments`) by restoring a compatible constructor signature.

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
