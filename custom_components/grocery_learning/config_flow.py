"""Config flow for Grocery Learning."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class GroceryLearningConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle Grocery Learning config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle first step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Grocery Learning", data={})
