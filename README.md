# Local Grocery Assistant

Local Grocery Assistant is a Home Assistant custom integration that gives you a clean, local-first grocery app with smart category routing, duplicate handling, and voice-friendly add flows.

## Why This Exists
- Keep grocery workflows local in Home Assistant.
- Make voice + typed adds land in one consistent app.
- Reduce list chaos with auto-routing and learning.
- Keep shopping simple in-store with category-ordered lists.

## Highlights
- Dedicated sidebar app: `Grocery List`
- Quick Add with per-user attribution
- Voice/list alias intake routing (for example: shopping list, grocery list)
- Auto-route by learned terms + defaults
- Duplicate decision flow (Add Anyway or Skip)
- Review-and-learn flow for unknown items
- Completed section with restore support + clear completed button
- In-app Configure experience for categories/order and system repair
- Self-provisioning for required todo lists/helpers

## Screenshots
- Main app: [docs/screenshots/main-list.png](docs/screenshots/main-list.png)
- Configure panel: [docs/screenshots/configure.png](docs/screenshots/configure.png)
- Duplicate flow: [docs/screenshots/duplicate-review.png](docs/screenshots/duplicate-review.png)
- Mobile view: [docs/screenshots/mobile-view.png](docs/screenshots/mobile-view.png)

## Demo Videos
- Change category flow: [docs/videos/change-category.mp4](docs/videos/change-category.mp4)
- Uncheck + clear completed flow: [docs/videos/completed-clear.mp4](docs/videos/completed-clear.mp4)

## Install
### HACS (recommended)
1. Add this repository as a custom repository in HACS (`Integration`) if not in default yet.
2. Install `Local Grocery Assistant`.
3. Restart Home Assistant.
4. Go to `Settings -> Devices & Services`.
5. Add `Local Grocery Assistant`.
6. Open `Grocery List` from the sidebar.
7. Click `Configure` and complete setup.

### Manual
1. Copy `custom_components/grocery_learning` into your HA config directory.
2. Restart Home Assistant.
3. Add integration from `Settings -> Devices & Services`.
4. Open `Grocery List` and complete setup.

## Quick Start
1. Open sidebar item `Grocery List`.
2. Add 2-3 items with Quick Add.
3. Add one item by voice to your shopping/grocery list.
4. If an item lands in `Other`, use review actions to teach the category once.
5. Re-test the same item and verify it routes correctly.

## Documentation
- Setup guide: [docs/setup.md](docs/setup.md)
- Usage guide: [docs/usage.md](docs/usage.md)
- Voice guide: [docs/voice.md](docs/voice.md)
- Troubleshooting: [docs/troubleshooting.md](docs/troubleshooting.md)
- FAQ: [docs/faq.md](docs/faq.md)

## Service APIs
- `grocery_learning.route_item`
- `grocery_learning.apply_review`
- `grocery_learning.confirm_duplicate`
- `grocery_learning.learn_term`
- `grocery_learning.forget_term`
- `grocery_learning.sync_helpers`

## Support
- Issues: https://github.com/rynecoop/ha-grocery-learning/issues
- Changelog: [CHANGELOG.md](CHANGELOG.md)

## Project Structure
- Integration: `custom_components/grocery_learning`
- Docs: `docs/`
- HACS metadata: `hacs.json`
- Branding assets: `brands/`
