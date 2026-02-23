# Grocery Learning

Home Assistant custom integration for grocery routing, review, and auto-learning.

This project is built from a production setup and is designed to be shareable.

## Why This Exists
This project is for people moving off Alexa Shopping List while keeping the same convenience for voice-added groceries.

Alexa shopping list support is often the last blocker for going fully local on voice assistants.  
Grocery Learning replaces that workflow in Home Assistant and adds features Alexa does not provide:
- local-first control in your HA environment
- store-walk routing by category/order
- review + correction workflow for uncertain items
- auto-learning from your corrections
- dashboard/admin visibility into learned behavior

Goal: make a truly local voice assistant setup practical, with grocery list behavior equal to or better than Alexa.

## Quick Start (Recommended)
1. Install integration (HACS custom repository or manual copy).
2. Restart Home Assistant.
3. Add integration:
   - `Settings -> Devices & Services -> Add Integration -> Grocery Learning`
4. In setup wizard:
   - keep default categories or add your own categories (comma/newline separated)
   - keep auto-provision enabled so missing grocery lists are created for you
   - keep auto-dashboard enabled so Grocery dashboards are created/updated for you
5. Open sidebar dashboards:
   - `Grocery`
   - `Grocery Admin` (admin-only)
6. Test:
   - Add `coffee` to grocery list (should route to Pantry).
   - Add a weird item (should go to Other + show review flow).
   - Apply review category and re-add the same item (should auto-route due to learning).

## What It Does
- Routes grocery items into category lists (produce, bakery, meat, dairy, frozen, pantry, household, other).
- Learns from your review decisions so future items auto-route.
- Supports review workflow for uncertain (`other`) items.
- Works with dashboard and automation-driven flows.

## Included In This Repo
- Integration code:
  - `custom_components/grocery_learning`
- HACS metadata:
  - `hacs.json`
- Example dashboard exports:
  - `examples/dashboards/lovelace.grocery.json`
  - `examples/dashboards/lovelace.grocery_admin.json`
- Example YAML snippets:
  - `examples/configuration_helpers.yaml`
  - `examples/automations.yaml`
  - `examples/scripts.yaml`

## Install (HACS Custom Repository)
1. Push this repo to GitHub.
2. In HACS, add a Custom Repository pointing to your repo URL, type `Integration`.
3. Install `Grocery Learning`.
4. Restart Home Assistant.
5. Add integration in UI (`Settings -> Devices & Services`).
6. Complete setup wizard (categories + auto-provision).
7. Import dashboard JSON examples or recreate cards from examples.

## Install (Manual)
1. Copy `custom_components/grocery_learning` into your HA config directory.
2. Restart Home Assistant.
3. Add integration in UI (`Settings -> Devices & Services`).
4. Complete setup wizard (categories + auto-provision).
5. Import dashboard examples from `examples/dashboards/`.

## Core Services
- `grocery_learning.route_item`
- `grocery_learning.apply_review`
- `grocery_learning.learn_term`
- `grocery_learning.forget_term`
- `grocery_learning.sync_helpers`

## Current Scope
This release provides:
- setup wizard with editable categories
- automatic provisioning of missing grocery todo lists (inbox, each category, other)
- automatic provisioning/updating of Grocery dashboards (main + admin)
- integration-managed inbox auto-routing and learning services
- optional helper sync for legacy YAML-based setups

You can still import/modify example dashboards manually if you want a custom layout.

## Troubleshooting
- `Action grocery_learning.route_item not found`
  - Ensure the integration is added in `Settings -> Devices & Services`.
  - Restart Home Assistant after installing/updating in HACS.
- Dashboard/admin view not visible
  - Confirm auto-dashboard is enabled in integration options.
  - Reopen Home Assistant frontend after integration reload.
  - Clear app/frontend cache or fully reopen the HA app.
- Item not routing as expected
  - Use review flow to classify and learn.
  - Call `grocery_learning.sync_helpers` if you manually edited learned terms.

## Publish Checklist
1. Update metadata in `custom_components/grocery_learning/manifest.json`:
   - `documentation`
   - `issue_tracker`
   - `codeowners`
2. Create GitHub release tag (for HACS install stability).
3. Verify `hacs.json` and manifest versions match intended release.
4. Add screenshots/GIFs to repo README for user onboarding.

## Roadmap
1. Native integration entities for review state.
2. Optional voice intent pack.
3. Full zero-touch onboarding flow hardening.
4. Guided category-review UX improvements.
5. Extended dedupe and normalization tuning options.
