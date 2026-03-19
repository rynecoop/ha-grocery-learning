# Local List Assist

Local List Assist is a Home Assistant custom integration that gives you a local-first list app with clean list management, category-based organization, duplicate handling, review-and-learn routing, and voice-friendly add flows.

## What It Is
- 100% Home Assistant hosted
- local-first by design
- built for household lists, errands, grocery runs, projects, camping, travel, and similar list workflows
- no cloud sync service outside Home Assistant

## Highlights
- dedicated sidebar app: `Local List Assist`
- quick add with per-user attribution where Home Assistant provides user context
- multiple local lists with color theming
- category sections with per-list category order
- in-place category editing in `List Settings`
- duplicate decision flow: `Add anyway` or `Skip`
- review-and-learn flow for uncategorized items
- completed section with restore and clear support
- `App Settings` and `List Settings` inside the app
- `Activity` moved under `App Settings -> Tools`
- automatic provisioning/repair for required helpers and todo lists
- near-real-time refresh across open Home Assistant devices using Home Assistant's own state updates

## Install
### HACS
1. Install `Local List Assist` from HACS.
2. Restart Home Assistant.
3. Go to `Settings -> Devices & Services`.
4. Add `Local List Assist`.
5. Open `Local List Assist` from the sidebar.

### Manual
1. Copy `custom_components/grocery_learning` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings -> Devices & Services`.

## Quick Start
1. Open `Local List Assist` from the sidebar.
2. Create your first list with the `+` button.
3. Add a few items with Quick Add.
4. Open `App Settings` and click `Install Voice Phrases` if you want voice adds.
5. Open `List Settings` on the active list to edit categories, color, and voice aliases.
6. If an item lands in `Other`, use the review actions once to teach the category.

## Current UI Model
- `+` button: create a new list
- active list chip: open `List Settings`
- long-press on touch or right-click on desktop: reorder lists
- hamburger menu: open navigation drawer
- `App Settings`: sync/repair/tools/links
- `Activity`: available from `App Settings -> Tools`

## Live Updates
- changes made on one Home Assistant device now propagate to other open Local List Assist panels almost immediately
- this uses a revision signal inside the integration and Home Assistant's normal pushed state updates
- active editing is protected: the panel waits to reload until dialogs/editors close

## Documentation
- Setup guide: [docs/setup.md](docs/setup.md)
- Usage guide: [docs/usage.md](docs/usage.md)
- Voice guide: [docs/voice.md](docs/voice.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- FAQ: [docs/faq.md](docs/faq.md)
- Regression checklist: [docs/regression-checklist.md](docs/regression-checklist.md)
- Media capture checklist: [docs/media-capture-checklist.md](docs/media-capture-checklist.md)

## Service APIs
- `grocery_learning.route_item`
- `grocery_learning.add_to_list`
- `grocery_learning.install_voice_sentences`
- `grocery_learning.apply_review`
- `grocery_learning.confirm_duplicate`
- `grocery_learning.learn_term`
- `grocery_learning.forget_term`
- `grocery_learning.sync_helpers`

## Compatibility Note
- display name is `Local List Assist`
- domain and service namespace remain `grocery_learning` for compatibility

## Support
- Issues: [https://github.com/rynecoop/ha-grocery-learning/issues](https://github.com/rynecoop/ha-grocery-learning/issues)
- Changelog: [CHANGELOG.md](CHANGELOG.md)

