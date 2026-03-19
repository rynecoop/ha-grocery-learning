# Setup Guide

## Prerequisites
- Home Assistant installed and running
- HACS installed if you want normal update flow

## Install With HACS
1. Open HACS.
2. Install `Local List Assist`.
3. Restart Home Assistant.
4. Go to `Settings -> Devices & Services`.
5. Add the `Local List Assist` integration.
6. Open `Local List Assist` from the sidebar.

## Manual Install
1. Copy `custom_components/grocery_learning` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings -> Devices & Services`.

## First Run
1. Open `Local List Assist`.
2. Create your first list with the `+` button.
3. Open `App Settings` if you want to:
   - change the dashboard name
   - set default categories
   - install voice phrases
   - run repair/provisioning
4. Open `List Settings` on the active list if you want to:
   - rename the list
   - change list color
   - add, reorder, edit, or remove categories
   - update voice aliases

## Navigation Model
- `+` button: create list
- active list chip: open `List Settings`
- long-press on touch or right-click on desktop: reorder lists
- hamburger menu: open the right-side menu
- `Activity`: open from `App Settings -> Tools`

## Notes
- category order controls section order in the main list view
- category names can be edited later without deleting and recreating them
- required helpers and todo lists can be recreated from `App Settings -> Repair Local Setup`
- open dashboards on multiple devices now refresh near-real-time when one device changes list data

