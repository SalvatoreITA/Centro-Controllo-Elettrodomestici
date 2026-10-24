"""Switch: presa smart + preferenze notifiche e abilitazione auto-off."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ApplianceCoordinator
from .entity import DomHouseEntity


@dataclass(frozen=True, kw_only=True)
class DHSwitchDescription(SwitchEntityDescription):
    """Switch di preferenza guidato dal coordinator."""

    value_fn: Callable[[ApplianceCoordinator], bool]
    set_fn: Callable[[ApplianceCoordinator, bool], None]
    requires_plug: bool = False


SWITCHES: tuple[DHSwitchDescription, ...] = (
    DHSwitchDescription(
        key="notifica_push", translation_key="notifica_push",
        icon="mdi:cellphone-message", entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.pref_push, set_fn=lambda c, v: c.set_flag("pref_push", v),
    ),
    DHSwitchDescription(
        key="notifica_google", translation_key="notifica_google",
        icon="mdi:google-assistant", entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.pref_google, set_fn=lambda c, v: c.set_flag("pref_google", v),
    ),
    DHSwitchDescription(
        key="notifica_alexa", translation_key="notifica_alexa",
        icon="mdi:microphone", entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.pref_alexa, set_fn=lambda c, v: c.set_flag("pref_alexa", v),
    ),
    DHSwitchDescription(
        key="notifica_ha", translation_key="notifica_ha",
        icon="mdi:bell-ring-outline", entity_category=EntityCategory.CONFIG,
        value_fn=lambda c: c.pref_ha, set_fn=lambda c, v: c.set_flag("pref_ha", v),
    ),
    DHSwitchDescription(
        key="spegnimento_auto", translation_key="spegnimento_auto",
        icon="mdi:timer-off-outline", entity_category=EntityCategory.CONFIG, requires_plug=True,
        value_fn=lambda c: c.auto_off_enabled, set_fn=lambda c, v: c.set_flag("auto_off_enabled", v),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura gli switch."""
    coordinator: ApplianceCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = []
    if coordinator.has_switch:
        entities.append(PlugSwitch(coordinator))
    for desc in SWITCHES:
        if not desc.requires_plug or coordinator.has_switch:
            entities.append(DHPrefSwitch(coordinator, desc))
    async_add_entities(entities)


class PlugSwitch(DomHouseEntity, SwitchEntity):
    """Rispecchia e comanda la presa reale configurata."""

    _attr_translation_key = "presa"
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator: ApplianceCoordinator) -> None:
        super().__init__(coordinator, "presa")

    @property
    def is_on(self) -> bool:
        return self.coordinator.plug_is_on

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_turn_plug(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_turn_plug(False)


class DHPrefSwitch(DomHouseEntity, SwitchEntity):
    """Switch di preferenza (notifiche, abilita auto-off)."""

    entity_description: DHSwitchDescription

    def __init__(
        self, coordinator: ApplianceCoordinator, description: DHSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.entity_description.set_fn(self.coordinator, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.entity_description.set_fn(self.coordinator, False)
        self.async_write_ha_state()
