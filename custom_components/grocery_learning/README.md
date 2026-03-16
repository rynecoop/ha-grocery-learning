# Local List Assist (Custom Integration)

This folder contains the integration code for domain `grocery_learning`.

For full end-user documentation, use the repo root README:
- `README.md`

## Provides
- Config entry setup via Devices & Services
- Category routing with learning/review flow
- Duplicate-prevention with add/skip confirmation state + metadata context
- Auto-provision of local todo lists
- Auto-generation of Home Assistant dashboards

## Services
- `grocery_learning.learn_term`
- `grocery_learning.forget_term`
- `grocery_learning.sync_helpers`
- `grocery_learning.route_item`
- `grocery_learning.apply_review`

## Notes
- Integration display name: `Local List Assist`
- Domain/service namespace stays `grocery_learning` for compatibility
- Branding assets guidance: `../../brands/README.md`
