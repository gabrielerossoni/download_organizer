# Download Organizer: scansioni senza processo residente

Windows, Python 3.10+. La modalita predefinita fa una scansione e termina. Fra due scansioni non resta alcun processo Python, watcher, dashboard o servizio IA del progetto. Zero RAM privata del progetto quando il processo e chiuso; Windows conserva i suoi servizi di sistema e puo tenere cache disco reclamabili.

## Uso

L'ambiente `.venv` e il modello semantico sono gia stati installati in questa copia. La configurazione locale conserva le tue cartelle e usa le proposte MiniLM, con `ai_auto_move: false`. Prima di avviare scansioni automatiche controlla le destinazioni con:

```powershell
.venv\Scripts\python.exe organizer.py --dry-run
```

La prima scansione registra i metadati. La seconda, dopo almeno `wait_seconds`, elabora i file rimasti stabili. Non viene lasciato un processo a dormire fra i controlli. In dry run vengono aggiornati solo log e metadati; nessun file viene spostato.

Scansione singola: `scripts/bat/start.bat` oppure `scripts/vbs/start.vbs` senza console. Per una nuova installazione esegui `Setup.bat`: crea l'ambiente, configura cartelle reali e installa il modello se scegli l'IA. Le nuove configurazioni hanno `dry_run: true`.

Per registrare l'esecuzione automatica ogni 5 minuti:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_schedule.ps1
```

Puoi usare `-IntervalMinutes 1` per controllare piu spesso; consuma piu CPU e ricarica il modello piu frequentemente. Il primo controllo parte un minuto dopo la registrazione. Viene usata Utilita di pianificazione di Windows, con l'utente corrente e senza privilegi amministrativi. Niente finestre, istanze sovrapposte o servizio IA. L'installatore rifiuta di sostituire una task omonima appartenente a un'altra cartella. Lo script e pronto; la task non viene registrata automaticamente da Setup.

Per fermare le scansioni automatiche: `scripts/vbs/stop.vbs`, oppure `scripts/stop_schedule.ps1`. Disabilita la task e chiede al processo in corso di fermarsi fra i file, senza terminare tutti i processi Python. Una scansione manuale successiva puo ripartire. Per rimuovere la task usa Utilita di pianificazione, nome `DownloadOrganizer`.

## Come funziona

1. Legge la configurazione e visita Downloads con `os.scandir`, senza accumulare una lista di tutti i file.
2. SQLite conserva nome, dimensione, data di modifica e identita del file fra le esecuzioni. La cache di SQLite e limitata a 64 KiB. File modificati ripartono da una nuova osservazione; una configurazione modificata invalida i risultati precedenti. Il database viene chiuso prima di uscire.
3. Applica prima memoria esplicitamente abilitata, una sola categoria presente nel nome e regole per estensione dei file non documentali. Le regole non caricano l'IA.
4. Per i restanti file carica MiniLM una sola volta nella scansione. Converte nome e un breve testo in un vettore e confronta la vicinanza con le descrizioni delle categorie. Non genera risposte, ragionamenti o categorie inventate.
5. Una proposta richiede similarita almeno 0.50 e un margine di almeno 0.10 sulla seconda categoria. Sono soglie euristiche, NON probabilita. Con `ai_auto_move: false`, il log mostra la proposta e il file va a Unsorted per revisione; con true viene usata la destinazione proposta. Casi incerti usano il fallback per estensione o Unsorted.
6. Windows rinomina atomicamente sullo stesso volume, senza sovrascrivere file esistenti. Fra volumi diversi copia a blocchi di 64 KiB, verifica dimensione e metadati del sorgente e lo rimuove solo alla fine. In caso di errore il sorgente resta disponibile per un retry.
7. Termina il processo: modello, tokenizer e librerie cessano di essere residenti. Nessun timer Python rimane in attesa.

La disponibilita di un file e ancora una verifica euristica: un download che resta fermo a lungo senza suffisso temporaneo puo sembrare completo. Vengono ignorati file temporanei, shortcut, link simbolici e alcuni file di sistema. Si esamina solo la cartella Downloads principale. File identici gia presenti nella destinazione rimangono in Downloads; il risultato e salvato per non ricalcolare gli hash a ogni scansione. Cambiare le regole li rende riesaminabili.

## Il modello scelto

**paraphrase-multilingual-MiniLM-L12-v2, ONNX INT8**, modello di embedding multilingue di Sentence Transformers. [Modello ufficiale](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) e [pesi quantizzati ufficiali](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/tree/main/onnx).

Scelta per questa classificazione semantica, non per chat o reasoning generale. Supporta 50 lingue e produce vettori a 384 dimensioni. E una scelta piccola e pratica fra i modelli multilingui valutati; non viene presentata come il piu piccolo modello esistente o come infallibile.

- Modello: 118.45 MB su disco; tokenizer originale SentencePiece: 5.07 MB. Circa 117.8 MiB complessivi.
- Solo ONNX Runtime, NumPy e SentencePiece; niente Torch, Transformers, tokenizers/Hugging Face Hub o Ollama nel percorso di esecuzione.
- Un thread per runtime e BLAS, un file alla volta e massimo 128 token: niente batch con grandi tensori o pool di decine di thread.
- Pesi e tokenizer scaricati soltanto dall'installatore: revisione fissata e SHA-256 verificati. Durante la classificazione non si usa la rete.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
.venv\Scripts\python.exe config\install_model.py
```

Configurazione essenziale:

```json
"ai_enabled": true,
"ai_backend": "semantic",
"ai_auto_move": false,
"ai_min_similarity": 0.50,
"ai_min_margin": 0.10
```

Sono chiavi dell'oggetto JSON esistente, non un file completo. Ogni categoria puo avere `description`, preferibilmente una frase con esempi italiani del contenuto previsto. Il modello viene caricato solo quando ci sono categorie con una destinazione e un file pronto che richiede analisi. Se manca il modello o una dipendenza, il log segnala il problema e vengono usate le regole di fallback.

Il backend Ollama precedente rimane selezionabile con `ai_backend: "ollama"`, ma richiede un servizio esterno e non offre lo stesso zero RAM del percorso semantico. Il codice chiede di scaricare immediatamente il modello dopo ogni richiesta (`keep_alive: 0`); non arresta un servizio Ollama usato da altre applicazioni.

## Testo dei documenti

TXT/MD/CSV e sorgenti di codice supportati: lettura di massimo 800 caratteri. DOCX: ZIP e XML della libreria standard, senza caricare l'intero documento in python-docx; limite 5 MB sul file e 2 MB sull'XML decompresso. Nessuna esecuzione di macro. PDF: prime tre pagine, testo limitato nel prompt, con PyMuPDF opzionale:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-content.txt
```

Senza PyMuPDF viene usato il nome del PDF. Non ci sono OCR o comprensione di immagini; un PDF scansionato puo quindi restare incerto. Parser PDF, notifiche facoltative e file complessi possono aumentare i picchi rispetto al benchmark semplice.

## RAM misurata su questo PC

Misure del 2 ottobre 2026, Python 3.12, processi distinti. MiB = 1,048,576 byte; non sono limiti garantiti su ogni PC.

| Percorso | RAM residente | Picco residente | Picco privato impegnato |
| --- | ---: | ---: | ---: |
| Scansione senza IA | 22.1 MiB | 22.1 MiB | 12.3 MiB |
| MiniLM INT8 con 10 categorie, inferenza | 222.4 MiB | 269.2 MiB | 264.3 MiB |
| Candidato TF-IDF, inferenza su testo | 20.1 MiB | 20.1 MiB | 11.9 MiB |
| Candidato TF-IDF + estrazione di un PDF reale | 49.1 MiB | 49.1 MiB | 46.7 MiB |
| Processo terminato | 0 MiB del processo | - | 0 MiB del processo |

L'importazione precedente dell'app con GUI consumava circa 42.6 MiB, senza IA. La prima prova ONNX/tokenizers raggiungeva circa 904 MiB di picco privato; limitare i thread BLAS e usare SentencePiece ha eliminato il grosso di quel consumo. Il peso del file del modello e la RAM sono grandezze diverse.

Riproduci senza toccare i tuoi Downloads:

```powershell
.venv\Scripts\python.exe benchmark.py
.venv\Scripts\python.exe benchmark.py --ai
.venv\Scripts\python.exe -m unittest -v
.venv\Scripts\python.exe -m pip check
```

28 test di sicurezza e funzionamento, inclusi apprendimento TF-IDF, astensione, verifica del modello e separazione dei gruppi. Il modello reale ha passato 12 casi sintetici italiani su 12, inclusi casi ambigui e senza informazioni; usa descrizioni curate delle categorie. E una prova di funzionamento limitata, non una stima dell'accuratezza sui tuoi file. Gli ID del tokenizer SentencePiece sono stati confrontati con quelli del tokenizer ufficiale su 8 campioni, inclusi testo lungo e Unicode. La modalita desktop opzionale non e stata verificata visivamente.

## Categorie, file reali e modello piccolo

Le tre attivita sono state implementate: descrizioni ed esempi locali piu precisi,
raccolta di 306 esempi reali e confronto MiniLM/TF-IDF su gruppi separati.
Il candidato TF-IDF pesa circa 36 KB su disco. Le etichette ricavate dalle cartelle
restano provvisorie: dopo calibrazione accetta 17/105 file di test, con un errore;
non e abilitato per l'organizzazione. I risultati e la procedura per correggere
gli esempi e riaddestrare sono in [CATEGORIE.md](CATEGORIE.md).

```powershell
.venv\Scripts\python.exe classification_lab.py evaluate --semantic
.venv\Scripts\python.exe benchmark.py --tiny
.venv\Scripts\python.exe benchmark.py --tiny --pdf
```

`examples` e una lista facoltativa di massimo cinque testi per categoria nella
configurazione; MiniLM li usa insieme alla descrizione. Il backend `tiny` usa solo
la libreria standard e carica `models/tiny.json`, dopo verifica delle etichette e
del test. L'anno e i percorsi non sono caratteristiche del classificatore:
aggiornare `folder` non richiede riaddestramento. Le destinazioni attuali non sono
state cambiate automaticamente, perche non tutte hanno una corrispondenza certa
nelle cartelle di quinta.

## Miglioramenti utili

- **Prima la qualita dei dati:** correggere le etichette nel CSV e aggiungere esempi delle categorie mancanti. I percorsi danno indizi, non la verita.
- **Poi una nuova verifica:** tenere download futuri separati dai file gia usati per scegliere le soglie, includendo documenti ambigui e fuori categoria.
- **Per risparmiare piu RAM:** il candidato TF-IDF e gia disponibile, ma servono etichette confermate e risultati migliori prima di sostituire MiniLM.
- **Per eliminare l'attesa periodica:** integrare l'evento di download completato del browser. Senza integrazione, un watcher sempre attivo usa RAM e contraddice il requisito di nessun processo residente.
- **Per i PDF scansionati:** OCR solo su richiesta; aumentera consumo e dipendenze. Non serve aggiungerlo finche non ci sono file reali che lo richiedono.

## Funzioni precedenti

Dashboard, tray, hotkey e watcher sono conservati in `desktop.py`, ma non vengono importati dalla scansione leggera:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.venv\Scripts\python.exe organizer.py --desktop
```

Questa modalita e residente e non rispetta zero RAM inattiva. La memoria salvata e conservata; `learning_enabled` rimane un'opzione esplicita. Nella scansione breve si applicano regole gia apprese, ma non si osservano i successivi spostamenti manuali. La modalita desktop puo apprendere solo eventi di movimento completi, senza dedurre spostamenti da cancellazioni.

## Licenza

[MIT](LICENSE). Il modello ha licenza Apache-2.0.
