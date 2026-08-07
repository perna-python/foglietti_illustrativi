# 🔎 Ricerca Farmaci AIFA

Applicazione desktop per la ricerca dei farmaci nella banca dati ufficiale **AIFA (Agenzia Italiana del Farmaco)**.

Permette di cercare medicinali, visualizzare le informazioni autorizzative, consultare confezioni e prescrizioni, scaricare il **Foglietto Illustrativo (FI)** e il **Riassunto delle Caratteristiche del Prodotto (RCP)**.

L'applicazione è sviluppata in **Python + Flet** con una moderna interfaccia desktop multipiattaforma.

---

## ✨ Funzionalità principali

### 🔍 Ricerca farmaci

- Ricerca tramite:
  - nome commerciale del farmaco
  - principio attivo
  - codice AIC
- Suggerimenti e correzione automatica della ricerca tramite API AIFA
- Ricerca asincrona senza bloccare l'interfaccia
- Sistema di debounce per evitare chiamate API inutili
- Cache temporanea delle ricerche

---

### 📋 Scheda farmaco

Per ogni farmaco vengono visualizzate:

- Denominazione
- Forma farmaceutica
- Principi attivi
- Via di somministrazione
- Codice ATC
- Informazioni sulle confezioni:
  - AIC
  - descrizione
  - classe di rimborsabilità
  - stato amministrativo
  - prescrizione

---

### ⚠️ Informazioni importanti

Evidenzia automaticamente:

- Farmaci carenti
- Farmaci dopanti
- Farmaci che influenzano la guida
- Interazioni con:
  - alcool
  - potassio

---

### 📄 Download documenti AIFA

Possibilità di scaricare:

- 📘 Foglietto Illustrativo (FI)
- 📙 Riassunto delle Caratteristiche del Prodotto (RCP)

I documenti vengono scaricati direttamente dai servizi AIFA.

---

### ⭐ Preferiti

Gestione dei farmaci preferiti:

- aggiunta/rimozione rapida
- salvataggio locale
- accesso immediato senza nuova ricerca

---

### 🕘 Cronologia

Memorizza gli ultimi farmaci consultati:

- massimo 50 elementi
- ordinamento dal più recente
- accesso rapido alle schede già aperte

---

### 🎨 Interfaccia grafica

Realizzata con **Flet 0.86.5**.

Caratteristiche:

- Layout moderno a due colonne
- Tema chiaro/scuro
- Componenti riutilizzabili
- Card informative
- Badge colorati
- Accordion per sezioni dettagliate
- Animazioni leggere
- Supporto desktop multipiattaforma

---

## 🖥️ Screenshot

*(Inserire qui eventuali immagini dell'applicazione)*

---

# 🛠️ Tecnologie utilizzate

## Linguaggio

- Python >= 3.12

## Framework UI

- Flet 0.86.5

## Client HTTP

- httpx

## API

- AIFA Banca Dati Farmaci

Endpoint utilizzato:

```
https://api.aifa.gov.it/aifa-bdf-eif-be/1.0.0
```

---

# 📦 Installazione

## Clonazione repository

```bash
git clone https://github.com/perna-python/foglietti_illustrativi.git

cd foglietti_illustrativi
```

---

## Creazione ambiente virtuale

### macOS / Linux

```bash
python3 -m venv .venv

source .venv/bin/activate
```

### Windows

```powershell
python -m venv .venv

.venv\Scripts\activate
```

---

## Installazione dipendenze

```bash
pip install -r requirements.txt
```

Oppure:

```bash
pip install flet==0.86.5 httpx
```

---

# ▶️ Avvio applicazione

Eseguire:

```bash
python ricerca_farmaci.py
```

L'applicazione verrà aperta come finestra desktop.

---

# 📁 Struttura progetto

```
foglietti_illustrativi/
│
├── ricerca_farmaci.py
├── requirements.txt
├── README.md
│
└── .venv/
```

---

# ⚙️ Architettura

L'applicazione è organizzata in componenti separati:

## API Layer

`AIFAService`

Gestisce:

- chiamate HTTP asincrone
- ricerca farmaci
- download documenti

---

## Data Model

Modelli tramite `dataclass`:

- `RisultatoFarmaco`
- `Confezione`
- `APIConfig`

Gestiscono il parsing sicuro delle risposte AIFA.

---

## Persistence Layer

`LocalStore`

Gestisce:

- preferiti
- cronologia
- modalità tema

Utilizza lo storage locale Flet quando disponibile.

---

## UI Components

Componenti riutilizzabili:

- Card farmaco
- Badge
- Accordion
- InfoTile
- Download panel
- Empty state

---

# 🔐 Privacy

L'applicazione:

- non raccoglie dati personali
- non utilizza database esterni
- non salva informazioni sanitarie dell'utente
- comunica esclusivamente con i servizi pubblici AIFA

---

# 🚀 Possibili sviluppi futuri

Possibili miglioramenti:

- [ ] Ricerca offline completa tramite database locale AIFA
- [ ] Esportazione PDF scheda farmaco
- [ ] Stampa rapida informazioni
- [ ] Confronto tra due o più farmaci
- [ ] Sincronizzazione preferiti tramite cloud
- [ ] Cronologia avanzata con ricerca
- [ ] Packaging installer:
  - macOS `.app`
  - Windows `.exe`

---

# 📄 Licenza

Questo progetto è distribuito con licenza MIT.

---

# 👨‍💻 Autore

Sviluppato con:

- Python
- Flet
- API AIFA