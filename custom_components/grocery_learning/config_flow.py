"""Config flow for Local Grocery Assistant."""

from __future__ import annotations

import re

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_CATEGORIES,
    CONF_DASHBOARD_NAME,
    CONF_EXPERIMENTAL_MULTILIST,
    CONF_INBOX_ENTITY,
    DEFAULT_CATEGORIES,
    DOMAIN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_DASHBOARD_NAME, default="Local List Assist"): cv.string,
        vol.Required(CONF_CATEGORIES, default=",".join(DEFAULT_CATEGORIES)): cv.string,
    }
)


def _normalize_categories(raw: str) -> list[str]:
    normalized = raw.replace("\n", ",")
    items = [part.strip().lower() for part in normalized.split(",")]
    out: list[str] = []
    for item in items:
        slug = re.sub(r"[^a-z0-9]+", "_", item).strip("_")
        if not slug or slug == "other":
            continue
        if slug not in out:
            out.append(slug)
    return out or list(DEFAULT_CATEGORIES)


class GroceryLearningConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Local List Assist config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle first step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            user_input[CONF_CATEGORIES] = _normalize_categories(user_input.get(CONF_CATEGORIES, ""))
            user_input[CONF_EXPERIMENTAL_MULTILIST] = True
            user_input[CONF_INBOX_ENTITY] = "todo.grocery_inbox"
            user_input["auto_dashboard"] = True
            user_input["auto_provision"] = True
            user_input["auto_route_inbox"] = True
            user_input["default_grocery_categories"] = True
            user_input["debug_mode"] = False
            user_input["notify_service"] = ""
            return self.async_create_entry(title="Local List Assist", data=user_input)
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return GroceryLearningOptionsFlow(config_entry)


class GroceryLearningOptionsFlow(config_entries.OptionsFlow):
    """Handle Local List Assist options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        current_data = {**self._config_entry.data, **self._config_entry.options}
        if user_input is not None:
            user_input[CONF_CATEGORIES] = _normalize_categories(user_input.get(CONF_CATEGORIES, ""))
            merged = dict(self._config_entry.options)
            merged.update(user_input)
            merged[CONF_EXPERIMENTAL_MULTILIST] = True
            merged["auto_dashboard"] = True
            merged["auto_provision"] = True
            merged["auto_route_inbox"] = True
            merged[CONF_INBOX_ENTITY] = "todo.grocery_inbox"
            merged["default_grocery_categories"] = True
            merged["debug_mode"] = False
            merged["notify_service"] = ""
            return self.async_create_entry(data=merged)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_DASHBOARD_NAME,
                    default=str(current_data.get(CONF_DASHBOARD_NAME, "Local List Assist")).strip() or "Local List Assist",
                ): cv.string,
                vol.Required(
                    CONF_CATEGORIES,
                    default=",".join(current_data.get(CONF_CATEGORIES, list(DEFAULT_CATEGORIES))),
                ): cv.string,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
