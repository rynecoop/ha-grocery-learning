# Changelog

## 0.12.2
- Extracted archive, restore, and delete-archived-list mutations into a pure helper module and added regression tests around those flows.
- Tightened backend validation for archive lifecycle behavior so list-management changes are safer to refactor.

## 0.12.1
- Extracted voice list-name matching into a pure helper module and added regression tests for display-name, alias, and list-id matching.
- Tightened release validation around voice alias behavior so custom-list voice routing changes are easier to verify safely.

## 0.12.0
- Fixed archived-list persistence so archived lists reload with the same normalized structure as active lists.
- Added a lightweight unit test suite for learned-term and multilist storage normalization, and wired it into CI.

## 0.11.3
- Added local panel-state updates for simple item actions so complete, recategorize, and clear completed feel faster and less jumpy.

## 0.11.2
- Simplified the Configure UI into clearer sections for app settings, create list, active list, and archived lists.
- Moved noisy maintenance controls into an advanced area and reduced rerender interruptions while a field is active.

## 0.11.1
- Removed the generic undo banner from the panel and made list archive a real archive with restore/delete controls in Configure.
- Reduced rerender interruptions while a field is focused, which stabilizes controls like the list color picker.

## 0.11.0
- Added an in-app undo banner for recent destructive actions.
- Users can now undo the latest complete/restore, category change, clear completed, and archive list action directly from the panel.

## 0.10.6
- Fixed item category editors so they keep their open state and focus cleanly while you pick a new category, including after background rerenders.

## 0.10.5
- Fixed inline category editors so they stay open across rerenders and keep the selected category while you are changing an item.
- Opening an item now focuses the category selector directly instead of collapsing the editor during background UI updates.

## 0.10.4
- Fixed the quick-add input so it keeps local draft state and restores focus after rerenders, which keeps the mobile keyboard open while typing.

## 0.10.3
- Fixed Configure inputs so text fields keep their local draft while typing instead of losing focus on rerender.
- Simplified active-list editing by replacing multiple save buttons with a single `Save Active List` action.

## 0.10.2
- Added per-list voice aliases so users can define one or more spoken names for each list in Configure.
- Voice routing now matches against configured aliases before falling back to the default grocery list.

## 0.10.1
- Fixed direct Assist matching for possessive custom list names like `Ryne's list` by comparing multiple normalized voice-name variants instead of a single exact form.

## 0.10.0
- Broadened direct Assist phrase coverage for custom lists and hardened internal list-name normalization so spoken custom list targets resolve more reliably.
- Moved Recent Activity into its own in-app tab so the main shopping view stays focused on the current list.
- Added per-list color theming for internal lists, including a configurable active-list color in Configure.

## 0.9.0
- Added a one-click `Install Voice Phrases` flow in Configure that writes the bundled sentence pack into Home Assistant's `custom_sentences` folder and attempts a conversation reload.
- Exposed the same capability as `grocery_learning.install_voice_sentences` for scripted setup and future automation.
- Kept the new direct Assist intent path and the legacy bridge path together so users can migrate voice safely.

## 0.8.0
- Added a first-class `LocalListAssistAddItem` Assist intent handler so Local List Assist can accept direct internal voice adds without depending only on `todo` bridge events.
- Kept the legacy `todo`/shopping-list bridge path as a fallback so existing voice setups do not break during migration.
- Updated the repo docs to reflect the internal `grocery_learning.add_to_list` service and the current voice architecture.

## 0.7.2
- Added a mobile fallback header with a menu button so the panel is still navigable when Home Assistant mobile does not expose its usual chrome.
- Changed the main app header to show the active list name instead of repeating the app name, which keeps the top of the view focused on the current list.
- Tightened the mobile layout so the panel reads more like a native list view on narrow screens.

## 0.7.1
- Moved Recent Activity below Completed so it stays available without sitting in the primary shopping flow.
- Fixed category-editor interaction in the native panel by separating checkbox clicks from row clicks, which stopped item taps from collapsing the editor by toggling completion.
- Stopped category controls from bubbling row-click events so recategorizing feels stable on mobile and desktop.

## 0.7.0
- Replaced the sidebar iframe registration with a real Home Assistant custom panel backed by a module-loaded web component.
- Added an internal `add_to_list` service for future Assist/automation ingestion that does not depend on Home Assistant `todo` entities.
- Added a persistent Recent Activity feed and Debug Mode to improve traceability and troubleshooting.
- Kept duplicate-review, recategorize, complete/restore, clear-completed, and multi-list management inside the new panel.

## 0.6.0
- Added a first-class internal `add_to_list` service so future Assist/automation paths can add directly into Local List Assist storage without depending on Home Assistant `todo` entities.
- Added a persistent Recent Activity feed in the app showing item adds, completions, restores, category changes, list operations, and completed-list clearing.
- Added a persistent Debug Mode setting in Configure to surface richer routing/activity logging without changing end-user workflows.
- Improved active-list context in the UI and expanded the settings payload so the app can reflect categorized vs flat-list state more clearly.

## 0.5.30
- Fixed mobile sidebar `401 Unauthorized` for the embedded panel by making only the app shell endpoint public again.
- Dashboard and action endpoints remain authenticated, so data access still requires valid Home Assistant auth.
- Preserved the frontend token-resolution improvements for authenticated API calls after the shell loads.

## 0.5.29
- Fixed mobile `401 Unauthorized` issues caused by the embedded app shell relying on iframe-local auth state.
- The app view now requires Home Assistant auth, and the frontend resolves tokens from the parent/top HA app context as well as local storage.
- This preserves existing dashboard/action auth while making sidebar access work consistently across desktop and mobile clients.

## 0.5.28
- Internal routing now treats both `voice_assistant` and `automation` intake sources as voice-like for list targeting.
- Any intake call with unresolved target (including source-list based automations) now routes to default Grocery list, preventing active-list bleed into custom lists.
- Added fallback mapping from source-list entity for voice/automation intake before defaulting.

## 0.5.27
- Voice routing now prioritizes explicit list-name context and no longer trusts raw bridge entity target alone when list name is missing.
- Unresolved voice list targets route to Grocery by design to prevent accidental placement into active/custom lists.
- Expanded intake compatibility for additional payload variants and domains (`shopping_list.add_item`, `list`, and `name` item fields).

## 0.5.26
- Fixed a critical `route_item` schema mismatch by allowing `source_list_name`; this restores routing for voice events that include list-name fields.
- Standardized intercepted todo intake events to use `voice_assistant` source so they do not fall back through typed/active-list behavior.

## 0.5.25
- Forced unresolved voice adds in internal multi-list mode to default Grocery list (never active-list fallback).
- Improved spoken list-name matching for possessive variants like "`Ryne's list`".
- Expanded voice intake capture for parent-context voice calls and additional list-name field variants (`todo_list_name`).

## 0.5.24
- Fixed voice intake handling for `todo.add_item` calls that include list name fields but no explicit entity target.
- Added name-based voice routing inputs (`name` / `list_name`) so spoken target list names are preserved for internal routing.
- Hardened bridge-source removal and voice intake routing with exception handling to prevent Assist from returning generic errors.

## 0.5.23
- Fixed voice-target routing to resolve internal list by both source bridge entity and source list friendly name.
- Added safe voice fallback: unresolved voice targets now route to default Grocery list instead of the currently active list.
- Included `source_list_name` in voice intake events to make spoken list names (for custom lists) map reliably.

## 0.5.22
- Fixed long-term voice bridge reliability by storing and using the actual created bridge entity IDs per list instead of assuming static IDs.
- Added persisted `voice_alias_entities` tracking so all resolved alias bridge entities route back to the correct internal list.
- Improved bridge provisioning to recover existing `todo.*` lists by friendly name when creation returns a different entity ID.

## 0.5.21
- Added voice alias bridge entities (`todo.lla_alias_<list_id>`) to improve Assist matching for phrases like "`<name> list`".
- Voice routing now accepts both primary and alias bridge entities for each internal list.
- Internal list bridge provisioning now creates voice-friendly alias names automatically where needed.

## 0.5.20
- Updated internal-list voice bridges to use the actual list name as the bridge todo title for better Assist matching.
- Made bridge routing independent from `auto_route_inbox` so voice targeting of app-created lists continues to work even if inbox auto-route is disabled.
- Kept bridge ingestion behavior: route into internal list and remove bridge item after ingestion.

## 0.5.19
- Added per-list voice bridge provisioning (`todo.lla_<list_id>`) for internal multi-list mode so voice adds can target app-created lists reliably.
- Routed voice bridge adds into the matching internal list and auto-removed bridge list items after ingestion.
- Further cleaned settings by separating default grocery behavior from per-list category controls.

## 0.5.18
- Cleaned Configure UI in internal multi-list mode by hiding legacy inbox/auto-route/auto-provision controls.
- Added a single toggle: `Use default shopping/grocery categories for new grocery lists`.
- Kept default list as Grocery with grocery categories; non-grocery lists can stay flat with no review popup noise.
- Moved all list management controls behind `Configure` and kept the active list selector in the header for a cleaner primary workflow.

## 0.5.17
- Renamed app/sidebar branding to **Local List Assist** for multi-list fit.
- Moved list management controls (create/rename/archive/per-list categories) behind `Configure` to keep the main view clean.
- Added top-level active-list selector in the app header.
- Limited smart auto-sorting + review prompts to grocery-style lists; non-grocery/flat lists now keep items in-place without review popups.
- Kept default list as Grocery with grocery-category behavior.

## 0.5.16
- Added per-list category control for experimental multi-list mode, including support for empty category sets (flat list behavior).
- New lists no longer inherit grocery categories by default; they start uncategorized unless custom categories are provided.
- Added smart grocery-category defaulting only when list names look grocery/shopping-oriented.
- Added app controls to set/clear active-list categories and optional categories at list creation time.

## 0.5.15
- Added experimental multi-list management actions: create list, switch active list, rename list, and archive non-default lists.
- Added app UI controls (experimental mode only) for managing internal lists directly from the Grocery app shell.
- Extended dashboard payload with list catalog metadata so the app can render active-list context and switching controls.

## 0.5.14
- Added experimental internal multi-list storage model (`multilist`) persisted by the integration store to begin decoupling app data from Home Assistant `todo.*` entities.
- Added runtime/internal routing path for `route_item`, `apply_review`, and `confirm_duplicate` when `experimental_multilist` is enabled.
- Added internal dashboard/action execution for add, complete/restore, recategorize, and clear-completed flows when the experimental flag is enabled.
- Kept legacy `todo.*` behavior unchanged when `experimental_multilist` is disabled (default).

## 0.5.13
- Fixed app-side user attribution to prefer Home Assistant `display_name` everywhere (panel actor bootstrap, quick-add action fallback, and service-call metadata resolution), so typed entries show real names instead of `User`.
- Hardened subtitle metadata parsing by matching `GLMETA` markers anywhere in the stored description payload, restoring relative-time rendering even when newline formatting differs.
- Switched Grocery dashboard/action API views to authenticated mode so user context is consistently available for attribution and routing metadata.

## 0.5.12
- Intake-list call-service routes are now explicitly marked as `voice_assistant` source so routed voice items no longer show `Typed` metadata.
- Voice intake routing now keeps source-list entries (`remove_from_source=false`) so native voice duplicate confirmation behavior can still occur on repeated voice adds.
- Keeps interactive duplicate popup disabled for non-QuickAdd routes, preserving app-side no-popup behavior for voice/external flows.

## 0.5.11
- Implemented permanent interactive duplicate qualifier: pending duplicate UI can only be created by typed in-app Quick Add (`interactive_duplicate=true`).
- Added schema/action wiring for `interactive_duplicate` so voice/external routes explicitly opt out.
- Added dashboard-time cleanup of legacy/stale non-interactive pending duplicate state to prevent old popup cards from resurfacing.

## 0.5.10
- Added a strict duplicate-prompt qualifier: popup flow is only allowed for typed in-app Quick Add calls.
- All non-QuickAdd routes (voice/external intake with `source_list`/`remove_from_source`) now clear pending duplicate state and skip duplicate popup flow.
- Prevented stale duplicate-pending UI cards from carrying over into subsequent voice/external add events.

## 0.5.9
- Fixed duplicate-entry attribution overwrite by rendering duplicate rows from each todo item's own description instead of shared normalized-item metadata.
- Added actor metadata propagation to duplicate-confirm actions so manually confirmed duplicates retain the confirming user's display name.
- Extended duplicate confirmation service schema to accept actor identity fields used for attribution.

## 0.5.8
- Fixed regression where app actions (add, recategorize, complete, clear completed) could fail in panel context after auth hardening changes.
- Restored action endpoint compatibility while adding token-aware frontend API requests (`Authorization: Bearer <hassTokens.access_token>` + same-origin credentials) for reliable authenticated API behavior in the iframe app shell.

## 0.5.7
- Enforced authenticated action endpoint requests so Quick Add has stable Home Assistant user identity context.
- Added server-side user display-name resolution from user ID for both quick-add action handling and route metadata fallback, ensuring subtitles use actual display names (e.g., `Ryne`, `Maang`) instead of generic `User`.
- Broadened duplicate-bypass gating for external intake paths (`source_list`/`remove_from_source`) so duplicate confirmation popups remain limited to in-app text Quick Add behavior.

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
