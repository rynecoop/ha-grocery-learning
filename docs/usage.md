# Usage Guide

![Main list](screenshots/main-list.png)

## Getting Around
- the app has a **bottom tab bar** with four screens, each one tap away:
  - `List` — your grocery list (and its list chips, quick add, and frequent items)
  - `Shop` — Shopping Mode
  - `Meals` — your saved recipes
  - `Plan` — the dated meal-plan calendar
- the `⋯` menu (top of the List screen) holds `App Settings`, `List Settings`, and `Activity`

## Daily Flow
1. Add items with Quick Add.
2. Tap a `FREQUENT` chip to add a common item without typing.
3. Add items by voice if you installed voice phrases.
4. When you head to the store, tap the `Shop` tab to enter Shopping Mode.
5. Work through the category sections in order.
6. Check items off as you go.
7. Clear completed items when you are done.

## Shopping Mode
- tap the `Shop` tab in the bottom bar to enter Shopping Mode
- Shopping Mode shows only the unchecked items, grouped in your list's category (store) order
- it has large tap targets, a progress bar (`X left`), and a quick add for anything you forgot
- checking an item off moves it out of the remaining list
- tap `Done` or the `List` tab to return to the full list

![Shopping Mode](screenshots/shopping-mode.png)

## Frequent Quick-Add
- the `FREQUENT` row above the list shows the items you add most often as one-tap chips
- tap a chip to add that item to the current list
- long-press a chip on touch, or right-click on desktop, to hide a suggestion you never want (it stays hidden even if it gets added again later)
- a suggestion appears only after you have added an item a couple of times
- anything already on the current list is hidden from the row
- the frequency tally is kept even when you `Clear Completed`, so your common items keep showing up

## Saved Meals
- tap the `Meals` tab in the bottom bar
- tap `New Meal`, give it a name, enter its ingredients one per line and (optionally) its directions one step per line, then `Create Meal`
- or tap `From current list` to turn whatever is on the active list into a new meal, then just name it
- tap a meal to open its detail view, which has two tabs:
  - `Add to list`: the ingredient checklist — every ingredient starts checked, so uncheck anything you already have or grew, then tap `Add N to list`
    - tap the pencil (✎) on an ingredient to tweak its text before adding, without editing the whole meal
    - use `All` / `None` to toggle every ingredient at once
    - each added ingredient is auto-categorized on the current list, just like a normal add
  - `Directions`: a numbered step list — tap a step to check it off as you cook
- `Edit` (in the detail view) changes a meal's name, ingredients, or directions; `Delete` removes it
- meals are stored locally and shared across your Home Assistant devices

![Meal directions cook mode](screenshots/meal-directions.png)

## Meal Planner (dated calendar)
- tap the `Plan` tab in the bottom bar
- the planner is a dated calendar: each row is a real date (e.g. "Monday Jul 6"), and today is highlighted
- use the `‹` and `›` arrows to move between weeks; `Today` jumps back to the current week
- for each day, pick a saved meal from `+ Add a meal…` to assign it; a day can hold more than one meal
- tap the `×` on a meal chip to remove it from that day
- `Add day` adds that day's ingredients to your list; `Add whole week to list` adds every meal planned in the week you are viewing
  - ingredients are combined and de-duplicated across meals, then shown in the same confirm checklist so you can uncheck anything you already have before adding
- nothing ever expires or clears on its own — past and future weeks stay exactly as you left them
- `Clear week` only clears the week currently shown; other weeks are untouched
- the plan is stored locally, syncs across devices, and is included in backups

![Meal planner dated calendar](screenshots/meal-planner.png)

![Saved Meals confirm checklist](screenshots/meals.png)

## Automatic Categories
- items are sorted into category sections automatically from a built-in knowledge of common grocery items
- matching prefers the most specific match, so multi-word items land correctly (for example `tomato sauce` goes to `Pantry`, not `Produce`)
- if an item still lands in `Other`, use the review buttons once to teach it (see Review and Learning below)

## List Management
- tap the active list chip to open `List Settings`
- use `List Settings` to:
  - rename the list
  - change list color
  - add categories
  - reorder categories
  - edit category names in place
  - remove categories
- long-press a list chip on touch or right-click on desktop to open list reorder controls
- drag a list chip to reorder your lists
- drag the handle (`⠿`) on the left of an item to reorder items within a category; the order is saved and syncs to other devices

## Duplicate Handling
- if an item already exists, the app shows a duplicate decision card
- choose `Add anyway` or `Skip`

## Review and Learning
- when an item doesn't match any category, a `Review Needed` card appears
- tap the category it belongs to — the app **learns** it, so future adds of that same item route there automatically
- tap `Keep Other` to leave it uncategorized (it stays in the `Other` section and isn't learned)

## Activity
- activity is available from `App Settings -> Tools -> Open activity`
- it shows recent list changes across the app

## Completed Items
- completed items move into the completed section
- restore by unchecking them
- use `Clear Completed` to purge completed history quickly

## Backup & Restore
- open `App Settings` from the menu (⋯), then expand `Tools`
- `Export backup` downloads a single JSON file containing all your lists, saved meals, item history, and learned categories
- `Import backup` restores from a file you previously exported — useful for moving to a new Home Assistant install or keeping a safety copy
- importing replaces your current data (you are asked to confirm first); if you use voice, run `Repair Local Setup` afterwards so the voice todo lists are re-provisioned

## Multi-Device Behavior
- open Local List Assist on two Home Assistant devices
- adding or completing an item on one device should appear on the other shortly after
- if one device is actively editing, it will refresh once editing closes

The panel adapts to phone-sized screens and follows your Home Assistant theme:

![Mobile view](screenshots/mobile-view.png)

