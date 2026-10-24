"""Time: orario spegnimento automatico e fascia oraria notifiche."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import time as dt_time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ApplianceCoordinator
from .entity import DomHouseEntity


@dataclass(frozen=True, kw_only=True)
class DHTimeDescription(TimeEntityDescription):
    """Entità time guidata dal coordinator."""

    value_fn: Callable[[ApplianceCoordinator], dt_time | None]
    set_fn: Callable[[ApplianceCoordinator, dt_time], None]
    requires_plug: bool = False


TIMES: tuple[DHTimeDescription, ...] = (
    DHTimeDescription(
        key="spegnimento_automatico", translation_key="spegnimento_automatico",
        icon="mdi:timer-off-outline", entity_category=EntityCategory.CONFIG, requires_plug=True,
        value_fn=lambda c: c.off_time, set_fn=lambda c, v: c.set_off_time(v),
    ),
    DHTimeDescription(
        key="notifiche_inizio", translation_key="notifiche_inizio",
        icon="mdi:timer-outline", entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.notif_start, set_fn=lambda c, v: c.set_notif_time("start", v),
    ),
    DHTimeDescription(
        key="notifiche_fine", translation_key="notifiche_fine",
        icon="mdi:timer-outline", entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.notif_end, set_fn=lambda c, v: c.set_notif_time("end", v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura le entità time."""
    coordinator: ApplianceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        DHTime(coordinator, desc)
        for desc in TIMES
        if not desc.requires_plug or coordinator.has_switch
    )


class DHTime(DomHouseEntity, TimeEntity):
    """Entità time guidata da un descrittore."""

    entity_description: DHTimeDescription

    def __init__(
        self, coordinator: ApplianceCoordinator, description: DHTimeDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> dt_time | None:
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_value(self, value: dt_time) -> None:
        self.entity_description.set_fn(self.coordinator, value)
        self.async_write_ha_state()
