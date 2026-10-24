"""Entità base condivisa."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ApplianceCoordinator


class DomHouseEntity(CoordinatorEntity[ApplianceCoordinator]):
    """Base: raggruppa tutte le entità sotto un unico device per elettrodomestico."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ApplianceCoordinator, key: str) -> None:
        """Inizializza l'entità."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.appliance_name,
            manufacturer="DomHouse.it",
            model="Centro Controllo Elettrodomestici",
        )
