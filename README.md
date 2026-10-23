# Centro Controllo Elettrodomestici (Custom Component)

Integrazione custom per **Home Assistant** che monitora un elettrodomestico tramite una **presa smart**: deduce lo stato (in funzione / fermo) dal consumo, misura durata, energia e costo di ogni ciclo e — se hai un impianto **fotovoltaico** e/o una **batteria** di accumulo — calcola quanta parte del consumo è coperta da energia pulita.

È la versione "duplicabile" del package YAML DomHouse: ogni elettrodomestico (lavatrice, forno, asciugatrice, lavastoviglie…) si aggiunge dalla UI, senza copiare file e rinominare entità a mano.

- **Versione:** 0.9.1
- **Dominio:** `domhouse_elettrodomestici`
- **Config flow:** sì (tutto dalla UI, nessun YAML)
- **Dipendenze:** nessuna (funziona da solo; le notifiche usano un blueprint incluso)
- 🌐 [www.domhouse.it](https://domhouse.it/centro-controllo-elettrodomestici-in-home-assistant/)

---

## Indice

- [Come funziona](#come-funziona)
- [Installazione](#installazione)
- [Configurazione](#configurazione)
- [Modello di calcolo (FV / batteria / rete)](#modello-di-calcolo-fv--batteria--rete)
- [Entità create](#entità-create)
- [Servizio di reset](#servizio-di-reset)
- [Statistiche periodiche](#statistiche-periodiche)
- [Notifiche fine ciclo](#notifiche-fine-ciclo)
- [Evento `..._ciclo_finito`](#evento-domhouse_elettrodomestici_ciclo_finito)
- [Persistenza](#persistenza)
- [Note](#note)
- [Changelog](#changelog)

---

## Come funziona

1. Legge la **potenza** della presa smart (in W).
2. Confronta con la **soglia di lavoro**: sopra soglia per *N* secondi (ritardo accensione) → **in funzione**; sotto soglia per *M* minuti (ritardo spegnimento) → **fermo**. I ritardi evitano falsi avvii e falsi stop nelle pause del ciclo (centrifuga, risciacqui, ecc.).
3. Quando parte un ciclo, integra l'**energia** (metodo di Riemann) e, se configurate, ne ripartisce il consumo tra **fotovoltaico**, **batteria** e **rete** in proporzione a come è alimentata la casa in quell'istante.
4. A fine ciclo salva durata, energia (per fonte), costo e % di energia pulita, aggiorna i contatori di periodo ed emette un **evento** per le notifiche.

Tutto è **event-driven** (reagisce ai cambi del sensore di potenza) con un tick di sicurezza ogni 15 s.

---

## Installazione

### Via HACS (consigliato)
1. HACS → menu ⋮ in alto a destra → **Repository personalizzate**.
2. Aggiungi l'URL del repository, categoria **Integration**.
3. Cerca *DomHouse – Centro Controllo Elettrodomestici* e installa.
4. **Riavvia** Home Assistant.
5. **Impostazioni → Dispositivi e servizi → Aggiungi integrazione** → cerca *DomHouse*.

### Manuale
Copia la cartella `custom_components/domhouse_elettrodomestici` in `config/custom_components/` e riavvia HA.

---

## Configurazione

Aggiungendo l'integrazione scegli **cosa creare** (menu a tre voci). Puoi aggiungerla più volte.

### 1. Impianto fotovoltaico (una volta sola, opzionale)
Sensori FV e batteria **condivisi** da tutti gli elettrodomestici.

| Campo | Note |
|-------|------|
| Produzione fotovoltaico | Potenza prodotta dal FV (W) — opzionale |
| Energia immessa in rete | Potenza immessa (W) — opzionale |
| Energia prelevata da rete | Potenza prelevata (W) — **serve per lo split** FV/batteria |
| Potenza batteria (bidirezionale) | Opzionale: un solo sensore con segno (W) |
| Potenza scarica batteria | Opzionale: sensore di sola scarica (W) |
| Bidirezionale: segno scarica | Positivo o negativo = scarica (default: positivo) |

Tutti i campi sono **opzionali**. La batteria si può fornire in tre modi: un sensore **bidirezionale** (il segno distingue carica/scarica), due sensori separati (usi il campo *scarica*), o solo il sensore di **scarica**.

### 2. Costo energia (una volta sola, opzionale)
Una scheda a sé con il solo prezzo **€/kWh**, condiviso da tutti gli elettrodomestici. È il posto per il costo **anche senza** fotovoltaico: non serve creare un impianto FV vuoto solo per il prezzo. Se non la crei vale il **default 0,25 €/kWh**.

**Priorità del costo:** costo impostato sul singolo elettrodomestico → scheda *Costo energia* → vecchio impianto FV (retrocompatibilità) → default 0,25.

### 3. Elettrodomestico (uno per apparecchio)

| Campo | Obbligatorio | Note |
|-------|:---:|------|
| Nome | ✅ | Es. "Lavatrice" |
| Sensore potenza | ✅ | La potenza della presa smart in **W** |
| Interruttore presa | — | Per accendere/spegnere la presa |
| Sensori FV (produzione/immessa/prelevata) | — | Solo come **override** dell'impianto: lasciali vuoti per usare quelli condivisi |
| Frase annuncio vocale (fine ciclo) | — | Es. `Lavaggio terminato` (default: `Ciclo terminato`) — vedi [notifiche](#notifiche-fine-ciclo) |

Soglia di lavoro e ritardi di accensione/spegnimento partono da valori di default e si regolano **a runtime** dalle entità `number` (vedi sotto).

---

## Modello di calcolo (FV / batteria / rete)

Lo split richiede almeno il sensore **prelievo da rete**. Il consumo di casa in ogni istante è:

```
consumo_casa = autoconsumo_FV + scarica_batteria + prelievo_rete
autoconsumo_FV = max(0, produzione − immissione)
```

Il consumo dell'elettrodomestico viene attribuito alle fonti **nelle stesse proporzioni** della casa. L'**energia pulita** è la somma di **FV + batteria**; il **costo** si calcola **solo sull'energia prelevata dalla rete** (FV e batteria sono a costo zero).

- **Senza fotovoltaico** → le voci FV e "Energia pulita" non vengono create; senza nemmeno la batteria, tutto il consumo è "da rete".
- **Senza prelievo da rete configurato** → nessuno split possibile, tutto considerato "da rete".

---

## Entità create

Gli `entity_id` seguono lo schema `<dominio>.<nome_slug>_<entità>`. Esempio con device "Lavatrice":

### Stato e potenze
| Entità | Esempio entity_id | Note |
|--------|-------------------|------|
| In funzione | `binary_sensor.lavatrice_in_funzione` | soglia + ritardi |
| Potenza | `sensor.lavatrice_potenza` | W |
| Potenza da fotovoltaico | `sensor.lavatrice_potenza_da_fotovoltaico` | solo con FV |
| Potenza da batteria | `sensor.lavatrice_potenza_da_batteria` | solo con batteria |
| Potenza da rete | `sensor.lavatrice_potenza_da_rete` | W |

### Energia pulita
| Entità | entity_id | Note |
|--------|-----------|------|
| Energia pulita | `sensor.lavatrice_energia_pulita` | % istantanea (FV+batteria), solo con FV o batteria |
| Energia pulita ciclo | `sensor.lavatrice_energia_pulita_ciclo` | % sull'intero ciclo |

### Energia del ciclo e lifetime
| Entità | entity_id | Note |
|--------|-----------|------|
| Energia ciclo | `sensor.lavatrice_energia_ciclo` | kWh del ciclo corrente/ultimo |
| Energia ciclo da FV / batteria / rete | `..._energia_ciclo_da_fotovoltaico` / `..._da_batteria` / `..._da_rete` | kWh, condizionali |
| Energia totale | `sensor.lavatrice_energia_totale` | kWh lifetime (`total_increasing`) |
| Energia totale da FV / batteria / rete | `..._energia_totale_da_fotovoltaico` / `..._da_batteria` / `..._da_rete` | per il **cruscotto Energia** di HA |

### Ciclo
| Entità | entity_id |
|--------|-----------|
| Durata ciclo | `sensor.lavatrice_durata_ciclo` |
| Costo ciclo | `sensor.lavatrice_costo_ciclo` (€) |
| Cicli totali | `sensor.lavatrice_cicli_totali` |
| Fine / Durata / Costo ultimo ciclo | `..._fine_ultimo_ciclo` / `..._durata_ultimo_ciclo` / `..._costo_ultimo_ciclo` |
| Ultimo reset | `sensor.lavatrice_ultimo_reset` |

### Statistiche di periodo
`sensor.lavatrice_energia_oggi|mese|anno`, `..._costo_oggi|mese|anno`, `..._cicli_oggi|mese|anno`, `..._tempo_oggi|mese|anno`, più `sensor.lavatrice_riepilogo_settimana`.

### Regolazioni a runtime (`number`)
| Entità | entity_id |
|--------|-----------|
| Soglia di lavoro | `number.lavatrice_soglia_di_lavoro` (W) |
| Ritardo accensione | `number.lavatrice_ritardo_accensione` (s) |
| Ritardo spegnimento | `number.lavatrice_ritardo_spegnimento` (min) |

### Controllo e preferenze
| Entità | entity_id | Note |
|--------|-----------|------|
| Presa | `switch.lavatrice_presa` | solo se hai associato un interruttore |
| Spegnimento automatico | `time.lavatrice_spegnimento_automatico` | a quell'ora, se la presa è accesa, viene spenta |
| Abilita spegnimento | `switch.lavatrice_abilita_spegnimento` | abilita/disabilita lo spegnimento a orario |
| Notifica Push / Google / Alexa / HA | `switch.lavatrice_notifica_push` / `_notifica_google` / `_notifica_alexa` / `_notifica_ha` | canali attivi (letti dal blueprint) |
| Notifiche dalle / alle | `time.lavatrice_notifiche_dalle` / `_notifiche_alle` | **fascia oraria solo per Google e Alexa** |

> Le voci **da fotovoltaico** e **Energia pulita** nascono solo con FV configurato; le voci **da batteria** solo con batteria. Chi non ha né l'uno né l'altra vede solo i consumi totali e il costo. Le entità **Presa / Spegnimento automatico** nascono solo se hai associato un interruttore.

---

## Servizio di reset

`domhouse_elettrodomestici.reset` azzera i contatori. Target: l'elettrodomestico. Campo **`azzera`**:

| Valore | Cosa azzera |
|--------|-------------|
| `tutto` | tutti i contatori (default) |
| `totali` | energia / cicli / tempo lifetime (azzera anche i periodi) |
| `statistiche` | oggi / mese / anno + storico 7 giorni |
| `ciclo` | solo il ciclo in corso |

La data dell'ultimo reset finisce nel sensore *Ultimo reset*. Dalla card si fa da **Controllo → Contatori → Esegui** (con conferma).

---

## Statistiche periodiche

- **Energia / Costo / Cicli / Tempo** per **oggi**, **mese**, **anno**. Ogni sensore porta negli attributi il **periodo precedente** (ieri / mese scorso / anno scorso) e, per l'energia, la quota da FV, da batteria, da rete e la % di energia pulita.
- **Riepilogo settimana**: stato = kWh totali degli ultimi 7 giorni; negli attributi, per ogni giorno della settimana, `kwh`, `costo`, `cicli`, `tempo_h`.

I reset di periodo avvengono da soli: a **mezzanotte** (giorno), il **1° del mese** e il **1° gennaio** (anno).

---

## Notifiche fine ciclo

A fine ciclo l'integrazione emette l'evento `domhouse_elettrodomestici_ciclo_finito`. Le notifiche si configurano con il **blueprint incluso** (`blueprints/automation/domhouse_elettrodomestici/notifica_fine_ciclo.yaml`), che non dipende da integrazioni specifiche.

- **Canali:** Push, Google (TTS), Alexa, HA (notifica persistente). Si attivano dagli **interruttori** di ogni elettrodomestico (anche dalla card).
- **Fascia oraria:** vale **solo** per Google e Alexa (gli annunci vocali). Push e HA arrivano sempre.
- **Target:** nel blueprint scegli solo i target — servizio `notify.*` per il push, i media player per Google/Alexa, e il **servizio TTS Google** (default `tts.google_translate_say`, modificabile). Con *Elettrodomestico (filtro)* vuoto, una sola automazione vale per tutti.
- **Frase vocale per device:** poiché il blueprint è unico ma la grammatica cambia, ogni elettrodomestico ha nelle sue **impostazioni** il campo *Frase annuncio vocale*: `Lavaggio terminato`, `Asciugatura terminata`, `Piatti lavati`, ecc. La push non è toccata.

---

## Evento `domhouse_elettrodomestici_ciclo_finito`

Payload (per automazioni tue):

| Campo | Tipo | Significato |
|-------|------|-------------|
| `entry_id` | str | id della config entry |
| `name` | str | nome dell'elettrodomestico |
| `frase_vocale` | str | frase configurata (per il TTS) |
| `duration_min` | float | durata ciclo in minuti |
| `energy_kwh` | float | energia totale del ciclo |
| `ftv_kwh` | float | energia da fotovoltaico |
| `batt_kwh` | float | energia da batteria |
| `grid_kwh` | float | energia da rete |
| `clean_pct` | float | % energia pulita (FV+batteria) |
| `cost` | float | costo del ciclo (€) |
| `has_pv` | bool | FV configurato |
| `has_batt` | bool | batteria configurata |
| `notifica_push` / `notifica_google` / `notifica_alexa` / `notifica_ha` | bool | canali attivi (Google/Alexa già filtrati per fascia oraria) |

---

## Persistenza

Tutto lo stato (totali lifetime, periodi, storico settimana, ultimo ciclo **e ciclo in corso**, preferenze, soglie) è salvato su disco: sopravvive ai riavvii di HA. Se HA si riavvia **durante** un ciclo, il ciclo riprende da dove era senza ripartire da zero.

---

## Note

- Gli `entity_id` sono generati da HA dai nomi in **italiano**: con HA in un'altra lingua gli slug cambiano (e la card va adattata).
- Il cambio di una **opzione** (impianto, costo, elettrodomestico) ricarica automaticamente l'integrazione: le modifiche sono attive subito, senza riavvio.

---

## Changelog

- **0.9.1** — I dati energetici del ciclo (energia/FV/batteria/rete) e lo stato del ciclo sono ora persistiti: non si azzerano più ai riavvii; i cicli in corso riprendono dopo un riavvio.
- **0.9.0** — Scheda **Costo energia** separata dall'impianto FV.
- **0.8.0** — Supporto **batteria** (bidirezionale / scarica) con split a 3 vie; funziona anche **senza FV**; entità condizionali per fonte.
- **0.7.0** — **Frase annuncio vocale** configurabile per elettrodomestico.
- **0.6.0** — Preferenze notifiche (push/google/alexa/ha) e fascia oraria sul device; switch presa event-driven.
- **0.4.0** — Controllo presa, spegnimento automatico a orario, servizio di reset.

---

© DomHouse.it — Salvatore Lentini
