# Working in this repo

Local List Assist ships as **two apps that share one product identity**, plus a
marketing site:

- this **Home Assistant integration** — `rynecoop/ha-grocery-learning` (domain `grocery_learning`)
- a standalone **Android app** — `rynecoop/local-list-assist-android`
- the **marketing site** — `rynecoop/locallistassist-site`, served at https://locallistassist.app

## Keep the marketing site in sync (standing rule)

Whenever you add or change a **user-facing feature** in this app, update the
marketing site to match **in the same unit of work** — don't leave it for later:

- update `products/home-assistant/index.html` (this app's product page)
- update the Home Assistant product card on `index.html` (the landing page)
- open a PR on `rynecoop/locallistassist-site` (add the repo to the session if it
  isn't already), verify it renders, and ship it alongside the app change

Keep site copy honest about what actually works (e.g. don't imply a local-only
feature syncs). Pure internal bug fixes that don't change what users see do not
need a site change.

## Release flow (for reference)

- Bump `custom_components/grocery_learning/manifest.json` `version`; the release
  workflow auto-publishes the GitHub release (HACS installs from releases).
- CI gate (`.github/workflows/validate.yml`): BOM check, ruff, compileall,
  `python -m unittest`, the node `test_state_helpers.mjs` tests, hassfest, HACS.
- Pure, HA-independent logic lives in small modules (`item_logic.py`,
  `frontend/state-helpers.js`) so it can be unit tested without Home Assistant.
