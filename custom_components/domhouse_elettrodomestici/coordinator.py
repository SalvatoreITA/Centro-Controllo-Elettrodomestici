"""Coordinator: logica di rilevamento ciclo, integrazione energia e split FTV/rete."""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COST_PER_KWH,
    CONF_DELAY_OFF_MIN,
    CONF_DELAY_ON_S,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_PV_EXPORT,
    CONF_PV_IMPORT,
    CONF_PV_PRODUCTION,
    CONF_SWITCH,
    CONF_THRESHOLD_W,
    CONF_VOICE_PHRASE,
    COST_DATA_KEY,
    DEFAULT_COST_PER_KWH,
    DEFAULT_DELAY_OFF_MIN,
    DEFAULT_DELAY_ON_S,
    DEFAULT_THRESHOLD_W,
    DEFAULT_VOICE_PHRASE,
    DOMAIN,
    EVENT_CYCLE_FINISHED,
    HUB_DATA_KEY,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

_SAVE_INTERVAL_S = 300  # salva i totali lifetime al massimo ogni 5 minuti

# Metriche monotòne da cui si derivano le statistiche di periodo
METRICS = ("energy", "energy_ftv", "energy_batt", "energy_grid", "cycles", "runtime")
PERIODS = ("day", "month", "year")
_WEEKDAYS = ("lunedi", "martedi", "mercoledi", "giovedi", "venerdi", "sabato", "domenica")


class ApplianceCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gestisce un singolo elettrodomestico."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, store: Store) -> None:
        """Inizializza il coordinator."""
        self._entry = entry
        self.entry_id = entry.entry_id
        self._store = store
        cfg = {**entry.data, **entry.options}

        self.appliance_name: str = cfg.get(CONF_NAME, entry.title)
        self.voice_phrase: str = (
            str(cfg.get(CONF_VOICE_PHRASE) or "").strip() or DEFAULT_VOICE_PHRASE
        )
        self._power_sensor: str = cfg[CONF_POWER_SENSOR]
        self._switch: str | None = cfg.get(CONF_SWITCH) or None
        self._pv_production: str | None = cfg.get(CONF_PV_PRODUCTION) or None
        self._pv_export: str | None = cfg.get(CONF_PV_EXPORT) or None
        self._pv_import: str | None = cfg.get(CONF_PV_IMPORT) or None
        raw_cost = cfg.get(CONF_COST_PER_KWH)
        self._cost_override: float | None = (
            float(raw_cost) if raw_cost not in (None, "") else None
        )

        # Parametri regolabili a runtime (dalle entità number)
        self.threshold_w: float = float(cfg.get(CONF_THRESHOLD_W, DEFAULT_THRESHOLD_W))
        self.delay_on_s: int = int(cfg.get(CONF_DELAY_ON_S, DEFAULT_DELAY_ON_S))
        self.delay_off_min: int = int(cfg.get(CONF_DELAY_OFF_MIN, DEFAULT_DELAY_OFF_MIN))

        # Stato di integrazione
        self._last_power: float = 0.0
        self._last_frac_ftv: float = 0.0
        self._last_frac_batt: float = 0.0
        self._last_time: datetime | None = None

        # Stato soglia / ciclo
        self._above: bool = False
        self.running: bool = False
        self._pending_on = None
        self._pending_off = None

        self.cycle_active: bool = False
        self._cycle_start: datetime | None = None
        self.energy_cycle_kwh: float = 0.0
        self.energy_cycle_ftv_kwh: float = 0.0
        self.energy_cycle_batt_kwh: float = 0.0
        self.energy_cycle_grid_kwh: float = 0.0

        # Totali lifetime (per utility_meter esterni)
        self.energy_total_kwh: float = 0.0
        self.energy_total_ftv_kwh: float = 0.0
        self.energy_total_batt_kwh: float = 0.0
        self.energy_total_grid_kwh: float = 0.0

        self.cycles_total: int = 0
        self.runtime_total_h: float = 0.0

        # Statistiche di periodo (baseline = valore all'inizio del periodo)
        self._baseline: dict[str, dict[str, float]] = {
            p: {m: 0.0 for m in METRICS} for p in PERIODS
        }
        self._last_period: dict[str, dict[str, float]] = {
            p: {m: 0.0 for m in METRICS} for p in PERIODS
        }
        self._week: dict[int, dict[str, float]] = {}
        self._baseline_ready: bool = False

        # Spegnimento automatico a orario
        self._off_time: dt_time | None = None
        self.auto_off_enabled: bool = False

        # Preferenze notifiche (lette dal blueprint tramite l'evento di fine ciclo)
        self.pref_push: bool = True
        self.pref_google: bool = False
        self.pref_alexa: bool = False
        self.pref_ha: bool = False
        self.last_reset: datetime | None = None
        self._notif_start: dt_time = dt_time(8, 0)
        self._notif_end: dt_time = dt_time(22, 0)

        self.last_cycle_end: datetime | None = None
        self.last_cycle_duration_min: float = 0.0
        self.last_cycle_energy_kwh: float = 0.0
        self.last_cycle_ftv_kwh: float = 0.0
        self.last_cycle_batt_kwh: float = 0.0
        self.last_cycle_grid_kwh: float = 0.0
        self.last_cycle_cost: float = 0.0

        self._unsub_state = None
        self._unsub_timer = None
        self._unsub_midnight = None
        self._unsub_off = None
        self._unsub_switch = None
        self._last_save: datetime | None = None

        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_{self.appliance_name}")
        self.data = {}

    # ------------------------------------------------------------------ setup

    async def async_restore(self, stored: dict[str, Any] | None) -> None:
        """Ripristina lo stato persistito."""
        if not stored:
            return
        self.energy_total_kwh = float(stored.get("energy_total_kwh", 0.0))
        self.energy_total_ftv_kwh = float(stored.get("energy_total_ftv_kwh", 0.0))
        self.energy_total_batt_kwh = float(stored.get("energy_total_batt_kwh", 0.0))
        self.energy_total_grid_kwh = float(stored.get("energy_total_grid_kwh", 0.0))
        self.cycles_total = int(stored.get("cycles_total", 0))
        self.runtime_total_h = float(stored.get("runtime_total_h", 0.0))

        # Statistiche di periodo
        for period in PERIODS:
            for metric in METRICS:
                if period in stored.get("baseline", {}):
                    self._baseline[period][metric] = float(
                        stored["baseline"][period].get(metric, 0.0)
                    )
                if period in stored.get("last_period", {}):
                    self._last_period[period][metric] = float(
                        stored["last_period"][period].get(metric, 0.0)
                    )
        if "baseline" in stored:
            self._baseline_ready = True
        for wd_str, vals in stored.get("week", {}).items():
            self._week[int(wd_str)] = {k: float(v) for k, v in vals.items()}
        if stored.get("off_time"):
            try:
                self._off_time = dt_time.fromisoformat(stored["off_time"])
            except (ValueError, TypeError):
                self._off_time = None
        self.auto_off_enabled = bool(stored.get("auto_off_enabled", False))
        self.pref_push = bool(stored.get("pref_push", True))
        self.pref_google = bool(stored.get("pref_google", False))
        self.pref_alexa = bool(stored.get("pref_alexa", False))
        self.pref_ha = bool(stored.get("pref_ha", False))
        if stored.get("last_reset"):
            self.last_reset = dt_util.parse_datetime(stored["last_reset"])
        for key, attr in (("notif_start", "_notif_start"), ("notif_end", "_notif_end")):
            if stored.get(key):
                try:
                    setattr(self, attr, dt_time.fromisoformat(stored[key]))
                except (ValueError, TypeError):
                    pass
        self.last_cycle_duration_min = float(stored.get("last_cycle_duration_min", 0.0))
        self.last_cycle_energy_kwh = float(stored.get("last_cycle_energy_kwh", 0.0))
        self.last_cycle_ftv_kwh = float(stored.get("last_cycle_ftv_kwh", 0.0))
        self.last_cycle_batt_kwh = float(stored.get("last_cycle_batt_kwh", 0.0))
        self.last_cycle_grid_kwh = float(stored.get("last_cycle_grid_kwh", 0.0))
        self.last_cycle_cost = float(stored.get("last_cycle_cost", 0.0))
        if stored.get("last_cycle_end"):
            self.last_cycle_end = dt_util.parse_datetime(stored["last_cycle_end"])
        # Stato del ciclo corrente/ultimo (così non si azzera ai riavvii di HA)
        self.energy_cycle_kwh = float(stored.get("energy_cycle_kwh", 0.0))
        self.energy_cycle_ftv_kwh = float(stored.get("energy_cycle_ftv_kwh", 0.0))
        self.energy_cycle_batt_kwh = float(stored.get("energy_cycle_batt_kwh", 0.0))
        self.energy_cycle_grid_kwh = float(stored.get("energy_cycle_grid_kwh", 0.0))
        self.cycle_active = bool(stored.get("cycle_active", False))
        if stored.get("cycle_start"):
            self._cycle_start = dt_util.parse_datetime(stored["cycle_start"])
        # parametri runtime, se l'utente li aveva modificati
        if "threshold_w" in stored:
            self.threshold_w = float(stored["threshold_w"])
        if "delay_on_s" in stored:
            self.delay_on_s = int(stored["delay_on_s"])
        if "delay_off_min" in stored:
            self.delay_off_min = int(stored["delay_off_min"])

    @callback
    def async_start(self) -> None:
        """Avvia i listener."""
        self._last_time = dt_util.utcnow()
        # Al primissimo avvio la baseline parte dai valori correnti (periodi a 0)
        if not self._baseline_ready:
            for period in PERIODS:
                for metric in METRICS:
                    self._baseline[period][metric] = self._current(metric)
            self._baseline_ready = True
        self._unsub_state = async_track_state_change_event(
            self.hass, [self._power_sensor], self._handle_power_event
        )
        self._unsub_timer = async_track_time_interval(
            self.hass, self._handle_tick, SCAN_INTERVAL
        )
        # Reset statistiche poco dopo la mezzanotte locale
        self._unsub_midnight = async_track_time_change(
            self.hass, self._handle_midnight, hour=0, minute=0, second=10
        )
        self._register_off_trigger()
        # Segue lo switch reale per riflettere subito on/off sulla presa (card)
        if self._switch:
            self._unsub_switch = async_track_state_change_event(
                self.hass, [self._switch], self._handle_switch_event
            )
        self.hass.async_create_task(self._async_update())

    async def async_shutdown(self) -> None:
        """Ferma i listener e salva lo stato."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None
        if self._unsub_midnight:
            self._unsub_midnight()
            self._unsub_midnight = None
        if self._unsub_off:
            self._unsub_off()
            self._unsub_off = None
        if self._unsub_switch:
            self._unsub_switch()
            self._unsub_switch = None
        self._cancel_pending()
        await self._async_save()
        await super().async_shutdown()

    # ------------------------------------------------------------- lettura stati

    def _get_float(self, entity_id: str | None) -> float | None:
        """Legge un'entità come float, None se non disponibile."""
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable", "none", ""):
            return None
        try:
            return float(state.state)
        except (ValueError, TypeError):
            return None

    def _pv_entities(self) -> tuple[str | None, str | None, str | None]:
        """Sensori FV: override locale, altrimenti quelli dell'impianto (hub)."""
        hub = self.hass.data.get(DOMAIN, {}).get(HUB_DATA_KEY, {})
        prod = self._pv_production or hub.get("pv_production")
        exp = self._pv_export or hub.get("pv_export")
        imp = self._pv_import or hub.get("pv_import")
        return prod, exp, imp

    def _battery_entities(self) -> tuple[str | None, str | None, str]:
        """Sensori batteria dall'impianto: (bidirezionale, scarica, segno)."""
        hub = self.hass.data.get(DOMAIN, {}).get(HUB_DATA_KEY, {})
        return (
            hub.get("battery_bidir"),
            hub.get("battery_discharge"),
            hub.get("battery_sign") or "positive",
        )

    def _battery_discharge_w(self) -> float:
        """Potenza erogata dalla batteria (scarica), in W (>=0). 0 se non configurata."""
        bidir, disch, sign = self._battery_entities()
        if bidir:
            v = self._get_float(bidir)
            if v is None:
                return 0.0
            if sign == "negative":
                v = -v
            return max(0.0, v)
        if disch:
            v = self._get_float(disch)
            return max(0.0, v) if v is not None else 0.0
        return 0.0

    def _fractions(self) -> tuple[float, float]:
        """Quote del consumo coperte da FV e da batteria (0..1 ciascuna)."""
        prod_e, exp_e, imp_e = self._pv_entities()
        if not imp_e:
            # Senza il prelievo da rete non è possibile ripartire: tutto da rete.
            return 0.0, 0.0
        imp = self._get_float(imp_e) or 0.0
        autoconsumo = 0.0
        if prod_e:
            prod = self._get_float(prod_e) or 0.0
            exp = self._get_float(exp_e) or 0.0
            autoconsumo = max(0.0, prod - exp)
        batt = self._battery_discharge_w()
        totale = autoconsumo + batt + imp
        if totale <= 0:
            return 0.0, 0.0
        f_ftv = autoconsumo / totale
        f_batt = batt / totale
        s = f_ftv + f_batt
        if s > 1.0:  # sicurezza numerica
            f_ftv, f_batt = f_ftv / s, f_batt / s
        return f_ftv, f_batt

    # ------------------------------------------------------------- aggiornamento

    @callback
    def _handle_power_event(self, event: Event) -> None:
        self.hass.async_create_task(self._async_update())

    @callback
    def _handle_switch_event(self, event: Event) -> None:
        # Lo switch reale è cambiato: aggiorna subito le entità (presa sulla card)
        self.async_set_updated_data({})

    @callback
    def _handle_tick(self, now: datetime) -> None:
        self.hass.async_create_task(self._async_update())

    async def _async_update(self) -> None:
        """Integra l'energia e valuta lo stato del ciclo."""
        now = dt_util.utcnow()
        power = self._get_float(self._power_sensor)

        # Sensore non disponibile: congela, non accumulare un dt gigante al ritorno
        if power is None:
            self._last_time = now
            return

        # Integrazione (left Riemann, come method:left del package)
        if self._last_time is not None:
            dt_s = (now - self._last_time).total_seconds()
            if dt_s > 0:
                wh = self._last_power * dt_s / 3600.0
                kwh = wh / 1000.0
                kwh_ftv = kwh * self._last_frac_ftv
                kwh_batt = kwh * self._last_frac_batt
                kwh_grid = max(0.0, kwh - kwh_ftv - kwh_batt)
                self.energy_total_kwh += kwh
                self.energy_total_ftv_kwh += kwh_ftv
                self.energy_total_batt_kwh += kwh_batt
                self.energy_total_grid_kwh += kwh_grid
                if self.running:
                    self.runtime_total_h += dt_s / 3600.0
                if self.cycle_active:
                    self.energy_cycle_kwh += kwh
                    self.energy_cycle_ftv_kwh += kwh_ftv
                    self.energy_cycle_batt_kwh += kwh_batt
                    self.energy_cycle_grid_kwh += kwh_grid

        # Memorizza per il prossimo intervallo
        self._last_power = power
        self._last_frac_ftv, self._last_frac_batt = self._fractions()
        self._last_time = now

        # Valutazione soglia + gestione ritardi
        self._evaluate_threshold(power)

        # Salvataggio periodico dei totali
        if self._last_save is None or (now - self._last_save).total_seconds() >= _SAVE_INTERVAL_S:
            await self._async_save()

        self.async_set_updated_data({})

    @callback
    def _evaluate_threshold(self, power: float) -> None:
        """Replica delay_on/delay_off del binary_sensor del package."""
        above = power > self.threshold_w

        if above and not self._above:
            # Potenza salita sopra soglia
            self._above = True
            self._cancel_off()
            if not self.running and self._pending_on is None:
                self._pending_on = async_call_later(
                    self.hass, self.delay_on_s, self._turn_on
                )
        elif not above and self._above:
            # Potenza scesa sotto soglia
            self._above = False
            self._cancel_on()
            if self.running and self._pending_off is None:
                self._pending_off = async_call_later(
                    self.hass, self.delay_off_min * 60, self._turn_off
                )

    @callback
    def _turn_on(self, _now=None) -> None:
        self._pending_on = None
        if self.running:
            return
        self.running = True
        if self.cycle_active:
            # Ciclo ripreso dopo un riavvio: continua a contare, non azzerare
            self.async_set_updated_data({})
        else:
            self._start_cycle()

    @callback
    def _turn_off(self, _now=None) -> None:
        self._pending_off = None
        if not self.running:
            return
        self.running = False
        self.hass.async_create_task(self._end_cycle())

    @callback
    def _start_cycle(self) -> None:
        self.cycle_active = True
        self._cycle_start = dt_util.utcnow()
        self.energy_cycle_kwh = 0.0
        self.energy_cycle_ftv_kwh = 0.0
        self.energy_cycle_batt_kwh = 0.0
        self.energy_cycle_grid_kwh = 0.0
        self.async_set_updated_data({})

    async def _end_cycle(self) -> None:
        self.cycle_active = False
        now = dt_util.utcnow()
        if self._cycle_start:
            self.last_cycle_duration_min = round(
                (now - self._cycle_start).total_seconds() / 60.0, 1
            )
        self.cycles_total += 1
        self.last_cycle_end = now
        self.last_cycle_energy_kwh = round(self.energy_cycle_kwh, 3)
        self.last_cycle_ftv_kwh = round(self.energy_cycle_ftv_kwh, 3)
        self.last_cycle_batt_kwh = round(self.energy_cycle_batt_kwh, 3)
        self.last_cycle_grid_kwh = round(self.energy_cycle_grid_kwh, 3)
        self.last_cycle_cost = round(self.energy_cycle_grid_kwh * self.cost_per_kwh, 2)

        clean_pct = 0.0
        if self.energy_cycle_kwh > 0:
            clean_pct = round(
                (self.energy_cycle_ftv_kwh + self.energy_cycle_batt_kwh)
                / self.energy_cycle_kwh * 100,
                1,
            )

        # Fascia oraria notifiche (vale per google/alexa, come nel package)
        now_t = dt_util.now().time()
        s, e = self._notif_start, self._notif_end
        in_fascia = (s <= now_t <= e) if s <= e else (now_t >= s or now_t <= e)

        # Evento per notifiche (blueprint/automazione dell'utente)
        self.hass.bus.async_fire(
            EVENT_CYCLE_FINISHED,
            {
                "entry_id": self._entry.entry_id,
                "name": self.appliance_name,
                "frase_vocale": self.voice_phrase,
                "duration_min": self.last_cycle_duration_min,
                "energy_kwh": self.last_cycle_energy_kwh,
                "ftv_kwh": self.last_cycle_ftv_kwh,
                "batt_kwh": self.last_cycle_batt_kwh,
                "grid_kwh": self.last_cycle_grid_kwh,
                "clean_pct": clean_pct,
                "cost": self.last_cycle_cost,
                "has_pv": self.has_pv,
                "has_batt": self.has_battery,
                "notifica_push": self.pref_push,
                "notifica_google": self.pref_google and in_fascia,
                "notifica_alexa": self.pref_alexa and in_fascia,
                "notifica_ha": self.pref_ha,
            },
        )
        await self._async_save()
        self.async_set_updated_data({})

    # ------------------------------------------------------------- statistiche

    def _current(self, metric: str) -> float:
        """Valore lifetime (monotòno) di una metrica."""
        return {
            "energy": self.energy_total_kwh,
            "energy_ftv": self.energy_total_ftv_kwh,
            "energy_batt": self.energy_total_batt_kwh,
            "energy_grid": self.energy_total_grid_kwh,
            "cycles": float(self.cycles_total),
            "runtime": self.runtime_total_h,
        }[metric]

    def period_value(self, period: str, metric: str) -> float:
        """Valore della metrica nel periodo corrente (oggi/mese/anno)."""
        return max(0.0, self._current(metric) - self._baseline[period][metric])

    def period_last(self, period: str, metric: str) -> float:
        """Valore della metrica nel periodo precedente (ieri/mese scorso/anno scorso)."""
        return self._last_period[period][metric]

    def period_clean_pct(self, period: str, last: bool = False) -> float:
        """Percentuale di energia pulita (FV + batteria) nel periodo."""
        if last:
            tot = self.period_last(period, "energy")
            pulito = self.period_last(period, "energy_ftv") + self.period_last(
                period, "energy_batt"
            )
        else:
            tot = self.period_value(period, "energy")
            pulito = self.period_value(period, "energy_ftv") + self.period_value(
                period, "energy_batt"
            )
        return round(pulito / tot * 100, 1) if tot > 0 else 0.0

    def period_cost(self, period: str, last: bool = False) -> float:
        """Costo (solo energia da rete) nel periodo."""
        grid = self.period_last(period, "energy_grid") if last else self.period_value(
            period, "energy_grid"
        )
        return round(grid * self.cost_per_kwh, 2)

    def week_summary(self) -> tuple[dict[str, dict[str, float]], float]:
        """Riepilogo degli ultimi 7 giorni per giorno della settimana."""
        out: dict[str, dict[str, float]] = {}
        tot_kwh = 0.0
        for idx, name in enumerate(_WEEKDAYS):
            d = self._week.get(idx, {})
            out[name] = {
                "kwh": round(d.get("kwh", 0.0), 3),
                "costo": round(d.get("costo", 0.0), 2),
                "cicli": int(d.get("cicli", 0)),
                "tempo_h": round(d.get("tempo_h", 0.0), 2),
            }
            tot_kwh += d.get("kwh", 0.0)
        return out, round(tot_kwh, 3)

    @callback
    def _handle_midnight(self, now: datetime) -> None:
        """Alla mezzanotte locale: salva il giorno concluso e resetta i periodi."""
        local = dt_util.as_local(now)
        # Il giorno appena concluso è "ieri"
        yesterday_wd = (local - timedelta(days=1)).weekday()
        self._week[yesterday_wd] = {
            "kwh": self.period_value("day", "energy"),
            "costo": self.period_value("day", "energy_grid") * self.cost_per_kwh,
            "cicli": self.period_value("day", "cycles"),
            "tempo_h": self.period_value("day", "runtime"),
        }
        # Reset giorno (sempre), mese (il 1°), anno (1° gennaio)
        self._roll("day")
        if local.day == 1:
            self._roll("month")
        if local.day == 1 and local.month == 1:
            self._roll("year")
        self.hass.async_create_task(self._async_save())
        self.async_set_updated_data({})

    @callback
    def _roll(self, period: str) -> None:
        """Chiude un periodo: salva il consuntivo e azzera la baseline."""
        for metric in METRICS:
            self._last_period[period][metric] = max(
                0.0, self._current(metric) - self._baseline[period][metric]
            )
            self._baseline[period][metric] = self._current(metric)

    # ------------------------------------------------------------- presa + off

    @property
    def off_time(self) -> dt_time | None:
        return self._off_time

    @property
    def has_switch(self) -> bool:
        return self._switch is not None

    @property
    def has_pv(self) -> bool:
        """True se i sensori FV (produzione + prelievo) permettono lo split FV."""
        prod_e, _exp_e, imp_e = self._pv_entities()
        return bool(prod_e and imp_e)

    @property
    def has_battery(self) -> bool:
        """True se c'è una batteria e il prelievo rete per ripartire il consumo."""
        _prod_e, _exp_e, imp_e = self._pv_entities()
        bidir, disch, _sign = self._battery_entities()
        return bool((bidir or disch) and imp_e)

    @property
    def plug_is_on(self) -> bool:
        if not self._switch:
            return False
        st = self.hass.states.get(self._switch)
        return st is not None and st.state == "on"

    async def async_turn_plug(self, turn_on: bool) -> None:
        """Accende/spegne la presa reale configurata."""
        if not self._switch:
            return
        domain = self._switch.split(".")[0]
        service = "turn_on" if turn_on else "turn_off"
        await self.hass.services.async_call(
            domain, service, {"entity_id": self._switch}, blocking=False
        )

    @callback
    def set_off_time(self, value: dt_time | None) -> None:
        """Imposta l'orario di spegnimento automatico."""
        self._off_time = value
        self._register_off_trigger()
        self.hass.async_create_task(self._async_save())
        self.async_set_updated_data({})

    @callback
    def _register_off_trigger(self) -> None:
        """(Ri)registra il trigger orario per lo spegnimento automatico."""
        if self._unsub_off is not None:
            self._unsub_off()
            self._unsub_off = None
        if self._off_time is not None:
            self._unsub_off = async_track_time_change(
                self.hass,
                self._handle_auto_off,
                hour=self._off_time.hour,
                minute=self._off_time.minute,
                second=0,
            )

    @callback
    def _handle_auto_off(self, now: datetime) -> None:
        if self.auto_off_enabled and self.plug_is_on:
            self.hass.async_create_task(self.async_turn_plug(False))

    # ------------------------------------------------------------- preferenze

    @property
    def notif_start(self) -> dt_time:
        return self._notif_start

    @property
    def notif_end(self) -> dt_time:
        return self._notif_end

    @callback
    def set_flag(self, name: str, value: bool) -> None:
        """Imposta una preferenza booleana (auto_off_enabled, pref_push/google/alexa)."""
        setattr(self, name, bool(value))
        self.hass.async_create_task(self._async_save())
        self.async_set_updated_data({})

    @callback
    def set_notif_time(self, which: str, value: dt_time) -> None:
        """Imposta l'inizio/fine della fascia oraria notifiche."""
        setattr(self, "_notif_start" if which == "start" else "_notif_end", value)
        self.hass.async_create_task(self._async_save())
        self.async_set_updated_data({})

    # ------------------------------------------------------------- reset

    async def async_reset_all(self, scope: str = "tutto") -> None:
        """Azzera i contatori secondo lo scope: tutto/totali/statistiche/ciclo."""
        if scope in ("tutto", "totali"):
            self.energy_total_kwh = 0.0
            self.energy_total_ftv_kwh = 0.0
            self.energy_total_batt_kwh = 0.0
            self.energy_total_grid_kwh = 0.0
            self.cycles_total = 0
            self.runtime_total_h = 0.0
        if scope in ("tutto", "totali", "statistiche"):
            for period in PERIODS:
                for metric in METRICS:
                    self._baseline[period][metric] = self._current(metric)
                    self._last_period[period][metric] = 0.0
            self._week = {}
        if scope in ("tutto", "ciclo"):
            self.energy_cycle_kwh = 0.0
            self.energy_cycle_ftv_kwh = 0.0
            self.energy_cycle_batt_kwh = 0.0
            self.energy_cycle_grid_kwh = 0.0
            if self.cycle_active:
                self._cycle_start = dt_util.utcnow()
        if scope == "tutto":
            self.last_cycle_end = None
            self.last_cycle_duration_min = 0.0
            self.last_cycle_energy_kwh = 0.0
            self.last_cycle_ftv_kwh = 0.0
            self.last_cycle_batt_kwh = 0.0
            self.last_cycle_grid_kwh = 0.0
            self.last_cycle_cost = 0.0
        self.last_reset = dt_util.utcnow()
        await self._async_save()
        self.async_set_updated_data({})

    # ------------------------------------------------------------- number runtime

    @callback
    def set_threshold(self, value: float) -> None:
        self.threshold_w = float(value)
        self.hass.async_create_task(self._async_save())
        self.async_set_updated_data({})

    @callback
    def set_delay_on(self, value: float) -> None:
        self.delay_on_s = int(value)
        self.hass.async_create_task(self._async_save())

    @callback
    def set_delay_off(self, value: float) -> None:
        self.delay_off_min = int(value)
        self.hass.async_create_task(self._async_save())

    # ------------------------------------------------------------- proprietà calc

    @property
    def cost_per_kwh(self) -> float:
        """Costo €/kWh: override locale, poi scheda Costo, poi impianto, poi default."""
        if self._cost_override is not None:
            return self._cost_override
        data = self.hass.data.get(DOMAIN, {})
        cost = data.get(COST_DATA_KEY, {}).get("cost_per_kwh")
        if cost is None:
            cost = data.get(HUB_DATA_KEY, {}).get("cost_per_kwh")
        return float(cost) if cost is not None else DEFAULT_COST_PER_KWH

    @property
    def power_w(self) -> float:
        return round(self._last_power, 1)

    @property
    def power_ftv_w(self) -> float:
        return round(self._last_power * self._last_frac_ftv, 1)

    @property
    def power_batt_w(self) -> float:
        return round(self._last_power * self._last_frac_batt, 1)

    @property
    def power_grid_w(self) -> float:
        frac = self._last_frac_ftv + self._last_frac_batt
        return round(max(0.0, self._last_power - self._last_power * frac), 1)

    @property
    def clean_pct(self) -> float:
        return round((self._last_frac_ftv + self._last_frac_batt) * 100, 1)

    @property
    def clean_pct_cycle(self) -> float:
        if self.energy_cycle_kwh <= 0:
            return 0.0
        return round(
            (self.energy_cycle_ftv_kwh + self.energy_cycle_batt_kwh)
            / self.energy_cycle_kwh * 100,
            1,
        )

    @property
    def cycle_duration_min(self) -> float:
        if self.cycle_active and self._cycle_start:
            return round((dt_util.utcnow() - self._cycle_start).total_seconds() / 60.0, 1)
        return self.last_cycle_duration_min

    @property
    def cost_cycle(self) -> float:
        return round(self.energy_cycle_grid_kwh * self.cost_per_kwh, 2)

    # ------------------------------------------------------------- persistenza

    async def _async_save(self) -> None:
        self._last_save = dt_util.utcnow()
        await self._store.async_save(
            {
                "energy_total_kwh": self.energy_total_kwh,
                "energy_total_ftv_kwh": self.energy_total_ftv_kwh,
                "energy_total_batt_kwh": self.energy_total_batt_kwh,
                "energy_total_grid_kwh": self.energy_total_grid_kwh,
                "cycles_total": self.cycles_total,
                "runtime_total_h": self.runtime_total_h,
                "baseline": self._baseline,
                "last_period": self._last_period,
                "week": {str(k): v for k, v in self._week.items()},
                "off_time": self._off_time.isoformat() if self._off_time else None,
                "auto_off_enabled": self.auto_off_enabled,
                "pref_push": self.pref_push,
                "pref_google": self.pref_google,
                "pref_alexa": self.pref_alexa,
                "pref_ha": self.pref_ha,
                "last_reset": self.last_reset.isoformat() if self.last_reset else None,
                "notif_start": self._notif_start.isoformat(),
                "notif_end": self._notif_end.isoformat(),
                "last_cycle_end": self.last_cycle_end.isoformat()
                if self.last_cycle_end
                else None,
                "last_cycle_duration_min": self.last_cycle_duration_min,
                "last_cycle_energy_kwh": self.last_cycle_energy_kwh,
                "last_cycle_ftv_kwh": self.last_cycle_ftv_kwh,
                "last_cycle_batt_kwh": self.last_cycle_batt_kwh,
                "last_cycle_grid_kwh": self.last_cycle_grid_kwh,
                "last_cycle_cost": self.last_cycle_cost,
                "energy_cycle_kwh": self.energy_cycle_kwh,
                "energy_cycle_ftv_kwh": self.energy_cycle_ftv_kwh,
                "energy_cycle_batt_kwh": self.energy_cycle_batt_kwh,
                "energy_cycle_grid_kwh": self.energy_cycle_grid_kwh,
                "cycle_active": self.cycle_active,
                "cycle_start": self._cycle_start.isoformat() if self._cycle_start else None,
                "threshold_w": self.threshold_w,
                "delay_on_s": self.delay_on_s,
                "delay_off_min": self.delay_off_min,
            }
        )

    # ------------------------------------------------------------- util interni

    @callback
    def _cancel_on(self) -> None:
        if self._pending_on is not None:
            self._pending_on()
            self._pending_on = None

    @callback
    def _cancel_off(self) -> None:
        if self._pending_off is not None:
            self._pending_off()
            self._pending_off = None

    @callback
    def _cancel_pending(self) -> None:
        self._cancel_on()
        self._cancel_off()

    async def _async_update_data(self) -> dict[str, Any]:
        """Non usato (event-driven): ritorna lo stato corrente."""
        return self.data or {}
