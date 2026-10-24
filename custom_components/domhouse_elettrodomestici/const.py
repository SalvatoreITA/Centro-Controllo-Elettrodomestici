"""Costanti per l'integrazione DomHouse Centro Controllo Elettrodomestici."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "domhouse_elettrodomestici"

# Piattaforme esposte
PLATFORMS: list[str] = ["binary_sensor", "sensor", "number", "switch", "time"]

# Servizio di reset contatori
SERVICE_RESET = "reset"
RESET_SCOPES = ("tutto", "totali", "statistiche", "ciclo")

# Tipo di config entry
CONF_ENTRY_TYPE = "entry_type"
ENTRY_TYPE_HUB = "hub"
ENTRY_TYPE_APPLIANCE = "appliance"
ENTRY_TYPE_COST = "cost"

# Chiavi in hass.data per i dati condivisi
HUB_DATA_KEY = "hub"
COST_DATA_KEY = "cost"

# ---- Chiavi di configurazione (config entry data/options) ----
CONF_NAME = "name"
CONF_POWER_SENSOR = "power_sensor"          # sensore potenza presa smart (W)
CONF_SWITCH = "switch"                        # switch presa (opzionale)
CONF_PV_PRODUCTION = "pv_production_sensor"   # produzione fotovoltaico (W)
CONF_PV_EXPORT = "pv_export_sensor"           # energia immessa in rete (W)
CONF_PV_IMPORT = "pv_import_sensor"           # energia prelevata da rete (W)
CONF_COST_PER_KWH = "cost_per_kwh"            # costo €/kWh

# Batteria di accumulo (opzionale, a livello impianto)
CONF_BATTERY_BIDIR = "battery_bidir"          # sensore potenza batteria bidirezionale (W)
CONF_BATTERY_DISCHARGE = "battery_discharge"  # sensore potenza di scarica batteria (W)
CONF_BATTERY_SIGN = "battery_sign"            # nel bidirezionale, quale segno = scarica

# Soglia e ritardi: valori iniziali (poi regolabili dalle entità number)
CONF_THRESHOLD_W = "threshold_w"
CONF_DELAY_ON_S = "delay_on_s"
CONF_DELAY_OFF_MIN = "delay_off_min"
CONF_VOICE_PHRASE = "voice_phrase"           # frase annuncio vocale fine ciclo (Google/Alexa)

# ---- Default ----
DEFAULT_THRESHOLD_W = 10.0      # sopra questa potenza l'elettrodomestico è "in funzione"
DEFAULT_DELAY_ON_S = 30         # secondi sopra soglia prima di dichiarare ON (anti falso avvio)
DEFAULT_DELAY_OFF_MIN = 3       # minuti sotto soglia prima di dichiarare OFF (pause ciclo)
DEFAULT_COST_PER_KWH = 0.25
DEFAULT_VOICE_PHRASE = "Ciclo terminato"   # frase di default per l'annuncio vocale
DEFAULT_BATTERY_SIGN = "positive"          # valore positivo = scarica (convenzione di default)

# Limiti entità number
MIN_THRESHOLD_W = 0.0
MAX_THRESHOLD_W = 5000.0
MIN_DELAY_ON_S = 0
MAX_DELAY_ON_S = 600
MIN_DELAY_OFF_MIN = 0
MAX_DELAY_OFF_MIN = 60

# Intervallo di integrazione energia (tick interno)
SCAN_INTERVAL = timedelta(seconds=15)

# Storage per la persistenza dello stato del coordinator
STORAGE_VERSION = 1
STORAGE_KEY = DOMAIN  # la chiave effettiva è per-entry: {DOMAIN}_{entry_id}

# Evento emesso a fine ciclo (per notifiche via blueprint/automazione utente)
EVENT_CYCLE_FINISHED = f"{DOMAIN}_ciclo_finito"
