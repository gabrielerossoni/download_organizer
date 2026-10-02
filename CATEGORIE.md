# Categorie e casi ambigui

Le categorie indicano il significato del file; `folder` indica dove salvarlo oggi.
Cambiando anno scolastico si aggiornano le destinazioni, non le etichette del modello.
Le destinazioni locali attuali di quarta sono conservate: quinta contiene nomi diversi
e non tutte le materie hanno una cartella corrispondente.

| Categoria | Contenuto previsto | Esempi | Confine da verificare |
| --- | --- | --- | --- |
| Informatica | Programmazione e database scolastici, algoritmi, classi Java, Python, SQL | Classi ed ereditarieta; vettori; query SQL | Un sorgente Java non dimostra che sia scolastico |
| Tecnologie / TPSIT | Processi e concorrenza, Unix, thread, sincronizzazione, progettazione di sistemi | fork/exec/waitpid; mutex; algoritmo del banchiere | Reti e IoT possono sovrapporsi alle altre materie |
| Sistemi | Progettazione e configurazione di reti e server | Subnet; routing; cablaggio; Syslog; data center | Un protocollo puo essere trattato anche in Telecomunicazioni |
| Telecomunicazioni | Segnali e collegamenti, Arduino, bus e protocolli IoT | UART; SPI; I2C; MQTT; modulazione | MQTT non identifica da solo una materia |
| Italiano | Letteratura e analisi del testo | Dante; poesia; romanzi; autori | La cartella ItalianoStoria non permette di separare le due materie |
| Storia | Eventi storici e contesto politico/sociale | Rivoluzioni; guerre; Risorgimento | Richiede esempi etichettati separatamente da Italiano |
| Corsi Esterni | Materiale di una formazione extrascolastica identificabile | Dispensa con titolo del corso | Dal solo argomento non si ricava dove e stato studiato |
| Progetti | Documentazione e materiale dei propri progetti personali | README; istruzioni di installazione; piano di funzionalita | Un esercizio scolastico puo chiamarsi progetto e usare le stesse tecnologie |
| Foto / Video / Musica | Media personali | JPG; MP4; MP3 | Le estensioni bastano per il tipo di file, non per riconoscere contenuti personali |

Le descrizioni di Tecnologie, Progetti, Informatica, Sistemi e Telecomunicazioni e
i rispettivi esempi sono stati aggiunti alla configurazione locale. Non sono nuove
etichette corrette per tutti i file: in particolare la provenienza personale/scolastica
spesso non e ricavabile dal contenuto.

## Esperimento su file reali

`classification_lab.py` raccoglie esempi locali senza spostarli. Dalle cartelle di
quarta, quinta e dei progetti personali sono stati raccolti 306 esempi: 117 per
addestramento, 84 per calibrare le soglie, 105 per test. I documenti dello stesso
progetto restano nello stesso gruppo; i duplicati esatti sono esclusi. File generati,
dipendenze e collegamenti sono esclusi. Italiano/Storia sono esclusi dalla raccolta
automatica perche condividono la destinazione. Foto, Video e Musica non hanno
campioni documentali in questo insieme.

I nomi delle cartelle producono **etichette provvisorie**. Non e una misura
dell'accuratezza verificata dall'utente. I risultati restano in
`memory/classification/report.json`, con le singole previsioni in `predictions.json`.
Il corpus contiene percorsi e frammenti di testo privati: e ignorato da Git e non
viene inviato a servizi esterni.

Il modello piccolo usa TF-IDF: pesa le parole frequenti nel documento e distintive
nel corpus, poi confronta il documento con un vettore medio per categoria.
Non genera risposte e non carica ONNX, NumPy o un server. La soglia di similarita
e il distacco dalla seconda categoria sono scelti sulla validazione, prima del test.
Se non esiste una soglia con almeno cinque previsioni accettate e zero errori
osservati sulla validazione, il candidato si astiene su tutto.

Risultati del 2 ottobre 2026, dopo la lettura dei PDF con PyMuPDF:

| Modello | Senza astensione: accordo con cartelle sul test | Con soglie | File accettati |
| --- | ---: | --- | ---: |
| TF-IDF, 36.168 byte su disco | 68/105 (64,8%) | 16 corretti, 1 errore | 17/105 |
| MiniLM, soglie attuali 0,50 / 0,10 | 43/105 (41,0%) | 3 corretti, 0 errori | 3/105 |

La calibrazione di MiniLM non ha trovato una soglia con almeno cinque accettazioni
senza errori sulla validazione. Il candidato TF-IDF non e abilitato: ha commesso un
errore sul test, le etichette non sono confermate e mancano campioni di alcune
categorie. `ai_auto_move` resta disattivato. Pochi successi non garantiscono zero
errori su file nuovi.

## Correggere e ripetere

1. Aprire `memory/classification/examples.csv` con un editor CSV/testo UTF-8.
   Per ciascun esempio correggere `kind` (`school`/`personal`) e `label`, poi
   mettere `reviewed` a `yes` soltanto dopo verifica. Il campo `group` raggruppa
   un progetto: non dividerlo per ottenere risultati migliori. Se non sai la
   categoria, escludi la riga dall'addestramento; non forzare una risposta.
2. Aggiungere esempi mancanti, soprattutto Italiano, Storia e corsi esterni; tenere
   anche file ambigui nuovi per una verifica separata. Le etichette delle immagini
   non si imparano leggendo testo: per quei file usare le regole sulle estensioni.
3. Eseguire:

```powershell
.venv\Scripts\python.exe classification_lab.py evaluate --semantic
.venv\Scripts\python.exe benchmark.py --tiny
.venv\Scripts\python.exe -m unittest -q
```

L'esperimento salva `models/tiny-candidate.json`, senza modificare il backend o le
soglie operative. `eligible_for_manual_activation` puo diventare vero soltanto
con etichette tutte confermate, almeno tre campioni di ogni categoria configurata
in ciascuna delle tre partizioni e almeno
dieci previsioni accettate senza errori sul test. Questo controllo minimo non e
una certificazione: serve poi una prova su download nuovi, senza spostamenti.
Rivedere ripetutamente il test per ottimizzare il modello lo rende un altro
insieme di validazione: per il giudizio finale servono file nuovi.

Solo dopo le verifiche, copiare il candidato in `models/tiny.json` e impostare
`ai_backend` a `tiny`. Il runtime rifiuta candidati non verificati, modelli oltre
1 MB su disco e categorie cambiate. Cambiare solo `folder` non invalida il modello.
La RAM del processo Python resta nell'ordine delle decine di MB: un modello sotto
1 MB su disco non rende il processo sotto 1 MB di RAM. Quando termina, la sua RAM
viene liberata.

Il benchmark locale ha misurato 20,1 MiB residenti per l'inferenza TF-IDF su testo
e 49,1 MiB includendo l'estrazione di un PDF reale. Sono campioni, non massimi
garantiti per qualsiasi documento; il lettore PDF pesa piu del classificatore.

Per raccogliere un nuovo anno si puo usare `collect --school-root PERCORSO`;
`--projects-root PERCORSO` aggiunge i progetti personali. La raccolta rifiuta di
sovrascrivere un CSV gia presente, per preservare le correzioni manuali.
