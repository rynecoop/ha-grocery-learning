# Grocery Learning

Home Assistant custom integration for grocery routing, review, and auto-learning.

This project is built from a production setup and is designed to be shareable.

## Quick Start (Recommended)
1. Install integration (HACS custom repository or manual copy).
2. Add `grocery_learning:` to `configuration.yaml`.
3. Restart Home Assistant.
4. Add helpers/snippets from:
   - `examples/configuration_helpers.yaml`
   - `examples/automations.yaml`
   - `examples/scripts.yaml`
5. Import dashboard examples from:
   - `examples/dashboards/lovelace.grocery.json`
   - `examples/dashboards/lovelace.grocery_admin.json`
6. Restart Home Assistant again.
7. Test:
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
5. Add to `configuration.yaml`:
   - `grocery_learning:`
6. Restart Home Assistant.
7. Merge helper/automation/script snippets from `examples/`.
8. Import dashboard JSON examples or recreate cards from examples.

## Install (Manual)
1. Copy `custom_components/grocery_learning` into your HA config directory.
2. Add `grocery_learning:` to `configuration.yaml`.
3. Restart Home Assistant.
4. Apply example helpers/automations/scripts from `examples/`.
5. Import dashboard examples from `examples/dashboards/`.

## Core Services
- `grocery_learning.route_item`
- `grocery_learning.apply_review`
- `grocery_learning.learn_term`
- `grocery_learning.forget_term`
- `grocery_learning.sync_helpers`

## Current Scope
This release provides the integration foundation and service APIs plus tested example config.
It includes a setup wizard and integration-managed inbox auto-routing.
It does not yet auto-create all helper entities/lists/dashboards by itself.

## Troubleshooting
- `Action grocery_learning.route_item not found`
  - Ensure `grocery_learning:` exists in `configuration.yaml`.
  - Restart Home Assistant after adding/changing integration files.
- Dashboard/admin view not visible
  - Confirm dashboard is imported/registered.
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
1. Auto-provision entities/lists on first run.
2. Native integration entities for review state.
3. Built-in dashboard creation.
4. Optional voice intent pack.
5. Full zero-touch onboarding flow.
