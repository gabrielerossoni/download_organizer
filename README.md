# 📁 Download Organizer

Organizza automaticamente la cartella Download in background.
**Safe-first**: se non sa dove mettere un file, lo mette in `Da_Smistare/` — non cancella mai nulla.

---

## 🚀 Primo avvio

1. Assicurati di avere **Python 3.8+** installato
2. Fai doppio click su **`avvia.bat`**
   - Installa le dipendenze automaticamente
   - Avvia l'organizer in ascolto

Per avviarlo **ad ogni login** senza finestre: esegui `aggiungi_avvio.bat`

---

## ⚙️ Configurazione — `config.json`

Il file viene creato automaticamente al primo avvio. Modificalo a piacere:

```json
{
  "download_folder": "C:\PROJECT",
  "unsure_folder": "Da_Smistare",
  "hotkey": "ctrl+shift+o",
  "wait_seconds": 3,
  "min_size_bytes": 100,
  "log_file": "organizer.log",
  "dry_run": false,
  "rules": [...]
}
```

| Chiave | Descrizione |
|---|---|
| `download_folder` | Cartella da monitorare |
| `unsure_folder` | Sottocartella per file non riconosciuti |
| `hotkey` | Tasto per scansione manuale |
| `wait_seconds` | Secondi di attesa prima di spostare (evita file in download) |
| `min_size_bytes` | Ignora file più piccoli di X byte |
| `dry_run` | `true` = simula senza spostare nulla (ottimo per testare) |
| `rules` | Lista regole personalizzabili (vedi sotto) |

---

## 📋 Regole personalizzate

Ogni regola ha questa forma:

```json
{
  "name": "Immagini",
  "folder": "Immagini",
  "extensions": [".jpg", ".png", ".gif"]
}
```

- **`name`**: nome descrittivo (solo per i log)
- **`folder`**: nome della sottocartella destinazione (creata automaticamente)
- **`extensions`**: lista estensioni da catturare

Puoi aggiungere, rimuovere o modificare regole liberamente.
L'ordine conta: vince la prima regola che matcha.

---

## 🔑 Hotkey

Di default: **`Ctrl + Shift + O`**

Forza una scansione di tutti i file presenti nei Download in quel momento.
Modificabile nel `config.json` con qualsiasi combinazione supportata da `keyboard`.

---

## 🛡️ Comportamento sicuro

| Situazione | Cosa fa |
|---|---|
| File ancora in download | Aspetta che smetta di crescere |
| File troppo piccolo (placeholder) | Lo ignora |
| Estensione non riconosciuta | Va in `Da_Smistare/` |
| File già esistente nella destinazione | Aggiunge timestamp, non sovrascrive |
| Duplicato esatto (stesso hash MD5) | Lo lascia dov'è |
| File nelle sottocartelle | Non lo tocca |
| File temporanei (`.tmp`, `.part`, `.crdownload`) | Ignorati |

---

## 📄 Log

Tutto viene registrato in `organizer.log` nella stessa cartella dello script.

---

## 🗂️ Struttura cartelle risultante

```
Downloads/
├── Immagini/
├── Video/
├── Audio/
├── Documenti/
├── Archivi/
├── Programmi/
├── Codice/
├── Font/
├── eBook/
├── Modelli3D/
├── Torrent/
└── Da_Smistare/      ← file non riconosciuti
```
