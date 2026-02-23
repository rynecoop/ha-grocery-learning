# Grocery Learning (Custom Integration)

This integration is the foundation for a shareable "grocery list routing + review + learn" system.

## Current Scope (v0.1.0)
- Config entry (`Settings -> Devices & Services -> Add Integration -> Grocery Learning`)
- Persistent learned term storage in HA storage
- Services:
  - `grocery_learning.learn_term`
  - `grocery_learning.forget_term`
  - `grocery_learning.sync_helpers`
  - `grocery_learning.route_item`
  - `grocery_learning.apply_review`

## How It Connects To Your Existing Setup
Your current YAML router already reads helper entities such as:
- `input_text.grocery_learned_pantry`
- `input_text.grocery_learned_dairy`
- etc.

After learning terms through integration services, call:
- `grocery_learning.sync_helpers`

This copies stored learned terms into those helpers so routing uses them immediately.

## Install (Local Custom Component)
1. Ensure this folder exists:
   - `/config/custom_components/grocery_learning`
2. Restart Home Assistant.
3. Add integration via UI:
   - `Settings -> Devices & Services -> Add Integration -> Grocery Learning`

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
1. Create category list entities directly from integration
2. Replace YAML scripts/automations with integration-native workflow
3. Ship packaged dashboards and one-click setup wizard
4. Publish as HACS repository with releases and docs
