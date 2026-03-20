import warnings
warnings.filterwarnings("ignore")

import os
import sys
import time
import shutil
import logging
import json
import hashlib
from flask import Flask, jsonify, request, Response, render_template_string
import queue
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
from threading import Thread, Lock
import pystray
from PIL import Image, ImageDraw

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    import keyboard
    from winotify import Notification
except ImportError:
    print("Installa le dipendenze: pip install -r requirements.txt")
    sys.exit(1)

CONFIG_PATH  = Path(__file__).parent / "config" / "config.json"
listeners = []  # connessioni SSE attive
MEMORIA_PATH = Path(__file__).parent / "memory" / "history.json"
LOG_QUEUE = queue.Queue(maxsize=500)  # coda eventi per SSE
OLLAMA_MODEL = "llama3.1:8b"


def print_banner(logger: logging.Logger):
    banner = r"""
    ___               _                 _ 
   |   \  ___ __ __ _ | | ___  __ _  __| |
   | |  |/ _ \\ V  V /| |/ _ \/ _` |/ _` |
   |___/ \___/ \_/\_/ |_|\___/\__,_|\__,_|
    ___                             _               
   / _ \  _ _  __ _  __ _  _ _ (_) ___ ___  _ _ 
  | (_) || '_|/ _` |/ _` || ' \| ||_ // -_)| '_|
   \___/ |_|  \__, |\__,_||_||_|_|/__|\___||_|  
              |___/                             
    """
    logger.info(banner)
    logger.info("⚡ Version 4.0 Pro | English Localization Active")
    logger.info("─" * 50)

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("[ERRORE] config.json non trovato. Esegui prima Setup.bat")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
# LOGGER
# ─────────────────────────────────────────────

class SSEHandler(logging.Handler):
    def emit(self, record):
        item = {
            "time": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage()
        }
        try:
            LOG_QUEUE.put_nowait(item)
        except queue.Full:
            pass
        for q in listeners:
            try:
                q.put_nowait(item)
            except queue.Full:
                pass
                
def setup_logger(log_path: str) -> logging.Logger:
    logger = logging.getLogger("organizer")
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(log_path, encoding="utf-8-sig")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)
    sse = SSEHandler()
    sse.setLevel(logging.INFO)
    logger.addHandler(sse)
    return logger

# ─────────────────────────────────────────────
# CLASSIFICATORE AI (Ollama)
# ─────────────────────────────────────────────

class AIClassifier:
    def __init__(self, cfg: dict, logger: logging.Logger):
        self.cfg    = cfg
        self.log    = logger
        self.model  = cfg.get("ollama_model", OLLAMA_MODEL)
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
        subjects_str = ", ".join(self.subjects) if self.subjects else "none"
        personal_str = ", ".join(self.personal_cats) if self.personal_cats else "Personal"
        content_section = f'\nContent (first lines):\n"""\n{content}\n"""' if content else ""

        return f"""You are a helper that classifies downloaded files for a student.

File Name : "{filename}"
Extension : "{extension}"{content_section}

Available School Subjects: {subjects_str}
Available Personal Categories: {personal_str}

Use your general knowledge to decide which category the file belongs to.
Reasoning examples:
- If the name contains an author, a literary movement, or a historical period -> deduce the subject.
- If the content discusses networks, protocols, or code -> deduce the technical subject.
- If it has nothing to do with school -> it is Personal.

Rules:
- Choose the category ONLY from the available lists above.
- If you are less than 70% sure, use 'unsure'.
- .ini, .db, .lnk files should always be 'unsure'.
- Do not invent categories outside the list.

Respond ONLY with this JSON:
{{"type": "school|personal|unsure", "category": "exact_name_from_list", "confidence": 0.0, "reason": "short explanation in English"}}"""
    
    def classify(self, path: Path, extension: str) -> dict:
        filename = path.name
        UNSURE = {"type": "unsure", "category": "", "confidence": 0, "reason": ""}
        try:
            content = self._extract_text(path)
            if content:
                self.log.debug(f"   Extracted text: {len(content)} chars")
            response = ollama_client.chat(
                model=self.model,
                messages=[{"role": "user", "content": self._build_prompt(filename, extension, content)}],
                format="json"
            )
            raw = response["message"]["content"].strip()
            raw = raw.strip("`").replace("```json", "").replace("```", "").strip()
            result = json.loads(raw)

            # Normalize model variations
            type_map = {
                "school": "school", "scholastic": "school", "scuola": "school",
                "personal": "personal", "personale": "personal",
                "unsure": "unsure", "unknown": "unsure"
            }
            raw_type = result.get("type", "").lower().strip()
            normalized = type_map.get(raw_type)
            if not normalized:
                raise ValueError(f"Invalid type: {raw_type}")
            result["type"] = normalized
            
            if float(result.get("confidence", 0)) < 0.70:
                self.log.debug(f"🧠 Low confidence ({result.get('confidence'):.2f}) for '{filename}'")
                return UNSURE
            return result
        except ollama_client.ResponseError as e:
            self.log.warning(f"🧠 AI: Model error on '{filename}': {e}")
            return {**UNSURE, "reason": str(e)}
        except Exception as e:
            self.log.warning(f"🧠 AI: Error on '{filename}': {e}")
            return {**UNSURE, "reason": str(e)}

# ─────────────────────────────────────────────
# MEMORY
# ─────────────────────────────────────────────
class Memoria:
    def __init__(self, logger: logging.Logger):
        self.log   = logger
        self.path  = MEMORIA_PATH
        self.rules = self._load()
        self.pending = {} # filename -> timestamp

    def _load(self) -> list:
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.log.warning(f"🧠 Memory: error saving history: {e}")

    def learn(self, filename: str, dest_path: str):
        """Saves a rule learned from a manual move."""
        stem = Path(filename).stem.lower()
        # Extract meaningful keywords (>3 chars)
        words = [w for w in stem.replace("_", " ").replace("-", " ").split() if len(w) > 3]
        if not words:
            return
        # Check if a similar rule already exists
        for rule in self.rules:
            if rule["dest"] == dest_path and any(w in rule["keywords"] for w in words):
                # Update keywords and hits
                rule["keywords"] = list(set(rule["keywords"] + words))
                rule["hits"] = rule.get("hits", 0) + 1
                self._save()
                self.log.info(f"🧠 Memory: updated rule for '{Path(dest_path).name}' (hits={rule['hits']})")
                return
        # New rule
        rule = {"keywords": words, "dest": dest_path, "hits": 1, "example": filename}
        self.rules.append(rule)
        self._save()
        self.log.info(f"🧠 Memory: new rule from '{filename}' → '{Path(dest_path).name}' (tags: {words})")

    def match(self, filename: str) -> str | None:
        stem = Path(filename).stem.lower()
        best_rule  = None
        best_score = 0
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            score = sum(1 for kw in rule["keywords"] if kw in stem)
            if score > best_score:
                best_score = score
                best_rule  = rule
        if best_rule and best_score >= 1:
            return best_rule["dest"]
        return None
    
    def add_pending(self, filename: str):
        self.pending[filename] = time.time()

    def resolve_pending(self, dest_path: Path):
        name = dest_path.name
        if name in self.pending:
            del self.pending[name]
            self.learn(name, str(dest_path.parent))
    
# ─────────────────────────────────────────────
# WATCHDOG
# ─────────────────────────────────────────────
class UnsureWatcher(FileSystemEventHandler):
    """Monitors Unsorted folder — learns when the user moves a file manually."""
    def __init__(self, memoria: Memoria, logger: logging.Logger):
        self.memoria = memoria
        self.log     = logger

    def on_moved(self, event):
        if not event.is_directory:
            src  = Path(event.src_path)
            dest = Path(event.dest_path)
            # File moved out of Unsorted to another folder
            if dest.parent != src.parent:
                self.log.info(f"🧠 Memory: manual move detected: {src.name} → {dest.parent.name}/")
                self.memoria.learn(src.name, str(dest.parent))
                
    def on_deleted(self, event):
        if not event.is_directory:
            src = Path(event.src_path)
            # Add to pending — destination not yet known
            self.log.debug(f"🧠 Memory: file removed from Unsorted: {src.name}")
            self.memoria.add_pending(src.name)

# ─────────────────────────────────────────────
# CORE ORGANIZER
# ─────────────────────────────────────────────

class Organizer:
    def __init__(self, cfg: dict, logger: logging.Logger):
        self.cfg        = cfg
        self.log        = logger
        self.dry_run    = cfg.get("dry_run", False)
        self.dl_dir     = Path(cfg["download_folder"])
        self.unsure_dir = Path(cfg.get("unsure_folder_path", str(self.dl_dir / "Unsorted")))
        self.ai         = AIClassifier(cfg, logger)
        self.memoria    = Memoria(logger)
        self.moved_count = 0
        self._scan_lock = Lock()

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
            self.log.warning("⚠ DRY RUN — no files will be moved")

    # ── Utilità ──────────────────────────────

    def _is_ready(self, path: Path) -> bool:
        try:
            s1 = path.stat().st_size
            time.sleep(1.5)
            s2 = path.stat().st_size
            if s1 != s2:
                self.log.debug(f"Still writing: {path.name}")
                return False
            if s2 < self.cfg.get("min_size_bytes", 100):
                self.log.debug(f"Too small, skipping: {path.name}")
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
        time.sleep(self.cfg.get("wait_seconds", 3))
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name

            if dest.exists():
                if self._same_file(src, dest):
                    self.log.info(f"Duplicate found, skipping: {src.name}")
                    return False
                ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = dest_dir / f"{src.stem}_{ts}{src.suffix}"

            if self.dry_run:
                self.log.info(f"[DRY RUN] {src.name} → {dest_dir} {label}")
                return True

            shutil.move(str(src), str(dest))
            self.moved_count += 1
            self.log.info(f"✓ {src.name} → {dest_dir.name}/ {label}")
            return True

        except PermissionError:
            self.log.warning(f"Permission denied: {src.name}")
            return False
        except Exception as e:
            self.log.error(f"Error moving {src.name}: {e}")
            return False

    # ── Logica principale ─────────────────────

    def process_file(self, path: Path):
        if not path.is_file():
            return
        if path.parent != self.dl_dir:
            return
        if path.name.startswith(".") or path.name in ("desktop.ini", "thumbs.db") or path.suffix.lower() in (".tmp", ".crdownload", ".part", ".download", ".ini", ".db", ".lnk"):
            return
        if not self._is_ready(path):
            return
        
        ext = path.suffix.lower()
        self.log.info(f"── Analyzing: {path.name}")
        name_lower = path.stem.lower()
        
        # LEVEL 0 — Memory (Previous manual moves)
        learned_dest = self.memoria.match(path.name)
        if learned_dest:
            dest = Path(learned_dest)
            if dest.exists():
                self.log.info(f"   Memory match: {dest.name}")
                if self._move(path, dest, "[memory]"):
                    self._notify(f"🧠 {path.name}", f"From memory → {dest.name}")
                return

        # LEVEL 1 — Direct keyword match
        for subject in self.cfg.get("school_subjects", []):
            subj_name = subject["name"].lower()
            if subj_name in name_lower and subject.get("folder"):
                self.log.info(f"   Direct match: '{subject['name']}'")
                dest = Path(subject["folder"])
                if self._move(path, dest, f"[direct/{subject['name']}]"):
                    self._notify(f"📚 {path.name}", f"School → {subject['name']}")
                return

        # LEVEL 2 — AI (Threshold 60%)
        result = self.ai.classify(path, ext)
        rtype  = result.get("type")
        cat    = result.get("category", "").lower().strip()
        self.log.debug(f"   AI Category: {rtype} / {cat} (conf={result.get('confidence', 0):.2f}) — {result.get('reason','')}")

        if rtype == "school" and cat:
            dest = self.subject_map.get(cat)
            if dest:
                if self._move(path, dest, f"[school/{cat}]"):
                    self._notify(f"📚 {path.name}", f"School → {cat}")
                return

        if rtype == "personal" and cat:
            dest = self.personal_map.get(cat)
            if dest:
                if self._move(path, dest, f"[personal/{cat}]"):
                    self._notify(f"🗂 {path.name}", f"Personal → {cat}")
                return

        # LEVEL 3 — Extension Fallback
        dest = self.ext_map.get(ext)
        if dest:
            if self._move(path, dest, f"[ext/{ext}]"):
                self._notify(f"📁 {path.name}", f"Moved → {dest.name}")
            return

        # LEVEL 4 — Unsorted
        self.log.info(f"❓ No category found: {path.name} → Unsorted/")
        self._move(path, self.unsure_dir, "[unsure]")
        self._notify(f"❓ {path.name}", "Not classified → Unsorted/")

    def scan_all(self):
        if not self._scan_lock.acquire(blocking=False):
            self.log.debug("Scan already in progress, skipping")
            return
        try:
            self.log.info("── Manual Scan Started ──")
            files = [f for f in self.dl_dir.iterdir() if f.is_file()]
            self.log.info(f"   {len(files)} files found")
            for f in files:
                self.process_file(f)
            self.log.info("── Scan Finished ──")
        finally:
            self._scan_lock.release()

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
# Tray Icon
# ─────────────────────────────────────────────

def create_tray_icon(org, observer, logger, tray_state):

    def make_icon_image(active: bool = True) -> Image.Image:
        size = (128, 128) # Higher res for better quality
        img  = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Professional Colors
        base_cyan = (79, 195, 247, 255) if active else (140, 140, 140, 255)
        deep_blue = (2, 119, 189, 255) if active else (100, 100, 100, 255)
        glow_color = (129, 212, 250, 255) if active else (160, 160, 160, 255)
        
        # 1. Shadow / Base depth
        draw.rounded_rectangle([15, 30, 113, 110], radius=12, fill=(0, 0, 0, 60))
        
        # 2. Main Folder Body (Gradient-like effect using layers)
        draw.rounded_rectangle([12, 28, 110, 105], radius=12, fill=deep_blue)
        draw.rounded_rectangle([12, 45, 110, 105], radius=12, fill=base_cyan)
        
        # 3. Folder Tab
        draw.rounded_rectangle([12, 15, 50, 35], radius=8, fill=base_cyan)
        
        # 4. Perspective highlight (Gloss)
        draw.rounded_rectangle([20, 50, 102, 60], radius=4, fill=(255, 255, 255, 40))
        
        # 5. Download Arrow (White with slight glow)
        white = (255, 255, 255, 255)
        # Glow
        draw.rectangle([58, 38, 70, 75], fill=glow_color)
        # Main Arrow
        draw.rectangle([60, 40, 68, 70], fill=white) # Stem
        draw.polygon([(48, 65), (80, 65), (64, 85)], fill=white) # Head
        
        return img.resize((64, 64), Image.Resampling.LANCZOS)

    state = {"running": True, "handler": DownloadHandler(org), "dl_dir": str(org.dl_dir)}

    def on_scan(icon, item):
        Thread(target=org.scan_all, daemon=True).start()

    def on_toggle(icon, item):
        if state["running"]:
            observer.stop()
            observer.join()
            state["running"] = False
            icon.icon = make_icon_image(active=False)
            icon.title = "Download Organizer — stopped"
            logger.info("Watcher stopped via Tray")
        else:
            new_obs = Observer()
            new_obs.schedule(state["handler"], state["dl_dir"], recursive=False)
            new_obs.start()
            state["new_obs"] = new_obs
            tray_state["new_obs"] = new_obs
            state["running"] = True
            icon.icon = make_icon_image(active=True)
            icon.title = "Download Organizer — active"
            logger.info("Watcher restarted via Tray")

    def on_open_log(icon, item):
        log_path = str(Path(__file__).parent / "organizer.log")
        WshShell = __import__("subprocess")
        WshShell.Popen([
            "powershell", "-NoExit", "-Command",
            f"Get-Content '{log_path}' -Wait -Tail 30 -Encoding UTF8"
        ])
        
    def on_open_dashboard(icon, item):
        import webbrowser
        webbrowser.open("http://127.0.0.1:5000")    
        
    def on_exit(icon, item):
        logger.info("Shutting down via Tray...")
        icon.stop()

    def get_toggle_label(item=None):
        return "Stop Watcher" if state["running"] else "Start Watcher"

    menu = pystray.Menu(
        pystray.MenuItem("Manual Scan",         on_scan, default=True),
        pystray.MenuItem(get_toggle_label,     on_toggle),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open Dashboard",      on_open_dashboard),
        pystray.MenuItem("Open Logs",           on_open_log),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit",                on_exit),
    )

    return pystray.Icon(
        name="download_organizer",
        icon=make_icon_image(),
        title="Download Organizer — active",
        menu=menu
    )

# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

def create_dashboard(org: Organizer, logger: logging.Logger):
    app = Flask(__name__)
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Download Organizer Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
<script src="https://unpkg.com/lucide@latest"></script>
<style>
  :root {
    --bg: #05070a;
    --card: rgba(255, 255, 255, 0.03);
    --border: rgba(255, 255, 255, 0.08);
    --accent: #4fc3f7;
    --accent-glow: rgba(79, 195, 247, 0.3);
    --text: #e0e6ed;
    --text-dim: #8492a6;
    --danger: #ff5252;
    --success: #00e676;
  }
  
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { 
    font-family: 'Outfit', sans-serif; 
    background: var(--bg); 
    background-image: radial-gradient(circle at 10% 20%, rgba(79, 195, 247, 0.05) 0%, transparent 40%), 
                      radial-gradient(circle at 90% 80%, rgba(2, 119, 189, 0.05) 0%, transparent 40%);
    color: var(--text); 
    padding: 30px;
    min-height: 100vh;
  }

  .container { max-width: 1200px; margin: 0 auto; }
  
  header { 
    display: flex; 
    justify-content: space-between; 
    align-items: center; 
    margin-bottom: 40px; 
    backdrop-filter: blur(10px);
    padding: 20px;
    border-radius: 20px;
    background: var(--card);
    border: 1px solid var(--border);
  }
  
  .logo { display: flex; align-items: center; gap: 15px; font-size: 1.5rem; font-weight: 600; letter-spacing: -0.5px; }
  .logo i { color: var(--accent); filter: drop-shadow(0 0 8px var(--accent-glow)); }
  
  .status-pill { 
    display: flex; 
    align-items: center; 
    gap: 8px; 
    background: rgba(0, 0, 0, 0.3); 
    padding: 6px 16px; 
    border-radius: 100px; 
    font-size: 0.85rem;
    border: 1px solid var(--border);
  }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--text-dim); transition: 0.3s; }
  .status-dot.online { background: var(--success); box-shadow: 0 0 10px var(--success); }
  .status-dot.offline { background: var(--danger); box-shadow: 0 0 10px var(--danger); }

  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
  .stat-card { 
    background: var(--card); 
    border: 1px solid var(--border); 
    padding: 20px; 
    border-radius: 16px; 
    backdrop-filter: blur(5px);
  }
  .stat-label { font-size: 0.8rem; color: var(--text-dim); text-transform: uppercase; margin-bottom: 5px; }
  .stat-value { font-size: 1.8rem; font-weight: 600; color: #fff; }

  .main-grid { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 30px; }
  .card { 
    background: var(--card); 
    border: 1px solid var(--border); 
    border-radius: 24px; 
    padding: 24px; 
    backdrop-filter: blur(12px);
    display: flex;
    flex-direction: column;
    height: 550px;
  }
  .card h2 { font-size: 1.1rem; margin-bottom: 20px; display: flex; align-items: center; gap: 10px; opacity: 0.9; }
  
  /* Log Box */
  .log-container { 
    flex: 1; 
    overflow-y: auto; 
    background: rgba(0,0,0,0.2); 
    border-radius: 16px; 
    padding: 15px; 
    font-family: 'Consolas', monospace; 
    font-size: 0.85rem;
    border: 1px solid rgba(255,255,255,0.03);
  }
  .log-line { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.02); animation: fadeIn 0.3s ease; }
  .log-time { color: var(--text-dim); margin-right: 12px; }
  .log-level { font-weight: 600; margin-right: 10px; width: 60px; display: inline-block; }
  .INFO .log-level { color: var(--accent); }
  .WARNING .log-level { color: #ffb74d; }
  .ERROR .log-level { color: var(--danger); }
  
  /* Rules */
  .rules-list { flex: 1; overflow-y: auto; padding-right: 5px; }
  .rule-item { 
    background: rgba(255,255,255,0.02); 
    border: 1px solid var(--border); 
    border-radius: 12px; 
    padding: 15px; 
    margin-bottom: 15px;
    transition: 0.2s;
  }
  .rule-item:hover { background: rgba(255,255,255,0.04); border-color: var(--accent); }
  .rule-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
  .rule-tags { display: flex; flex-wrap: wrap; gap: 6px; }
  .tag { background: rgba(79, 195, 247, 0.1); color: var(--accent); padding: 3px 10px; border-radius: 6px; font-size: 0.75rem; border: 1px solid rgba(79, 195, 247, 0.2); }
  .rule-dest { font-size: 0.8rem; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  
  .actions { display: flex; align-items: center; gap: 10px; }
  .btn-icon { background: none; border: none; color: var(--text-dim); cursor: pointer; padding: 5px; transition: 0.2s; }
  .btn-icon:hover { color: #fff; }
  .btn-icon.delete:hover { color: var(--danger); }
  
  .badge-hits { font-size: 0.7rem; background: rgba(255,255,255,0.05); padding: 2px 8px; border-radius: 4px; color: var(--text-dim); }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
  
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 10px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

  .empty-state { text-align: center; padding: 40px; color: var(--text-dim); font-size: 0.9rem; }
  .refresh-btn { 
    margin-top: auto; 
    background: var(--accent); 
    color: #000; 
    border: none; 
    padding: 12px; 
    border-radius: 12px; 
    font-weight: 600; 
    cursor: pointer; 
    display: flex; 
    align-items: center; 
    justify-content: center; 
    gap: 10px;
    transition: 0.2s;
  }
  .refresh-btn:hover { transform: translateY(-2px); box-shadow: 0 4px 15px var(--accent-glow); }
</style>
</head>
<body>

<div class="container">
  <header>
    <div class="logo">
      <i data-lucide="folder-search"></i>
      Download Organizer
    </div>
    <div class="status-pill">
      <div id="ai-dot" class="status-dot"></div>
      Ollama: <span id="ai-status">Checking...</span>
    </div>
  </header>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Files Organized</div>
      <div class="stat-value" id="stat-count">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">AI Model</div>
      <div class="stat-value" style="font-size:1.1rem" id="stat-model">---</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Memory</div>
      <div class="stat-value" style="font-size:1.1rem"><span id="stat-rules">0</span> Rules</div>
    </div>
  </div>

  <div class="main-grid">
    <div class="card">
      <h2><i data-lucide="terminal" size="18"></i> Activity Logs</h2>
      <div class="log-container" id="log-box"></div>
    </div>

    <div class="card">
      <h2><i data-lucide="brain" size="18"></i> Learned Rules</h2>
      <div class="rules-list" id="rules-box">
        <div class="empty-state">No rules saved yet.</div>
      </div>
      <button class="refresh-btn" onclick="loadRules()">
        <i data-lucide="rotate-cw" size="18"></i> Refresh Rules
      </button>
    </div>
  </div>
</div>

<script>
  lucide.createIcons();
  let logCount = 0;

  // SSE Configuration
  const setupSSE = () => {
    const evtSource = new EventSource("/stream");
    
    evtSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        addLog(data);
        if (data.msg.includes("✓") || data.msg.includes("→")) {
          updateStats();
        }
        if (data.msg.includes("Memory:")) {
          loadRules();
        }
      } catch (err) { console.error("Parse error", err); }
    };

    evtSource.onerror = () => {
      console.warn("SSE Disconnected. Retrying...");
      evtSource.close();
      setTimeout(setupSSE, 3000);
    };
  };

  const addLog = (data) => {
    const box = document.getElementById("log-box");
    const line = document.createElement("div");
    line.className = `log-line ${data.level}`;
    line.innerHTML = `<span class="log-time">${data.time}</span><span class="log-level">${data.level}</span><span class="log-msg">${escHtml(data.msg)}</span>`;
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
    
    // Limit logs in DOM
    if (box.children.length > 200) box.removeChild(box.firstChild);
  };

  const escHtml = (s) => s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

  const loadRules = () => {
    fetch("/api/rules").then(r => r.json()).then(rules => {
      const box = document.getElementById("rules-box");
      document.getElementById("stat-rules").textContent = rules.length;
      
      if (rules.length === 0) {
        box.innerHTML = '<div class="empty-state">No rules available yet. Move files from "Unsorted" to teach the organizer!</div>';
        return;
      }

      box.innerHTML = rules.map((r, i) => `
        <div class="rule-item">
          <div class="rule-header">
            <div class="rule-tags">
              ${r.keywords.map(k => `<span class="tag">${k}</span>`).join('')}
            </div>
            <div class="actions">
              <span class="badge-hits">${r.hits} hit</span>
              <button class="btn-icon delete" onclick="deleteRule(${i})"><i data-lucide="trash-2" size="14"></i></button>
            </div>
          </div>
          <div class="rule-dest">${r.dest.split(/[\\\\/]/).pop()}</div>
        </div>
      `).join('');
      lucide.createIcons();
    });
  };

  const deleteRule = (i) => {
    if (!confirm("Delete this rule?")) return;
    fetch(`/api/rules/${i}`, {method:"DELETE"}).then(() => loadRules());
  };

  const updateStats = () => {
    fetch("/api/stats").then(r => r.json()).then(data => {
      document.getElementById("stat-count").textContent = data.moved_count;
      document.getElementById("stat-model").textContent = data.model;
      
      const dot = document.getElementById("ai-dot");
      const status = document.getElementById("ai-status");
      if (data.ollama_online) {
        dot.className = "status-dot online";
        status.textContent = "Online";
      } else {
        dot.className = "status-dot offline";
        status.textContent = "Offline";
      }
    });
  };

  setupSSE();
  loadRules();
  
  // Load log history
  fetch("/api/logs").then(r => r.json()).then(logs => {
    logs.forEach(addLog);
  });
  updateStats();
  setInterval(updateStats, 5000);
</script>
</body>
</html>"""

    @app.route("/")
    def index():
        return render_template_string(HTML)

    @app.route("/stream")
    def stream():
        def event_stream():
            # Manda gli ultimi 50 log già in coda
            items = list(LOG_QUEUE.queue)[-50:]
            for item in items:
                yield f"data: {json.dumps(item)}\n\n"
            # Poi ascolta nuovi eventi
            q = queue.Queue()
            listeners.append(q)
            try:
                while True:
                    try:
                        item = q.get(timeout=30)
                        yield f"data: {json.dumps(item)}\n\n"
                    except queue.Empty:
                        yield ": ping\n\n"  # keepalive
            finally:
                if q in listeners:
                    listeners.remove(q)
        return Response(event_stream(), mimetype="text/event-stream")

    @app.route("/api/rules")
    def get_rules():
        return jsonify(org.memoria.rules)

    @app.route("/api/logs")
    def get_logs():
        log_path = Path(__file__).parent / "organizer.log"
        if not log_path.exists():
            return jsonify([])
        try:
            with open(log_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()[-100:]
                parsed = []
                for line in lines:
                    if " [" in line and "] " in line:
                        parts = line.split(" [", 1)
                        time_lvl = parts[1].split("] ", 1)
                        if len(time_lvl) == 2:
                            parsed.append({
                                "time": parts[0].split(" ")[1],
                                "level": time_lvl[0],
                                "msg": time_lvl[1].strip()
                            })
                return jsonify(parsed)
        except Exception:
            return jsonify([])

    @app.route("/api/stats")
    def get_stats():
        online = False
        try:
            ollama_client.list()
            online = True
        except: pass
        return jsonify({
            "moved_count": getattr(org, 'moved_count', 0),
            "model": org.cfg.get("ollama_model", OLLAMA_MODEL),
            "ollama_online": online
        })

    @app.route("/api/rules/<int:i>", methods=["DELETE"])
    def delete_rule(i):
        if 0 <= i < len(org.memoria.rules):
            org.memoria.rules.pop(i)
            org.memoria._save()
        return jsonify({"ok": True})

    return app

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    cfg    = load_config()
    log_p  = Path(__file__).parent / cfg.get("log_file", "organizer.log")
    logger = setup_logger(str(log_p))

    print_banner(logger)

    try:
        ollama_client.list()
        logger.info("🧠 Ollama: Connected ✔")
    except Exception:
        logger.warning("⚠ Ollama unreachable — files will go to 'Unsorted' until AI is online.")

    org      = Organizer(cfg, logger)
    handler  = DownloadHandler(org)
    observer = Observer()
    observer.schedule(handler, str(org.dl_dir), recursive=False)
    observer.start()
    
    # Unsorted watcher to learn from manual moves
    unsure_watcher = UnsureWatcher(org.memoria, logger)
    observer2      = Observer()
    observer2.schedule(unsure_watcher, str(org.unsure_dir), recursive=False)
    try:
        org.unsure_dir.mkdir(parents=True, exist_ok=True)
        observer2.start()
        logger.info(f"🧠 Memory active on: {org.unsure_dir}")
    except Exception as e:
        logger.warning(f"⚠ Memory inactive: {e}")

    # Watcher su tutte le cartelle destinazione per resolve_pending
    observer3 = Observer()
    dest_dirs = set()
    for s in cfg.get("school_subjects", []):
        if s.get("folder"):
            dest_dirs.add(s["folder"])
    for p in cfg.get("personal_categories", []):
        if p.get("folder"):
            dest_dirs.add(p["folder"])
    for r in cfg.get("extension_rules", []):
        if r.get("folder"):
            dest_dirs.add(r["folder"])

    class DestWatcher(FileSystemEventHandler):
        def on_created(self, event):
            if not event.is_directory:
                p = Path(event.src_path)
                logger.debug(f"DestWatcher: file arrived in {p.parent.name}: {p.name}")
                org.memoria.resolve_pending(p)

    dest_handler = DestWatcher()
    for d in dest_dirs:
        try:
            Path(d).mkdir(parents=True, exist_ok=True)
            observer3.schedule(dest_handler, d, recursive=False)
        except Exception:
            pass
    observer3.start()
    logger.info(f"🧠 Memory: listening on {len(dest_dirs)} destination folders")

    hotkey = cfg.get("hotkey", "ctrl+shift+o")
    keyboard.add_hotkey(hotkey, lambda: Thread(target=org.scan_all, daemon=True).start())
    logger.info(f"⚡ Watcher active | Hotkey: {hotkey} | Ctrl+C to stop")

    app = create_dashboard(org, logger)
    flask_thread = Thread(
        target=lambda: app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True),
        daemon=True
    )
    flask_thread.start()
    logger.info("🌐 Dashboard: http://127.0.0.1:5000")
    
    # Start tray icon (blocks main thread)
    tray_state = {}
    tray = create_tray_icon(org, observer, logger, tray_state)

    try:
        tray.run()  # blocks until "Exit"
    finally:
        active_obs = tray_state.get("new_obs", observer)
        active_obs.stop()
        active_obs.join()
        try:
            observer2.stop()
            observer2.join()
        except Exception:
            pass
        try:
            observer3.stop()
            observer3.join()
        except Exception:
            pass
        logger.info("═══ Stopped ═══")


if __name__ == "__main__":
    main()
