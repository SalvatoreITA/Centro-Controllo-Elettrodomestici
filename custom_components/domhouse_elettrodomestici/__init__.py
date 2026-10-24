"""DomHouse Centro Controllo Elettrodomestici."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_BATTERY_BIDIR,
    CONF_BATTERY_DISCHARGE,
    CONF_BATTERY_SIGN,
    CONF_COST_PER_KWH,
    CONF_ENTRY_TYPE,
    CONF_PV_EXPORT,
    CONF_PV_IMPORT,
    CONF_PV_PRODUCTION,
    COST_DATA_KEY,
    DEFAULT_BATTERY_SIGN,
    DEFAULT_COST_PER_KWH,
    DOMAIN,
    ENTRY_TYPE_COST,
    ENTRY_TYPE_HUB,
    HUB_DATA_KEY,
    PLATFORMS,
    STORAGE_VERSION,
)
from .coordinator import ApplianceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura un impianto (hub) o un elettrodomestico."""
    hass.data.setdefault(DOMAIN, {})

    entry_type = entry.data.get(CONF_ENTRY_TYPE)
    if entry_type == ENTRY_TYPE_HUB:
        return await _async_setup_hub(hass, entry)
    if entry_type == ENTRY_TYPE_COST:
        return await _async_setup_cost(hass, entry)

    return await _async_setup_appliance(hass, entry)


async def _async_setup_hub(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Carica i dati d'impianto condivisi (FV + costo)."""
    cfg = {**entry.data, **entry.options}
    hass.data[DOMAIN][HUB_DATA_KEY] = {
        "pv_production": cfg.get(CONF_PV_PRODUCTION) or None,
        "pv_export": cfg.get(CONF_PV_EXPORT) or None,
        "pv_import": cfg.get(CONF_PV_IMPORT) or None,
        "battery_bidir": cfg.get(CONF_BATTERY_BIDIR) or None,
        "battery_discharge": cfg.get(CONF_BATTERY_DISCHARGE) or None,
        "battery_sign": cfg.get(CONF_BATTERY_SIGN) or DEFAULT_BATTERY_SIGN,
        "cost_per_kwh": float(cfg.get(CONF_COST_PER_KWH, DEFAULT_COST_PER_KWH)),
    }
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_setup_cost(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Carica la scheda Costo energia (solo €/kWh), condivisa da tutti."""
    cfg = {**entry.data, **entry.options}
    hass.data[DOMAIN][COST_DATA_KEY] = {
        "cost_per_kwh": float(cfg.get(CONF_COST_PER_KWH, DEFAULT_COST_PER_KWH)),
    }
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_setup_appliance(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Configura un elettrodomestico."""
    store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}")
    stored = await store.async_load()

    coordinator = ApplianceCoordinator(hass, entry, store)
    await coordinator.async_restore(stored)

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Rimuove un impianto o un elettrodomestico."""
    entry_type = entry.data.get(CONF_ENTRY_TYPE)
    if entry_type == ENTRY_TYPE_HUB:
        hass.data[DOMAIN].pop(HUB_DATA_KEY, None)
        return True
    if entry_type == ENTRY_TYPE_COST:
        hass.data[DOMAIN].pop(COST_DATA_KEY, None)
        return True

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: ApplianceCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Ricarica la config entry quando cambiano le opzioni."""
    await hass.config_entries.async_reload(entry.entry_id)
