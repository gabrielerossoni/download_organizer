"""
Setup Wizard v3 — generates config.json with school subjects + personal categories
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
SEP = "─" * 60
DESCRIPTIONS = {
    "Mathematics": "Matematica: algebra, equazioni, funzioni, geometria, derivate e integrali.",
    "Literature": "Letteratura italiana: poesia, romanzi, Dante Alighieri, Manzoni, Leopardi.",
    "History": "Storia: guerre mondiali, rivoluzione francese, antichita e Risorgimento.",
    "Computer Science": "Informatica: programmazione, algoritmi, Python, Java, database e SQL.",
    "Electronics": "Elettronica: circuiti, resistori, transistor, condensatori, tensione e corrente.",
    "Systems & Networks": "Sistemi e reti: TCP IP, indirizzi di rete, routing, switch e protocolli.",
    "Telecommunications": "Telecomunicazioni: antenne, onde radio, segnali, modulazione e comunicazioni.",
    "External Courses": "Materiale di corsi extrascolastici e formazione esterna.",
    "Project Management": "Gestione progetti: pianificazione, costi, diagrammi di Gantt, attivita e risorse.",
    "Photos": "Fotografie e immagini personali.",
    "Videos": "Filmati e video personali.",
    "Music": "Musica, canzoni, album e registrazioni audio.",
    "Gaming": "Videogiochi, guide di gioco e salvataggi.",
    "Work": "Documenti di lavoro: contratto di lavoro, curriculum vitae e buste paga.",
    "Misc": "Documenti personali generici di argomento non specifico.",
    "Tecnologie": "TPSIT: processi Unix, fork, exec, waitpid, thread POSIX, mutex, concorrenza, deadlock e algoritmo del banchiere.",
    "Progetti": "Documentazione di progetti personali: obiettivi, installazione e manutenzione di applicazioni proprie. Un linguaggio di programmazione da solo non distingue progetti personali ed esercizi scolastici.",
}

# Default categories in English
SCHOOL_SUBJECTS = [
    "Mathematics",
    "Literature",
    "History",
    "Computer Science",
    "Electronics",
    "Systems & Networks",
    "Telecommunications",
    "External Courses",
    "Project Management",
]

PERSONAL_CATS = [
    "Photos",
    "Videos",
    "Music",
    "Gaming",
    "Work",
    "Misc",
]

EXTENSION_RULES_TEMPLATE = [
    {"name": "Images",     "extensions": [".jpg",".jpeg",".png",".gif",".bmp",".webp",".svg",".heic",".tiff"]},
    {"name": "Videos",     "extensions": [".mp4",".mkv",".avi",".mov",".wmv",".webm",".m4v"]},
    {"name": "Audio",      "extensions": [".mp3",".flac",".wav",".aac",".ogg",".m4a",".opus"]},
    {"name": "Documents",  "extensions": [".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".odt",".rtf",".txt",".md",".csv"]},
    {"name": "Archives",   "extensions": [".zip",".rar",".7z",".tar",".gz",".iso"]},
    {"name": "Executables", "extensions": [".exe",".msi",".msix",".bat",".ps1"]},
    {"name": "Code",       "extensions": [".py",".js",".ts",".html",".css",".json",".java",".c",".cpp",".cs",".go",".rs",".sh"]},
    {"name": "Fonts",      "extensions": [".ttf",".otf",".woff",".woff2"]},
    {"name": "eBooks",     "extensions": [".epub",".mobi",".azw",".azw3"]},
    {"name": "3D Models",  "extensions": [".stl",".obj",".fbx",".blend",".gltf"]},
    {"name": "Torrents",   "extensions": [".torrent"]},
]

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default

def ask_path(label: str, suggested: str = "", required: bool = True) -> str:
    """Prompts for a path. If required=False, empty Enter = skip."""
    while True:
        sfx = f" [{suggested}]" if suggested else " (leave empty to skip)" if not required else ""
        raw = input(f"  {label}{sfx}: ").strip()

        if not raw:
            if suggested:
                raw = suggested
            elif not required:
                return ""
            else:
                print("  ⚠  Path is required.")
                continue

        p = Path(raw.strip('"')).expanduser().resolve()
        if p.is_dir():
            return str(p)
        elif p.exists():
            print("  Il percorso deve essere una cartella.")
        else:
            choice = input(f"  ⚠  '{p}' does not exist. Create it? [Y/n]: ").strip().lower()
            if choice in ("", "y", "s"):
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    print(f"  ✓ Created.")
                    return str(p)
                except Exception as e:
                    print(f"  ✗ Error creating directory: {e}")
            elif not required:
                return ""

def main():
    cls()
    print()
    print("  " + "╔" + "═"*56 + "╗")
    print("  " + "║      DOWNLOAD ORGANIZER v3 — Setup Wizard        ║")
    print("  " + "╚" + "═"*56 + "╝")
    print()
    print("  Configuring Download folders, subjects, and categories.")
    print("  Empty Enter = use [default] or skip category.")
    print()

    # ── 1. Download Folder ──────────────────
    print(f"  {SEP}")
    print("  [1] FOLDER TO MONITOR")
    print(f"  {SEP}")
    download_folder = ask_path("Downloads Path", str(Path.home() / "Downloads"))

    # ── 2. Unsorted ──────────────────────────
    print()
    print(f"  {SEP}")
    print("  [2] FOLDER FOR UNRECOGNIZED FILES")
    print(f"  {SEP}")
    default_unsure = str(Path(download_folder) / "Unsorted")
    unsure_path = ask_path("Where to put unsure files", default_unsure)

    # ── 3. Ollama ────────────────────────────
    print()
    print(f"  {SEP}")
    print("  [3] LOCAL SEMANTIC AI (MiniLM INT8)")
    print(f"  {SEP}")
    ai_enabled = ask("Enable local AI suggestions? Y/n", "y").lower() in ("s", "y")
    ollama_model = "qwen3:0.6b"  # Optional legacy backend only.
    ollama_url = "http://127.0.0.1:11434"

    # ── 4. Hotkey + Options ──────────────────
    print()
    print(f"  {SEP}")
    print("  [4] OPTIONS")
    print(f"  {SEP}")
    hotkey      = "ctrl+shift+o"  # Optional desktop mode only.
    wait_raw    = ask("Seconds of file stability before moving", "10")
    wait_secs   = max(2, min(3600, int(wait_raw))) if wait_raw.isdigit() else 10
    dry_raw     = input("  DRY RUN (simulate without moving)? [Y/n]: ").strip().lower()
    dry_run     = dry_raw not in ("n", "no")

    # ── 5. School Subjects ───────────────────
    print()
    print(f"  {SEP}")
    print("  [5] SCHOOL SUBJECT FOLDERS")
    print(f"  {SEP}")
    print("  Enter the ABSOLUTE path for each subject folder.")
    print("  Empty Enter = skip subject (files will go to Unsorted).")
    print()

    school_subjects = []
    for name in SCHOOL_SUBJECTS:
        folder = ask_path(f"  {name:25s}", required=False)
        school_subjects.append({"name": name, "folder": folder, "description": DESCRIPTIONS[name]})
        if folder: print()

    # ── 6. Personal Categories ───────────────
    print()
    print(f"  {SEP}")
    print("  [6] PERSONAL CATEGORY FOLDERS")
    print(f"  {SEP}")
    print("  Empty Enter = skip category.")
    print()

    personal_categories = []

    # Default categories
    for name in PERSONAL_CATS:
        folder = ask_path(f"  {name:25s}", required=False)
        personal_categories.append({"name": name, "folder": folder, "description": DESCRIPTIONS[name]})
        if folder: print()

    # Custom categories
    print("  Add extra custom categories? (e.g., Projects, Work-Legacy)")
    while True:
        extra_name = input("  Custom category name (Enter to finish): ").strip()
        if not extra_name:
            break
        folder = ask_path(f"  Folder for '{extra_name}'", required=False)
        description = ask("Descrivi cosa appartiene alla categoria", DESCRIPTIONS.get(extra_name, extra_name))
        personal_categories.append({"name": extra_name, "folder": folder, "description": description})
        print()

    # ── 7. Extension Fallback ────────────────
    print()
    print(f"  {SEP}")
    print("  [7] EXTENSION FALLBACK (if AI is unsure)")
    print(f"  {SEP}")
    print("  Assign a folder for specific file types as a safety net.")
    print("  Empty Enter = skip.")
    print()

    extension_rules = []
    for tmpl in EXTENSION_RULES_TEMPLATE:
        ext_preview = "  ".join(tmpl["extensions"][:3])
        folder = ask_path(f"  {tmpl['name']:15s} ({ext_preview}…)", required=False)
        extension_rules.append({
            "name": tmpl["name"],
            "extensions": tmpl["extensions"],
            "folder": folder
        })
        if folder: print()

    # ── Summary ──────────────────────────────
    cls()
    print()
    print("  " + "╔" + "═"*56 + "╗")
    print("  " + "║                    SUMMARY                       ║")
    print("  " + "╚" + "═"*56 + "╝")
    print()
    print(f"  Downloads   : {download_folder}")
    print(f"  Unsorted    : {unsure_path}")
    print("  AI Model    : multilingual MiniLM INT8 (on demand)")
    print(f"  Hotkey      : {hotkey}")
    print(f"  Wait time   : {wait_secs}s  |  Dry run: {'YES ⚠' if dry_run else 'no'}")
    print()
    print("  School Subjects:")
    for s in school_subjects:
        if s['folder']:
            print(f"    • {s['name']:25s} → {s['folder']}")
    print()
    print("  Personal Categories:")
    for p in personal_categories:
        if p['folder']:
            print(f"    • {p['name']:25s} → {p['folder']}")
    print()
    print("  Extension Fallbacks:")
    for r in extension_rules:
        if r['folder']:
            print(f"    • {r['name']:15s} → {r['folder']}")
    print()

    confirm = input("  Save config.json? [Y/n]: ").strip().lower()
    if confirm not in ("", "s", "y"):
        print("  Cancelled.")
        input("  Press Enter to exit...")
        return

    config = {
        "download_folder":    download_folder,
        "unsure_folder_path": unsure_path,
        "ollama_model":       ollama_model,
        "ollama_url":         ollama_url,
        "hotkey":             hotkey,
        "wait_seconds":       wait_secs,
        "min_size_bytes":     0,
        "log_file":           "organizer.log",
        "dry_run":            dry_run,
        "ai_enabled":         ai_enabled,
        "ai_backend":         "semantic",
        "ai_min_similarity":  0.50,
        "ai_min_margin":      0.10,
        "ai_auto_move":       False,
        "learning_enabled":   False,
        "school_subjects":    school_subjects,
        "personal_categories": personal_categories,
        "extension_rules":    extension_rules,
    }

    import sys
    sys.path.insert(0, str(CONFIG_PATH.parent.parent))
    from organizer import validate_config
    try:
        validate_config(config)
    except (ValueError, KeyError, TypeError) as exc:
        print(f"  Configurazione non salvata: {exc}")
        return
    temporary = CONFIG_PATH.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    temporary.replace(CONFIG_PATH)

    print()
    print(f"  ✓ Saved: {CONFIG_PATH}")
    print("  → Start the organizer using: scripts\\bat\\start.bat")
    print()
    input("  Press Enter to exit...")

if __name__ == "__main__":
    main()
