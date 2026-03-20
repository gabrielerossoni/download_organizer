# 📁 Download Organizer

Organizza automaticamente la cartella Download in background usando AI locale (Ollama).
**Safe-first**: se non è sicuro dove mettere un file, va in `Unsorted/` — non cancella mai nulla.

---

## 🚀 Installazione

### Requisiti

- **Python 3.10+** — [python.org](https://python.org)
- **Ollama** — [ollama.com](https://ollama.com)
- Un modello Ollama installato (consigliato: `llama3.1:8b`)

```bash
ollama pull llama3.1:8b
```

### Setup

1. Fai doppio click su **`Setup_DownloadOrganizer.exe`**
2. Compila le cartelle per ogni materia e categoria
3. Clicca **Salva e installa**
4. Il setup installa le dipendenze, crea il config e aggiunge lo script all'avvio automatico

---

## 📂 Struttura progetto

```
Download Organizer/
├── Setup.bat                     ← esegui questo per installare
├── organizer.py                  ← script principale
├── requirements.txt
├── README.md
│
├── config/
│   ├── config.json               ← generato dal setup
│   └── setup_wizard.py           ← wizard CLI alternativo
│
├── memory/
│   └── history.json              ← regole apprese automaticamente
│
├── scripts/
│   ├── vbs/
│   │   ├── start.vbs              ← avvio silenzioso (usato da startup)
│   │   └── stop.vbs               ← ferma l'organizer
│   └── bat/
│       ├── start.bat              ← avvio con terminale (per debug)
│       └── add_to_startup.bat     ← aggiunge manualmente ad avvio automatico
```

---

## ⚙️ Configurazione — `config/config.json`

| Chiave | Descrizione |
|---|---|
| `download_folder` | Cartella da monitorare |
| `unsure_folder_path` | Percorso assoluto per file non classificati |
| `ollama_model` | Modello Ollama da usare |
| `hotkey` | Tasto per scansione manuale |
| `wait_seconds` | Secondi di attesa prima di spostare |
| `dry_run` | `true` = simula senza spostare |
| `school_subjects` | Materie con cartella destinazione |
| `personal_categories` | Categorie personali con cartella |
| `extension_rules` | Fallback per estensione |

---

## 🧠 Come funziona la classificazione

Il sistema usa **4 livelli** in ordine di priorità:

| Livello | Metodo | Esempio |
|---|---|---|
| **0** | Memoria (appresa da te) | Hai spostato `prova.pdf` → ricorda |
| **1** | Match diretto nel nome | `sistemi_reti.pdf` → Sistemi |
| **2** | AI (Ollama/llama3.1) | `foscolo_analisi.pdf` → Italiano |
| **3** | Fallback estensione | `.mp3` → Audio |
| **4** | Unsorted | tutto il resto |

---

## 🌐 Dashboard

Apri la dashboard dal menu tray → **Apri dashboard** oppure vai su:

```text
http://127.0.0.1:5000
```

La dashboard mostra:

- **Log attività** in tempo reale
- **Regole apprese** con toggle on/off e modifica keywords

---

## 🧠 Sistema di memoria

Lo script impara dai tuoi errori:

1. Un file finisce in `Unsorted/`
2. Lo sposti a mano nella cartella giusta
3. Lo script lo nota e salva la regola in `memory/history.json`
4. La prossima volta, file con nome simile vanno direttamente nella cartella giusta

Puoi vedere e modificare le regole dalla dashboard.

---

## 🖥️ Tray icon

L'organizer gira silenzioso con un'icona nella system tray (vicino all'orologio).

Click destro → menu:

- **Scansione manuale** — analizza tutti i file presenti ora nei Download
- **Ferma/Avvia watcher** — pausa temporanea
- **Apri dashboard** — apre il browser su localhost:5000
- **Apri log** — apre PowerShell con log in tempo reale
- **Esci** — ferma tutto

---

## 🛡️ Comportamento sicuro

| Situazione | Cosa fa |
|---|---|
| File ancora in download | Aspetta che smetta di crescere |
| Estensione non riconosciuta | Va in `Unsorted/` |
| File già esistente in destinazione | Aggiunge timestamp, non sovrascrive |
| Duplicato esatto (stesso MD5) | Lo lascia dov'è |
| File nelle sottocartelle | Non lo tocca |
| File temp (`.tmp`, `.crdownload`) | Ignorati |
| `desktop.ini`, `thumbs.db` | Ignorati |

---

## 🔧 Avvio manuale

**Silenzioso (consigliato):**

```batch

scripts\vbs\start.vbs
```

**Con terminale (per debug):**

```batch

scripts\bat\start.bat
```

---

## 📦 Dipendenze

```text
watchdog        — monitora la cartella download
keyboard        — hotkey globale
winotify        — notifiche Windows
ollama          — client AI locale
pymupdf         — legge PDF
python-docx     — legge file Word
flask           — dashboard web
pystray         — tray icon
Pillow          — icona tray
```

Installate automaticamente dal setup o con:

```bash

pip install -r requirements.txt

```
