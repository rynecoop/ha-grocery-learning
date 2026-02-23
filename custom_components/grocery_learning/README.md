# Local Grocery Assistant (Custom Integration)

This integration is the foundation for a shareable "grocery list routing + review + learn" system.

It is specifically aimed at replacing Alexa Shopping List workflows for users moving to a local Home Assistant voice setup.

## Current Scope (v0.1.4)
- Config entry (`Settings -> Devices & Services -> Add Integration -> Local Grocery Assistant`)
- Setup wizard for:
  - auto-provisioning grocery lists
  - auto-provisioning Grocery dashboards
  - category selection/customization
  - inbox auto-routing and optional notifications
- Persistent learned term storage in HA storage
- Services:
  - `grocery_learning.learn_term`
  - `grocery_learning.forget_term`
  - `grocery_learning.sync_helpers`
  - `grocery_learning.route_item`
  - `grocery_learning.apply_review`

## Zero-Touch Install Path
1. Install via HACS.
2. Restart Home Assistant.
3. Add integration from Devices & Services.
4. Keep auto-provision and auto-dashboard enabled in wizard.

The integration will create:
- missing grocery todo lists for inbox, each selected category, and `other`
- storage dashboards `Grocery` and `Grocery Admin` (admin-only) with cards based on your category order

## Integration Icon In HACS
To show a custom integration icon, submit branding for domain `grocery_learning` to Home Assistant brands.
Starter assets and notes are in `branding/README.md`.

## Legacy Compatibility
If you still use helper-driven YAML routing, keep using:
- `grocery_learning.sync_helpers`

This pushes learned terms into `input_text.grocery_learned_<category>` helpers when they exist.

## Service Examples
Learn a term:
```yaml
service: grocery_learning.learn_term
data:
  category: pantry
  term: vanilla coke
```

Forget a term:
```yaml
service: grocery_learning.forget_term
data:
  category: pantry
  term: vanilla coke
```

Sync to helper entities:
```yaml
service: grocery_learning.sync_helpers
```

Route item via integration:
```yaml
service: grocery_learning.route_item
data:
  item: coffee
  source_list: todo.grocery_inbox
  remove_from_source: true
  review_on_other: true
```

Apply pending review:
```yaml
service: grocery_learning.apply_review
data:
  category: pantry
  learn: true
```

## Roadmap To "Install And Works From Zero"
1. Remove remaining helper dependencies from review UX
2. Add guided onboarding for voice assistant intents
3. Continue HACS release hardening + docs
