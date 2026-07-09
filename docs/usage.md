# Usage Guide

![Main list](screenshots/main-list.png)

## Daily Flow
1. Add items with Quick Add.
2. Tap a `FREQUENT` chip to add a common item without typing.
3. Add items by voice if you installed voice phrases.
4. When you head to the store, tap the cart button (🛒) to enter Shopping Mode.
5. Work through the category sections in order.
6. Check items off as you go.
7. Clear completed items when you are done.

## Shopping Mode
- tap the cart button (🛒) in the header to enter Shopping Mode
- Shopping Mode shows only the unchecked items, grouped in your list's category (store) order
- it has large tap targets, a progress bar (`X left`), and a quick add for anything you forgot
- checking an item off moves it out of the remaining list
- tap `Done` to return to the full list

![Shopping Mode](screenshots/shopping-mode.png)

## Frequent Quick-Add
- the `FREQUENT` row above the list shows the items you add most often as one-tap chips
- tap a chip to add that item to the current list
- a suggestion appears only after you have added an item a couple of times
- anything already on the current list is hidden from the row
- the frequency tally is kept even when you `Clear Completed`, so your common items keep showing up

## Saved Meals
- open `Meals` from the menu (⋯)
- tap `New Meal`, give it a name, and enter its ingredients one per line, then `Create Meal`
- tap `Add to list` on a meal to open a confirm checklist
- every ingredient starts checked; uncheck anything you already have or grew, then tap `Add N to list`
- use `All` / `None` to toggle every ingredient at once
- each added ingredient is auto-categorized on the current list, just like a normal add
- `Edit` changes a meal's name or ingredients; `Delete` removes it
- meals are stored locally and shared across your Home Assistant devices

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
- unknown items may land in `Other`
- use the review buttons once to assign the correct category
- future adds of the same term should route correctly

## Activity
- activity is available from `App Settings -> Tools -> Open activity`
- it shows recent list changes across the app

## Completed Items
- completed items move into the completed section
- restore by unchecking them
- use `Clear Completed` to purge completed history quickly

## Multi-Device Behavior
- open Local List Assist on two Home Assistant devices
- adding or completing an item on one device should appear on the other shortly after
- if one device is actively editing, it will refresh once editing closes

The panel adapts to phone-sized screens and follows your Home Assistant theme:

![Mobile view](screenshots/mobile-view.png)

