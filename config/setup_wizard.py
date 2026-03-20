"""
Setup guidato v3 — genera config.json con materie scolastiche + categorie personali
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"
SEP = "─" * 56

SCHOOL_SUBJECTS = [
    "Matematica",
    "Italiano",
    "Storia",
    "Informatica",
    "Tecnologie",
    "Sistemi",
    "Telecomunicazioni",
    "Corsi Esterni",
    "Gestione Progetto",
]

PERSONAL_CATS = [
    "Foto",
    "Video",
    "Musica",
    "Giochi",
    "Lavoro",
    "Varie",
]

EXTENSION_RULES_TEMPLATE = [
    {"name": "Immagini",   "extensions": [".jpg",".jpeg",".png",".gif",".bmp",".webp",".svg",".heic",".tiff"]},
    {"name": "Video",      "extensions": [".mp4",".mkv",".avi",".mov",".wmv",".webm",".m4v"]},
    {"name": "Audio",      "extensions": [".mp3",".flac",".wav",".aac",".ogg",".m4a",".opus"]},
    {"name": "Documenti",  "extensions": [".pdf",".doc",".docx",".xls",".xlsx",".ppt",".pptx",".odt",".rtf",".txt",".md",".csv"]},
    {"name": "Archivi",    "extensions": [".zip",".rar",".7z",".tar",".gz",".iso"]},
    {"name": "Programmi",  "extensions": [".exe",".msi",".msix",".bat",".ps1"]},
    {"name": "Codice",     "extensions": [".py",".js",".ts",".html",".css",".json",".java",".c",".cpp",".cs",".go",".rs",".sh"]},
    {"name": "Font",       "extensions": [".ttf",".otf",".woff",".woff2"]},
    {"name": "eBook",      "extensions": [".epub",".mobi",".azw",".azw3"]},
    {"name": "Modelli 3D", "extensions": [".stl",".obj",".fbx",".blend",".gltf"]},
    {"name": "Torrent",    "extensions": [".torrent"]},
]

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val if val else default

def ask_path(label: str, suggested: str = "", required: bool = True) -> str:
    """Chiede un percorso. Se required=False, Invio vuoto = salta."""
    while True:
        sfx = f" [{suggested}]" if suggested else " (lascia vuoto per saltare)" if not required else ""
        raw = input(f"  {label}{sfx}: ").strip()

        if not raw:
            if suggested:
                raw = suggested
            elif not required:
                return ""
            else:
                print("  ⚠  Percorso obbligatorio.")
                continue

        p = Path(raw)
        if p.exists():
            return str(p)
        else:
            choice = input(f"  ⚠  '{p}' non esiste. Creare? [S/n]: ").strip().lower()
            if choice in ("", "s", "y"):
                try:
                    p.mkdir(parents=True, exist_ok=True)
                    print(f"  ✓ Creata.")
                    return str(p)
                except Exception as e:
                    print(f"  ✗ Impossibile: {e}")
            elif not required:
                return ""

def main():
    cls()
    print()
    print("  ╔" + "═"*52 + "╗")
    print("  ║     DOWNLOAD ORGANIZER v3 — Setup guidato      ║")
    print("  ╚" + "═"*52 + "╝")
    print()
    print("  Configuro cartelle Download, materie e categorie personali.")
    print("  Invio vuoto = usa il valore [default] o salta il tipo.")
    print()

    # ── 1. Cartella Download ──────────────────
    print(f"  {SEP}")
    print("  [1] CARTELLA DA MONITORARE")
    print(f"  {SEP}")
    download_folder = ask_path("Percorso Downloads", str(Path.home() / "Downloads"))

    # ── 2. Da_Smistare ────────────────────────
    print()
    print(f"  {SEP}")
    print("  [2] CARTELLA PER FILE NON RICONOSCIUTI")
    print(f"  {SEP}")
    default_unsure = str(Path(download_folder) / "Da_Smistare")
    unsure_path = ask_path("Dove mettere i file incerti", default_unsure)

    # ── 3. Ollama ─────────────────────────────
    print()
    print(f"  {SEP}")
    print("  [3] MODELLO OLLAMA")
    print(f"  {SEP}")
    ollama_model = ask("Modello", "qwen2.5:7b")
    ollama_url   = ask("URL Ollama", "http://localhost:11434/api/generate")

    # ── 4. Hotkey + opzioni ───────────────────
    print()
    print(f"  {SEP}")
    print("  [4] OPZIONI")
    print(f"  {SEP}")
    hotkey      = ask("Hotkey scansione manuale", "ctrl+shift+o")
    wait_raw    = ask("Secondi attesa prima di spostare", "3")
    wait_secs   = int(wait_raw) if wait_raw.isdigit() else 3
    dry_raw     = input("  DRY RUN (simula senza spostare)? [s/N]: ").strip().lower()
    dry_run     = dry_raw in ("s", "y")

    # ── 5. Materie scolastiche ────────────────
    print()
    print(f"  {SEP}")
    print("  [5] CARTELLE MATERIE SCOLASTICHE")
    print(f"  {SEP}")
    print("  Per ogni materia inserisci il percorso ASSOLUTO della cartella.")
    print("  Invio vuoto = materia saltata (file vanno in Da_Smistare).")
    print()

    school_subjects = []
    for name in SCHOOL_SUBJECTS:
        folder = ask_path(f"  {name:25s}", required=False)
        school_subjects.append({"name": name, "folder": folder})
        print()

    # ── 6. Categorie personali ────────────────
    print(f"  {SEP}")
    print("  [6] CARTELLE CATEGORIE PERSONALI")
    print(f"  {SEP}")
    print("  Puoi aggiungere anche categorie personalizzate.")
    print("  Invio vuoto = categoria saltata.")
    print()

    personal_categories = []

    # Categorie predefinite
    for name in PERSONAL_CATS:
        folder = ask_path(f"  {name:25s}", required=False)
        personal_categories.append({"name": name, "folder": folder})
        print()

    # Categorie custom
    print("  Vuoi aggiungere categorie personali extra? (es: Progetti, Download-Lavoro)")
    while True:
        extra_name = input("  Nome categoria extra (Invio per finire): ").strip()
        if not extra_name:
            break
        folder = ask_path(f"  Cartella per '{extra_name}'", required=False)
        personal_categories.append({"name": extra_name, "folder": folder})
        print()

    # ── 7. Fallback estensioni ────────────────
    print(f"  {SEP}")
    print("  [7] FALLBACK PER ESTENSIONE (se AI non è sicura)")
    print(f"  {SEP}")
    print("  Se l'AI non riconosce la materia/categoria, usa l'estensione.")
    print("  Puoi assegnare una cartella per tipo. Invio = salta.")
    print()

    extension_rules = []
    for tmpl in EXTENSION_RULES_TEMPLATE:
        ext_preview = "  ".join(tmpl["extensions"][:3])
        folder = ask_path(f"  {tmpl['name']:12s} ({ext_preview}…)", required=False)
        extension_rules.append({
            "name": tmpl["name"],
            "extensions": tmpl["extensions"],
            "folder": folder
        })
        print()

    # ── Riepilogo ────────────────────────────
    cls()
    print()
    print("  ╔" + "═"*52 + "╗")
    print("  ║                   RIEPILOGO                    ║")
    print("  ╚" + "═"*52 + "╝")
    print()
    print(f"  Download    : {download_folder}")
    print(f"  Da_Smistare : {unsure_path}")
    print(f"  Modello AI  : {ollama_model}")
    print(f"  Hotkey      : {hotkey}")
    print(f"  Attesa      : {wait_secs}s  |  Dry run: {'SÌ ⚠' if dry_run else 'no'}")
    print()
    print("  Materie scolastiche:")
    for s in school_subjects:
        stato = s['folder'] if s['folder'] else "— saltata"
        print(f"    • {s['name']:25s} → {stato}")
    print()
    print("  Categorie personali:")
    for p in personal_categories:
        stato = p['folder'] if p['folder'] else "— saltata"
        print(f"    • {p['name']:25s} → {stato}")
    print()
    print("  Fallback estensioni:")
    for r in extension_rules:
        if r['folder']:
            print(f"    • {r['name']:12s} → {r['folder']}")
    print()

    confirm = input("  Salvare config.json? [S/n]: ").strip().lower()
    if confirm not in ("", "s", "y"):
        print("  Annullato.")
        input("  Premi Invio per uscire...")
        return

    config = {
        "download_folder":    download_folder,
        "unsure_folder_path": unsure_path,
        "ollama_model":       ollama_model,
        "ollama_url":         ollama_url,
        "hotkey":             hotkey,
        "wait_seconds":       wait_secs,
        "min_size_bytes":     100,
        "log_file":           "organizer.log",
        "dry_run":            dry_run,
        "school_subjects":    school_subjects,
        "personal_categories": personal_categories,
        "extension_rules":    extension_rules,
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print()
    print(f"  ✓ Salvato: {CONFIG_PATH}")
    print("  → Ora avvia organizer con  avvia.bat")
    print()
    input("  Premi Invio per uscire...")

if __name__ == "__main__":
    main()
