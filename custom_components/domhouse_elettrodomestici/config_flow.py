"""Config flow per DomHouse Centro Controllo Elettrodomestici."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_BATTERY_BIDIR,
    CONF_BATTERY_DISCHARGE,
    CONF_BATTERY_SIGN,
    CONF_COST_PER_KWH,
    CONF_ENTRY_TYPE,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_PV_EXPORT,
    CONF_PV_IMPORT,
    CONF_PV_PRODUCTION,
    CONF_SWITCH,
    CONF_VOICE_PHRASE,
    DEFAULT_BATTERY_SIGN,
    DEFAULT_COST_PER_KWH,
    DEFAULT_VOICE_PHRASE,
    DOMAIN,
    ENTRY_TYPE_APPLIANCE,
    ENTRY_TYPE_COST,
    ENTRY_TYPE_HUB,
)

_HUB_UNIQUE_ID = "domhouse_impianto_ftv"
_COST_UNIQUE_ID = "domhouse_costo_energia"

_POWER_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="power")
)
_SWITCH_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain=["switch", "input_boolean"])
)
_COST_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=0, max=5, step=0.001, mode=selector.NumberSelectorMode.BOX
    )
)
_BATTERY_SIGN_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value="positive", label="Positivo = scarica"),
            selector.SelectOptionDict(value="negative", label="Negativo = scarica"),
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)


def _opt(key: str, defaults: dict[str, Any], sel: Any) -> dict:
    """Campo opzionale che precompila il valore corrente se presente."""
    if defaults.get(key):
        return {vol.Optional(key, default=defaults[key]): sel}
    return {vol.Optional(key): sel}


def _hub_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema dell'impianto: sensori FV e batteria, condivisi da tutti."""
    fields: dict[Any, Any] = {}
    fields.update(_opt(CONF_PV_PRODUCTION, defaults, _POWER_SENSOR_SELECTOR))
    fields.update(_opt(CONF_PV_EXPORT, defaults, _POWER_SENSOR_SELECTOR))
    fields.update(_opt(CONF_PV_IMPORT, defaults, _POWER_SENSOR_SELECTOR))
    fields.update(_opt(CONF_BATTERY_BIDIR, defaults, _POWER_SENSOR_SELECTOR))
    fields.update(_opt(CONF_BATTERY_DISCHARGE, defaults, _POWER_SENSOR_SELECTOR))
    fields[
        vol.Optional(
            CONF_BATTERY_SIGN,
            default=defaults.get(CONF_BATTERY_SIGN, DEFAULT_BATTERY_SIGN),
        )
    ] = _BATTERY_SIGN_SELECTOR
    return vol.Schema(fields)


def _cost_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Scheda Costo energia: solo €/kWh, condiviso da tutti gli elettrodomestici."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_COST_PER_KWH,
                default=defaults.get(CONF_COST_PER_KWH, DEFAULT_COST_PER_KWH),
            ): _COST_SELECTOR
        }
    )


def _appliance_schema(defaults: dict[str, Any], *, with_name: bool) -> vol.Schema:
    """Schema elettrodomestico. I sensori FV sono override opzionali dell'impianto."""
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, ""))] = str
    if defaults.get(CONF_POWER_SENSOR):
        fields[vol.Required(CONF_POWER_SENSOR, default=defaults[CONF_POWER_SENSOR])] = (
            _POWER_SENSOR_SELECTOR
        )
    else:
        fields[vol.Required(CONF_POWER_SENSOR)] = _POWER_SENSOR_SELECTOR
    fields.update(_opt(CONF_SWITCH, defaults, _SWITCH_SELECTOR))
    fields.update(_opt(CONF_PV_PRODUCTION, defaults, _POWER_SENSOR_SELECTOR))
    fields.update(_opt(CONF_PV_EXPORT, defaults, _POWER_SENSOR_SELECTOR))
    fields.update(_opt(CONF_PV_IMPORT, defaults, _POWER_SENSOR_SELECTOR))
    fields[
        vol.Optional(
            CONF_VOICE_PHRASE,
            default=defaults.get(CONF_VOICE_PHRASE, DEFAULT_VOICE_PHRASE),
        )
    ] = selector.TextSelector()
    return vol.Schema(fields)


class DomHouseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Aggiunta di un impianto o di un elettrodomestico."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Scelta iniziale: impianto FV o elettrodomestico."""
        return self.async_show_menu(
            step_id="user", menu_options=["hub", "cost", "appliance"]
        )

    async def async_step_hub(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Impianto FV + costo (uno solo)."""
        await self.async_set_unique_id(_HUB_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            data = {**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_HUB}
            return self.async_create_entry(title="Impianto fotovoltaico", data=data)
        return self.async_show_form(step_id="hub", data_schema=_hub_schema({}))

    async def async_step_cost(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Scheda Costo energia (una sola)."""
        await self.async_set_unique_id(_COST_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            data = {**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_COST}
            return self.async_create_entry(title="Costo energia", data=data)
        return self.async_show_form(step_id="cost", data_schema=_cost_schema({}))

    async def async_step_appliance(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Nuovo elettrodomestico."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(slugify(user_input[CONF_NAME]))
            self._abort_if_unique_id_configured()
            data = {**user_input, CONF_ENTRY_TYPE: ENTRY_TYPE_APPLIANCE}
            return self.async_create_entry(title=user_input[CONF_NAME], data=data)
        return self.async_show_form(
            step_id="appliance",
            data_schema=_appliance_schema({}, with_name=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> DomHouseOptionsFlow:
        """Restituisce l'options flow."""
        return DomHouseOptionsFlow(config_entry)


class DomHouseOptionsFlow(config_entries.OptionsFlow):
    """Modifica di un impianto o di un elettrodomestico esistente."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Inizializza l'options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Modifica le opzioni, in base al tipo di entry."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = {**self._entry.data, **self._entry.options}
        entry_type = self._entry.data.get(CONF_ENTRY_TYPE)
        if entry_type == ENTRY_TYPE_HUB:
            schema = _hub_schema(current)
        elif entry_type == ENTRY_TYPE_COST:
            schema = _cost_schema(current)
        else:
            schema = _appliance_schema(current, with_name=False)
        return self.async_show_form(step_id="init", data_schema=schema)
