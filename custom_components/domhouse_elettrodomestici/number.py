"""Number: soglia e ritardi regolabili a runtime (come gli input_number del package)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfPower, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    MAX_DELAY_OFF_MIN,
    MAX_DELAY_ON_S,
    MAX_THRESHOLD_W,
    MIN_DELAY_OFF_MIN,
    MIN_DELAY_ON_S,
    MIN_THRESHOLD_W,
)
from .coordinator import ApplianceCoordinator
from .entity import DomHouseEntity


@dataclass(frozen=True, kw_only=True)
class DHNumberDescription(NumberEntityDescription):
    """Descrittore number con getter/setter sul coordinator."""

    value_fn: Callable[[ApplianceCoordinator], float]
    set_fn: Callable[[ApplianceCoordinator, float], None]


NUMBERS: tuple[DHNumberDescription, ...] = (
    DHNumberDescription(
        key="soglia",
        translation_key="soglia",
        native_min_value=MIN_THRESHOLD_W,
        native_max_value=MAX_THRESHOLD_W,
        native_step=1,
        native_unit_of_measurement=UnitOfPower.WATT,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:flash",
        value_fn=lambda c: c.threshold_w,
        set_fn=lambda c, v: c.set_threshold(v),
    ),
    DHNumberDescription(
        key="ritardo_on",
        translation_key="ritardo_on",
        native_min_value=MIN_DELAY_ON_S,
        native_max_value=MAX_DELAY_ON_S,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:timer-play-outline",
        value_fn=lambda c: c.delay_on_s,
        set_fn=lambda c, v: c.set_delay_on(v),
    ),
    DHNumberDescription(
        key="ritardo_off",
        translation_key="ritardo_off",
        native_min_value=MIN_DELAY_OFF_MIN,
        native_max_value=MAX_DELAY_OFF_MIN,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:timer-stop-outline",
        value_fn=lambda c: c.delay_off_min,
        set_fn=lambda c, v: c.set_delay_off(v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura le entità number."""
    coordinator: ApplianceCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DomHouseNumber(coordinator, desc) for desc in NUMBERS)


class DomHouseNumber(DomHouseEntity, NumberEntity):
    """Number guidato da un descrittore."""

    entity_description: DHNumberDescription

    def __init__(
        self, coordinator: ApplianceCoordinator, description: DHNumberDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return self.entity_description.value_fn(self.coordinator)

    async def async_set_native_value(self, value: float) -> None:
        self.entity_description.set_fn(self.coordinator, value)
        self.async_write_ha_state()
