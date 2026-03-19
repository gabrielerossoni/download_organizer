import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import shutil
import logging
import json
import hashlib
try:
    import fitz  # pymupdf
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False
import ollama as ollama_client
from pathlib import Path
from datetime import datetime
from threading import Thread

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import keyboard
    from winotify import Notification
except ImportError:
    print("Installa le dipendenze: pip install -r requirements.txt")
    sys.exit(1)

CONFIG_PATH  = Path(__file__).parent / "config.json"
MEMORIA_PATH = Path(__file__).parent / "memoria.json"
OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5:7b"


# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("[ERRORE] config.json non trovato. Esegui prima 1_SETUP_PRIMA.bat")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
# LOGGER
# ─────────────────────────────────────────────

def setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("organizer")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    return logger


# ─────────────────────────────────────────────
# CLASSIFICATORE AI (Ollama)
# ─────────────────────────────────────────────

class AIClassifier:
    def __init__(self, cfg: dict, logger: logging.Logger):
        self.cfg    = cfg
        self.log    = logger
        self.model  = cfg.get("ollama_model", OLLAMA_MODEL)
        self.url    = cfg.get("ollama_url", OLLAMA_URL)
        self.subjects      = [s["name"] for s in cfg.get("school_subjects", [])]
        self.personal_cats = [p["name"] for p in cfg.get("personal_categories", [])]

    def _extract_text(self, path: Path, max_chars: int = 800) -> str:
        """Estrae testo dai primi contenuti del file, max_chars caratteri."""
        try:
            ext = path.suffix.lower()
            if ext == ".pdf" and HAS_PDF:
                doc = fitz.open(str(path))
                text = ""
                for page in doc[:3]:  # prime 3 pagine
                    text += page.get_text()
                    if len(text) >= max_chars:
                        break
                doc.close()
                return text[:max_chars].strip()
            elif ext in (".docx",) and HAS_DOCX:
                doc = DocxDocument(str(path))
                text = "\n".join(p.text for p in doc.paragraphs[:30])
                return text[:max_chars].strip()
            elif ext in (".txt", ".md", ".csv"):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read(max_chars).strip()
        except Exception as e:
            self.log.debug(f"Estrazione testo fallita per {path.name}: {e}")
        return ""
    
    def _build_prompt(self, filename: str, extension: str, content: str = "") -> str:
        subjects_str = ", ".join(self.subjects) if self.subjects else "nessuna"
        personal_str = ", ".join(self.personal_cats) if self.personal_cats else "Personale"
        
        content_section = f'\nPrime righe del contenuto:\n"""\n{content}\n"""' if content else ""

        return f"""Classifica questo file. Rispondi SOLO con JSON, nessun altro testo.

Nome file : "{filename}"
Estensione: "{extension}"{content_section}

Materie scolastiche disponibili: {subjects_str}
Categorie personali disponibili: {personal_str}

Esempi di argomenti per materia (non esaustivi):
- Sistemi: packet tracer, cisco, reti, router, switch, protocolli, TCP/IP, firewall, VLAN
- Informatica: programmazione, algoritmo, python, java, database, SQL, codice
- Matematica: equazioni, algebra, geometria, calcolo, disequazioni, integrali
- Italiano: letteratura, dante, grammatica, analisi, tema, poesia, autore
- Storia: guerra, rivoluzione, impero, medioevo, fascismo, risorgimento
- Telecomunicazioni: segnali, frequenze, modulazione, antenna, fibra
- Tecnologie: elettronica, circuiti, componenti, Arduino

Se il nome o il contenuto del nome suggerisce uno di questi argomenti, classifica nella materia corrispondente.
Se è personale (foto vacanze, musica, giochi ecc.) classifica come personale.
Se non sei sicuro almeno al 70%, usa unsure.

Rispondi SOLO con questo JSON:
{{"type": "scuola|personale|unsure", "category": "nome_esatto_dalla_lista", "confidence": 0.0, "reason": "breve"}}"""
    
    def classify(self, path: Path, extension: str) -> dict:
        filename = path.name
        UNSURE = {"type": "unsure", "category": "", "confidence": 0, "reason": ""}
        try:
            content = self._extract_text(path)
            if content:
                self.log.debug(f"   Testo estratto: {len(content)} caratteri")
            response = ollama_client.chat(
                model=self.model,
                messages=[{"role": "user", "content": self._build_prompt(filename, extension, content)}],
                format="json"
            )
            raw = response["message"]["content"].strip()
            raw = raw.strip("`").replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)

            # Normalizza varianti che il modello può restituire
            type_map = {
                "scuola": "scuola", "scolastico": "scuola", "school": "scuola",
                "personale": "personale", "personal": "personale",
                "unsure": "unsure", "unknown": "unsure", "incerto": "unsure"
            }
            raw_type = result.get("type", "").lower().strip()
            normalized = type_map.get(raw_type)
            if not normalized:
                raise ValueError(f"type non valido: {raw_type}")
            result["type"] = normalized
            
            if float(result.get("confidence", 0)) < 0.70:
                self.log.debug(f"Confidenza bassa ({result.get('confidence'):.2f}) per '{filename}'")
                return UNSURE
            return result
        except ollama_client.ResponseError as e:
            self.log.warning(f"Ollama errore modello '{filename}': {e}")
            return {**UNSURE, "reason": str(e)}
        except Exception as e:
            self.log.warning(f"Errore AI su '{filename}': {e}")
            return {**UNSURE, "reason": str(e)}


# ─────────────────────────────────────────────
# CORE ORGANIZER
# ─────────────────────────────────────────────

class Organizer:
    def __init__(self, cfg: dict, logger: logging.Logger):
        self.cfg        = cfg
        self.log        = logger
        self.dry_run    = cfg.get("dry_run", False)
        self.dl_dir     = Path(cfg["download_folder"])
        self.unsure_dir = Path(cfg.get("unsure_folder_path", str(self.dl_dir / "Da_Smistare")))
        self.ai         = AIClassifier(cfg, logger)

        # Mappa nome_materia (lowercase) → Path
        self.subject_map: dict[str, Path] = {
            s["name"].lower(): Path(s["folder"])
            for s in cfg.get("school_subjects", []) if s.get("folder")
        }

        # Mappa categoria_personale (lowercase) → Path
        self.personal_map: dict[str, Path] = {
            p["name"].lower(): Path(p["folder"])
            for p in cfg.get("personal_categories", []) if p.get("folder")
        }

        # Fallback estensione → Path
        self.ext_map: dict[str, Path] = {}
        for rule in cfg.get("extension_rules", []):
            if rule.get("folder"):
                for ext in rule["extensions"]:
                    self.ext_map[ext.lower()] = Path(rule["folder"])

        if self.dry_run:
            self.log.warning("=== DRY RUN — nessun file verrà spostato ===")

    # ── Utilità ──────────────────────────────

    def _is_ready(self, path: Path) -> bool:
        try:
            s1 = path.stat().st_size
            time.sleep(1.5)
            s2 = path.stat().st_size
            if s1 != s2:
                self.log.debug(f"Ancora in scrittura: {path.name}")
                return False
            if s2 < self.cfg.get("min_size_bytes", 100):
                self.log.debug(f"Troppo piccolo, skip: {path.name}")
                return False
            return True
        except (FileNotFoundError, PermissionError):
            return False

    def _same_file(self, a: Path, b: Path) -> bool:
        try:
            def md5(p):
                h = hashlib.md5()
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                return h.hexdigest()
            return md5(a) == md5(b)
        except Exception:
            return False

    def _move(self, src: Path, dest_dir: Path, label: str = "") -> bool:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name

            if dest.exists():
                if self._same_file(src, dest):
                    self.log.info(f"Duplicato esatto, skip: {src.name}")
                    return False
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = dest_dir / f"{src.stem}_{ts}{src.suffix}"

            if self.dry_run:
                self.log.info(f"[DRY RUN] {src.name} → {dest_dir} {label}")
                return True

            shutil.move(str(src), str(dest))
            self.log.info(f"✓ {src.name} → {dest_dir.name}/ {label}")
            return True

        except PermissionError:
            self.log.warning(f"Permesso negato: {src.name}")
            return False
        except Exception as e:
            self.log.error(f"Errore spostando {src.name}: {e}")
            return False

    # ── Logica principale ─────────────────────

    def process_file(self, path: Path):
        if not path.is_file():
            return
        if path.parent != self.dl_dir:
            return
        if path.name.startswith(".") or path.suffix.lower() in (".tmp", ".crdownload", ".part", ".download"):
            return

        time.sleep(self.cfg.get("wait_seconds", 3))
        if not self._is_ready(path):
            return

        ext = path.suffix.lower()
        self.log.info(f"── Analisi: {path.name}")
        name_lower = path.stem.lower()

        # LIVELLO 1 — nome contiene esattamente il nome di una materia
        for subject in self.cfg.get("school_subjects", []):
            subj_name = subject["name"].lower()
            if subj_name in name_lower and subject.get("folder"):
                self.log.info(f"   Match diretto: '{subject['name']}'")
                dest = Path(subject["folder"])
                if self._move(path, dest, f"[diretto/{subject['name']}]"):
                    self._notify(f"📚 {path.name}", f"Scuola → {subject['name']}")
                return

        # LIVELLO 2 — AI (soglia 60%)
        result = self.ai.classify(path, ext)
        rtype  = result.get("type")
        cat    = result.get("category", "").lower().strip()
        self.log.debug(f"   AI → {rtype} / {cat} (conf={result.get('confidence', 0):.2f}) — {result.get('reason','')}")

        if rtype == "scuola" and cat:
            dest = self.subject_map.get(cat)
            if dest:
                if self._move(path, dest, f"[scuola/{cat}]"):
                    self._notify(f"📚 {path.name}", f"Scuola → {cat}")
                return

        if rtype == "personale" and cat:
            dest = self.personal_map.get(cat)
            if dest:
                if self._move(path, dest, f"[personale/{cat}]"):
                    self._notify(f"🗂 {path.name}", f"Personale → {cat}")
                return

        # LIVELLO 3 — fallback estensione
        dest = self.ext_map.get(ext)
        if dest:
            if self._move(path, dest, f"[ext/{ext}]"):
                self._notify(f"📁 {path.name}", f"Spostato → {dest.name}")
            return

        # LIVELLO 4 — File_Sconosciuti
        self.log.info(f"? Nessuna categoria: {path.name} → File_Sconosciuti/")
        self._move(path, self.unsure_dir, "[unsure]")
        self._notify(f"❓ {path.name}", "Non classificato → File_Sconosciuti/")

    def scan_all(self):
        self.log.info("── Scansione manuale ──")
        files = [f for f in self.dl_dir.iterdir() if f.is_file()]
        self.log.info(f"   {len(files)} file trovati")
        for f in files:
            self.process_file(f)
        self.log.info("── Fine scansione ──")

    def _notify(self, title: str, msg: str):
        try:
            toast = Notification(app_id="Download Organizer", title=title, msg=msg, duration="short")
            toast.show()
        except Exception:
            pass


# ─────────────────────────────────────────────
# WATCHDOG
# ─────────────────────────────────────────────

class DownloadHandler(FileSystemEventHandler):
    def __init__(self, org: Organizer):
        self.org = org

    def on_created(self, event):
        if not event.is_directory:
            Thread(target=self.org.process_file, args=(Path(event.src_path),), daemon=True).start()

    def on_moved(self, event):
        if not event.is_directory:
            Thread(target=self.org.process_file, args=(Path(event.dest_path),), daemon=True).start()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    cfg    = load_config()
    log_p  = Path(__file__).parent / cfg.get("log_file", "organizer.log")
    logger = setup_logger(str(log_p))

    logger.info("═══ Download Organizer v3 (Ollama/Qwen2.5) ═══")
    logger.info(f"Modello : {cfg.get('ollama_model', OLLAMA_MODEL)}")
    logger.info(f"Cartella: {cfg['download_folder']}")

    try:
        ollama_client.list()
        logger.info("Ollama: connesso ✓")
    except Exception:
        logger.warning("⚠ Ollama non raggiungibile — i file andranno in Da_Smistare finché non parte")

    org      = Organizer(cfg, logger)
    handler  = DownloadHandler(org)
    observer = Observer()
    observer.schedule(handler, str(org.dl_dir), recursive=False)
    observer.start()

    hotkey = cfg.get("hotkey", "ctrl+shift+o")
    keyboard.add_hotkey(hotkey, lambda: Thread(target=org.scan_all, daemon=True).start())
    logger.info(f"Watcher attivo | Hotkey: {hotkey} | Ctrl+C per fermare")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Chiusura...")
    finally:
        observer.stop()
        observer.join()
        logger.info("═══ Fermato ═══")


if __name__ == "__main__":
    main()
