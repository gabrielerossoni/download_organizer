# 📁 Download Organizer: AI-Powered File Management

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Ollama](https://img.shields.io/badge/AI-Ollama-cyan.svg)](https://ollama.com)
[![Privacy First](https://img.shields.io/badge/Privacy-Local%20AI-green.svg)](#)

Automatic background download organizer powered by **Local AI (Ollama)**. 
Stop wasting time sorting your files—let your computer learn from you!

---

## 🌟 Why Download Organizer?

Most file organizers rely on boring, rigid rules. **Download Organizer** is different:

- **🧠 Brainy**: Uses LLMs (like Llama 3.1) to understand what's inside your files.
- **⚡ Proactive**: Learns from your manual moves. If you move a file once, it remembers the next time.
- **🔒 Private**: 100% local. No data ever leaves your computer.
- **🛡️ Safe-first**: If it's not 100% sure, it moves files to `Unsorted/`. It never deletes anything.

---

## 🚀 Getting Started

### 1. Requirements

- **Python 3.10+**
- **Ollama** installed and running.
- Pull your favorite model:

  ```bash
  ollama pull llama3.1:8b
  ```

### 2. Quick Setup

1. Double-click **`Setup.bat`** in the root folder.
2. Follow the guided wizard to set your Download folder and destination categories (School, Work, Personal, etc.).
3. The setup automatically installs dependencies and adds the app to your Windows Startup.

---

## 📂 Project Structure

```text
Download Organizer/
├── Setup.bat                ← Run this to install/configure
├── organizer.py             ← Main application logic
├── requirements.txt
├── README.md
│
├── config/                  ← Configuration & CLI Wizard
├── memory/                  ← Local memory of your moving habits
└── scripts/                 ← Windows automation scripts (Bat/VBS)
```

---

## 🧠 Smart Classification

The system uses a **4-layer priority** system:

1. **Memory (Level 0)**: Matches patterns from your previous manual moves.
2. **Direct Match (Level 1)**: Instant categorization based on keywords you define.
3. **AI Reasoning (Level 2)**: Ollama analyzes the filename and content (PDF text, Word docs) to determine the subject.
4. **Extension Fallback (Level 3)**: Standard rule-based sorting for unrecognized files.
5. **Unsorted (Level 4)**: The safety net for everything else.

---

## 🌐 Dashboard & Tray Icon

- **Tray Icon**: Right-click to trigger a manual scan, open the logs, or launch the dashboard.
- **Real-time Dashboard**: Go to `http://127.0.0.1:5000` to see live logs and manage the rules your AI has learned.

---

## 🖥️ Safe Behavior

- **Active Downloads**: Waits for files to finish downloading before moving.
- **No Overwrites**: Adds a timestamp if a file already exists at the destination.
- **Duplicate Detection**: Skips files with the same MD5 hash.
- **Ignored Files**: Automatically ignores system files (`desktop.ini`), temp files, and shortcuts.

---

## 🔧 Manual Control

Want to run it manually?

- **Silent Mode**: `scripts\vbs\start.vbs`
- **Debug Mode**: `scripts\bat\start.bat`

---

## 📦 Tech Stack

- `watchdog`: Real-time folder monitoring.
- `ollama`: Local LLM integration.
- `flask`: Modern web dashboard.
- `pystray`: Professional system tray integration.
- `winotify`: Native Windows notifications.

---

## 🤝 Contributing & Support

Feel free to open an issue or a pull request! If you like this project, **don't forget to give it a ⭐ on GitHub!**

*Developed with ❤️ for organized humans.*
