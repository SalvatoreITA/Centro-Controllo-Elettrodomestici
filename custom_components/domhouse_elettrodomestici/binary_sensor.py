"""Binary sensor: elettrodomestico in funzione."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, RESET_SCOPES, SERVICE_RESET
from .coordinator import ApplianceCoordinator
from .entity import DomHouseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura il binary sensor e il servizio di reset."""
    coordinator: ApplianceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([RunningBinarySensor(coordinator)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_RESET,
        {vol.Optional("azzera", default="tutto"): vol.In(RESET_SCOPES)},
        "async_handle_reset",
    )


class RunningBinarySensor(DomHouseEntity, BinarySensorEntity):
    """ON quando l'elettrodomestico sta lavorando (soglia + ritardi)."""

    _attr_translation_key = "in_funzione"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:state-machine"

    def __init__(self, coordinator: ApplianceCoordinator) -> None:
        super().__init__(coordinator, "in_funzione")

    @property
    def is_on(self) -> bool:
        return self.coordinator.running

    @property
    def extra_state_attributes(self) -> dict[str, float]:
        return {
            "sopra_soglia": self.coordinator._above,
            "ciclo_attivo": self.coordinator.cycle_active,
        }

    async def async_handle_reset(self, azzera: str = "tutto") -> None:
        """Gestisce il servizio di reset contatori."""
        await self.coordinator.async_reset_all(azzera)
