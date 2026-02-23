"""Config flow for Grocery Learning."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv

from .const import CONF_AUTO_ROUTE_INBOX, CONF_INBOX_ENTITY, CONF_NOTIFY_SERVICE, DOMAIN

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AUTO_ROUTE_INBOX, default=True): bool,
        vol.Required(CONF_INBOX_ENTITY, default="todo.grocery_inbox"): cv.string,
        vol.Optional(CONF_NOTIFY_SERVICE, default=""): cv.string,
    }
)


class GroceryLearningConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Grocery Learning config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle first step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        if user_input is not None:
            return self.async_create_entry(title="Grocery Learning", data=user_input)
        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA)
