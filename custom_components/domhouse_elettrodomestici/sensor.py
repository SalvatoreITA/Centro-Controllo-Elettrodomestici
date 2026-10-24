"""Sensori: potenza, consumi FTV/rete, energia, % pulita, durata, costo, cicli."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ApplianceCoordinator
from .entity import DomHouseEntity


@dataclass(frozen=True, kw_only=True)
class DHSensorDescription(SensorEntityDescription):
    """Descrittore con funzione di lettura dal coordinator."""

    value_fn: Callable[[ApplianceCoordinator], Any]
    attr_fn: Callable[[ApplianceCoordinator], dict[str, Any]] | None = None
    requires: str | None = None  # None=sempre; "pv"; "battery"; "clean" (pv o batteria)


SENSORS: tuple[DHSensorDescription, ...] = (
    DHSensorDescription(
        key="potenza",
        translation_key="potenza",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        value_fn=lambda c: c.power_w,
    ),
    DHSensorDescription(
        key="potenza_ftv",
        translation_key="potenza_ftv",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power-variant",
        value_fn=lambda c: c.power_ftv_w,
        requires="pv",
    ),
    DHSensorDescription(
        key="potenza_batteria",
        translation_key="potenza_batteria",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:home-battery",
        value_fn=lambda c: c.power_batt_w,
        requires="battery",
    ),
    DHSensorDescription(
        key="potenza_rete",
        translation_key="potenza_rete",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:transmission-tower",
        value_fn=lambda c: c.power_grid_w,
    ),
    DHSensorDescription(
        key="energia_pulita",
        translation_key="energia_pulita",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:leaf",
        value_fn=lambda c: c.clean_pct,
        requires="clean",
    ),
    DHSensorDescription(
        key="energia_pulita_ciclo",
        translation_key="energia_pulita_ciclo",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:leaf",
        value_fn=lambda c: c.clean_pct_cycle,
        requires="clean",
    ),
    DHSensorDescription(
        key="energia_ciclo",
        translation_key="energia_ciclo",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda c: round(c.energy_cycle_kwh, 3),
    ),
    DHSensorDescription(
        key="energia_ciclo_ftv",
        translation_key="energia_ciclo_ftv",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:solar-power-variant",
        value_fn=lambda c: round(c.energy_cycle_ftv_kwh, 3),
        requires="pv",
    ),
    DHSensorDescription(
        key="energia_ciclo_batteria",
        translation_key="energia_ciclo_batteria",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:home-battery",
        value_fn=lambda c: round(c.energy_cycle_batt_kwh, 3),
        requires="battery",
    ),
    DHSensorDescription(
        key="energia_ciclo_rete",
        translation_key="energia_ciclo_rete",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:transmission-tower",
        value_fn=lambda c: round(c.energy_cycle_grid_kwh, 3),
    ),
    DHSensorDescription(
        key="energia_totale",
        translation_key="energia_totale",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        value_fn=lambda c: round(c.energy_total_kwh, 3),
    ),
    DHSensorDescription(
        key="energia_totale_ftv",
        translation_key="energia_totale_ftv",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:solar-power-variant",
        value_fn=lambda c: round(c.energy_total_ftv_kwh, 3),
        requires="pv",
    ),
    DHSensorDescription(
        key="energia_totale_batteria",
        translation_key="energia_totale_batteria",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:home-battery",
        value_fn=lambda c: round(c.energy_total_batt_kwh, 3),
        requires="battery",
    ),
    DHSensorDescription(
        key="energia_totale_rete",
        translation_key="energia_totale_rete",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        icon="mdi:transmission-tower",
        value_fn=lambda c: round(c.energy_total_grid_kwh, 3),
    ),
    DHSensorDescription(
        key="durata_ciclo",
        translation_key="durata_ciclo",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-outline",
        value_fn=lambda c: c.cycle_duration_min,
    ),
    DHSensorDescription(
        key="costo_ciclo",
        translation_key="costo_ciclo",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="€",
        icon="mdi:currency-eur",
        value_fn=lambda c: c.cost_cycle,
    ),
    DHSensorDescription(
        key="cicli_totali",
        translation_key="cicli_totali",
        state_class=SensorStateClass.TOTAL_INCREASING,
        icon="mdi:counter",
        value_fn=lambda c: c.cycles_total,
    ),
    DHSensorDescription(
        key="ultimo_ciclo_fine",
        translation_key="ultimo_ciclo_fine",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        value_fn=lambda c: c.last_cycle_end,
    ),
    DHSensorDescription(
        key="ultimo_ciclo_durata",
        translation_key="ultimo_ciclo_durata",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        icon="mdi:timer-check-outline",
        value_fn=lambda c: c.last_cycle_duration_min,
    ),
    DHSensorDescription(
        key="ultimo_ciclo_costo",
        translation_key="ultimo_ciclo_costo",
        native_unit_of_measurement="€",
        icon="mdi:currency-eur",
        value_fn=lambda c: c.last_cycle_cost,
    ),
    DHSensorDescription(
        key="ultimo_reset",
        translation_key="ultimo_reset",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:restart",
        value_fn=lambda c: c.last_reset,
    ),
)

# Etichette dei periodi: chiave interna -> suffisso leggibile
_PERIOD_LABELS = {"day": "oggi", "month": "mese", "year": "anno"}


def _period_descriptions() -> tuple[DHSensorDescription, ...]:
    """Genera i sensori oggi/mese/anno (con periodo precedente negli attributi)."""
    out: list[DHSensorDescription] = []
    for period, lab in _PERIOD_LABELS.items():
        out.append(
            DHSensorDescription(
                key=f"energia_{lab}",
                translation_key=f"energia_{lab}",
                device_class=SensorDeviceClass.ENERGY,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
                suggested_display_precision=3,
                value_fn=lambda c, p=period: round(c.period_value(p, "energy"), 3),
                attr_fn=lambda c, p=period: {
                    "da_fotovoltaico": round(c.period_value(p, "energy_ftv"), 3),
                    "da_batteria": round(c.period_value(p, "energy_batt"), 3),
                    "da_rete": round(c.period_value(p, "energy_grid"), 3),
                    "perc_energia_pulita": c.period_clean_pct(p),
                    "precedente": round(c.period_last(p, "energy"), 3),
                    "perc_pulita_precedente": c.period_clean_pct(p, last=True),
                },
            )
        )
        out.append(
            DHSensorDescription(
                key=f"costo_{lab}",
                translation_key=f"costo_{lab}",
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement="€",
                icon="mdi:currency-eur",
                value_fn=lambda c, p=period: c.period_cost(p),
                attr_fn=lambda c, p=period: {"precedente": c.period_cost(p, last=True)},
            )
        )
        out.append(
            DHSensorDescription(
                key=f"cicli_{lab}",
                translation_key=f"cicli_{lab}",
                state_class=SensorStateClass.MEASUREMENT,
                icon="mdi:counter",
                value_fn=lambda c, p=period: int(c.period_value(p, "cycles")),
                attr_fn=lambda c, p=period: {
                    "precedente": int(c.period_last(p, "cycles"))
                },
            )
        )
        out.append(
            DHSensorDescription(
                key=f"tempo_{lab}",
                translation_key=f"tempo_{lab}",
                device_class=SensorDeviceClass.DURATION,
                state_class=SensorStateClass.MEASUREMENT,
                native_unit_of_measurement=UnitOfTime.HOURS,
                suggested_display_precision=2,
                icon="mdi:timer-sand",
                value_fn=lambda c, p=period: round(c.period_value(p, "runtime"), 2),
                attr_fn=lambda c, p=period: {
                    "precedente": round(c.period_last(p, "runtime"), 2)
                },
            )
        )
    return tuple(out)


WEEK_SENSOR = DHSensorDescription(
    key="riepilogo_settimana",
    translation_key="riepilogo_settimana",
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    icon="mdi:calendar-week",
    value_fn=lambda c: c.week_summary()[1],
    attr_fn=lambda c: c.week_summary()[0],
)


def _entity_enabled(requires: str | None, c: ApplianceCoordinator) -> bool:
    """Crea l'entità solo se la fonte richiesta è configurata."""
    if requires == "pv":
        return c.has_pv
    if requires == "battery":
        return c.has_battery
    if requires == "clean":
        return c.has_pv or c.has_battery
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Configura i sensori."""
    coordinator: ApplianceCoordinator = hass.data[DOMAIN][entry.entry_id]
    descriptions = (*SENSORS, *_period_descriptions(), WEEK_SENSOR)
    async_add_entities(
        DomHouseSensor(coordinator, desc)
        for desc in descriptions
        if _entity_enabled(desc.requires, coordinator)
    )


class DomHouseSensor(DomHouseEntity, SensorEntity):
    """Sensore generico guidato da un descrittore."""

    entity_description: DHSensorDescription

    def __init__(
        self, coordinator: ApplianceCoordinator, description: DHSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attr_fn is None:
            return None
        return self.entity_description.attr_fn(self.coordinator)
