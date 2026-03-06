# Changelog

## 0.5.6
- Improved Quick Add user attribution by resolving current HA user from local `hassTokens` access token against `/api/auth/current_user` when standard unauthenticated panel context does not include `hass_user`.
- Added stale duplicate-state cleanup on non-prompt duplicate-allowed routes so previously pending duplicate prompts do not persist into later voice/external add flows.

## 0.5.5
- Fixed typed-user attribution by injecting current Home Assistant user identity into the app shell at render time and forwarding actor metadata on Quick Add requests.
- Improved metadata persistence fallback so unresolved typed adds no longer store `Unknown`; they store actor name or `User`.
- Added route-level guard to always bypass duplicate confirmation for `voice_assistant` source calls, ensuring voice-confirmed repeats do not trigger additional in-app duplicate prompts.

## 0.5.4
- Fixed remaining duplicate-confirmation overlap by forcing `allow_duplicate=true` for all external todo intake listener routes (prevents secondary in-app duplicate prompt loops after voice/external add flows).
- Added frontend current-user capture (`/api/auth/current_user`) and forwarded actor metadata for Quick Add, enabling user-name attribution when context user ID is unavailable.
- Reworked item subtitle rendering to use stored metadata at read time (`last_added_at`, `last_added_by_name`, `last_source`) so timestamps show relative age (`Just now`, `5 minutes ago`, `2 hours ago`, `3 days ago`) instead of static `just now`.
- Updated typed attribution fallback to `User` (instead of `Voice Assistant`) when user identity cannot be resolved.

## 0.5.3
- Fixed voice-flow duplicate handling when intake comes through inbox-like paths by basing duplicate bypass on detected event source (`voice_assistant`) instead of only list alias mismatch.
- Improved source detection priority for todo service events so contexts with both `parent_id` and `user_id` are treated as voice assistant calls.
- Fixed attribution fallback so typed items without resolvable user context no longer default to `Voice Assistant`; they now default to `User`.

## 0.5.2
- Fixed duplicate-prompt overlap for voice assistant list-alias intake flows (`shopping list` / `grocery list`).
- Voice alias adds now bypass integration duplicate confirmation UI (`allow_duplicate=true`) so voice-confirmed duplicates do not trigger a second in-app decision loop.
- Typed/in-app add flows still keep duplicate confirmation behavior.

## 0.5.1
- Simplified main list UX by moving setup/settings behind a dedicated `Configure` button instead of always rendering wizard controls in the active shopping view.
- Added first-run `Setup Needed` notice with quick open action, while keeping day-to-day list workflow clean.
- Fixed quick-add user attribution by forwarding the authenticated Home Assistant user ID from the app API request context into routing service calls.

## 0.5.0
- Added an in-app Setup Wizard / Settings panel directly in the Grocery app.
- Added in-app reconfiguration for categories and category order (order now driven by the categories field in wizard/settings).
- Added in-app inbox entity, auto-route, and auto-provision controls.
- Added one-tap `Repair/Provision` action to self-heal required Grocery lists/helpers without manual YAML/helper setup.
- Added built-in system health display (missing required lists + runtime readiness) in the app.
- Preserved custom wizard-complete state across native HA options updates.

## 0.4.9
- Expanded add-item intake routing to support voice-assistant adds from common list aliases (for example `shopping list` / `grocery list`), not just the configured inbox entity.
- Intake routing now removes items from the source alias list after routing so items appear in the Grocery app lists instead of being stranded in generic todo lists.
- Added context-aware source labeling for routed items (`voice_assistant`, `typed`, `automation`) based on service call context.

## 0.4.8
- Added a `Clear Completed` button in the app to purge completed grocery history in one tap.
- Simplified item UI by hiding category controls by default; click an item row to open category reassignment.
- Reworked item-row event handling to avoid inline JS reference bugs that could break recategorization for certain item IDs.
- Fixed review/duplicate fallback reads so helper states like `unknown`/`unavailable` are ignored instead of being treated as real item names.
- Hardened recategorize action responses with explicit backend errors (`item_not_found`, `missing_item_reference`, `item_summary_missing`) instead of false-success responses.

## 0.4.7
- Fixed custom app API view crash (`'GroceryLearningDashboardView' object has no attribute 'hass'`) by resolving Home Assistant runtime from `request.app["hass"]`.
- Restored dashboard load and add-action functionality for the sidebar app panel.

## 0.4.6
- Fixed custom app add-action reliability by lazily initializing integration runtime from API views when state is not ready.
- Added storage-load fallbacks so runtime still starts even if saved data is malformed or migration metadata is missing.
- Updated app-shell API handling to surface backend errors in the UI instead of silently failing actions.

## 0.4.5
- Renamed the Home Assistant sidebar panel title from `Grocery App` to `Grocery List`.
- Hardened `/api/grocery_learning/dashboard` to always return a safe JSON payload shape (including startup/not-ready states) so the custom app no longer fails with raw 500 responses.
- Added dashboard payload type/state guards to prevent malformed runtime state from breaking app load.

## 0.4.4
- Fixed custom app load reliability by hardening todo list reads in dashboard payload generation (graceful fallback instead of fatal 500).
- Updated integration-managed dashboards to be hidden from sidebar so users go directly to the `Grocery App` sidebar entry.
- Removed dependency on opening nested dashboard launch cards for normal use.

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
