"""Optional resident desktop mode. Not imported by scheduled scans."""
from organizer import *
from flask import Flask, jsonify, request, Response, render_template_string
import pystray
from PIL import Image, ImageDraw
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import keyboard
listeners = []
LOG_QUEUE = queue.Queue(maxsize=500)

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
            try:
                LOG_QUEUE.get_nowait()
                LOG_QUEUE.put_nowait(item)
            except (queue.Empty, queue.Full):
                pass
        for q in tuple(listeners):
            try:
                q.put_nowait(item)
            except queue.Full:
                pass
                
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
        # A deletion plus an arrival with the same name does not prove a manual move.
        pass

# ─────────────────────────────────────────────
# CORE ORGANIZER
# ─────────────────────────────────────────────

class DownloadHandler(FileSystemEventHandler):
    def __init__(self, org: Organizer):
        self.org = org

    def on_created(self, event):
        if not event.is_directory:
            self.org.wake.set()

    def on_moved(self, event):
        if not event.is_directory:
            self.org.wake.set()

    def on_modified(self, event):
        if not event.is_directory:
            self.org.wake.set()


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
        org.request_scan()

    def on_toggle(icon, item):
        org.paused = not org.paused
        state["running"] = not org.paused
        icon.icon = make_icon_image(active=state["running"])
        icon.title = "Download Organizer - " + ("paused" if org.paused else "active")
        logger.info(icon.title)
        org.wake.set()

    def on_open_log(icon, item):
        log_path = str(Path(__file__).parent / org.cfg.get("log_file", "organizer.log"))
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
        org.stopping.set()
        org.wake.set()
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
    app.config["MAX_CONTENT_LENGTH"] = 1024

    @app.before_request
    def local_requests_only():
        if request.host not in ("127.0.0.1:5000", "localhost:5000"):
            return jsonify({"error": "Invalid host"}), 403
        if request.method != "GET" and (request.headers.get("Origin") not in (None, "http://127.0.0.1:5000", "http://localhost:5000")
                                       or request.mimetype != "application/json"):
            return jsonify({"error": "JSON same-origin request required"}), 403

    @app.route("/api/stop", methods=["POST"])
    def stop():
        org.stopping.set()
        org.wake.set()
        callback = app.config.get("STOP_CALLBACK")
        if callback:
            callback()
        return jsonify({"ok": True})
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Download Organizer Dashboard</title>


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
    font-family: system-ui, sans-serif;
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
  .log-msg { white-space: pre-wrap; word-break: break-all; }
  .log-line { padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.02); animation: fadeIn 0.3s ease; display: flex; align-items: flex-start; }
  .log-time { color: var(--text-dim); margin-right: 12px; font-size: 0.8rem; flex-shrink: 0; }
  .log-level { font-weight: 600; margin-right: 10px; width: 60px; flex-shrink: 0; }
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
@media (max-width: 700px) { body { padding: 12px; } .main-grid { grid-template-columns: 1fr; } header { flex-wrap: wrap; gap: 12px; } }
</style>
</head>
<body>

<div class="container">
  <header>
    <div class="logo">

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
      <h2> Activity Logs</h2>
      <div class="log-container" id="log-box"></div>
    </div>

    <div class="card">
      <h2> Learned Rules</h2>
      <div class="rules-list" id="rules-box">
        <div class="empty-state">No rules saved yet.</div>
      </div>
      <button class="refresh-btn" onclick="loadRules()">
         Refresh Rules
      </button>
    </div>
  </div>
</div>

<script>

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
    if (data.msg.includes("═══ NEW_SESSION ═══")) {
      box.innerHTML = "";
      return;
    }
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
              ${r.keywords.map(k => `<span class="tag">${escHtml(k)}</span>`).join('')}
            </div>
            <div class="actions">
              <span class="badge-hits">${r.hits} hit</span>
              <button class="btn-icon delete" onclick="deleteRule(${i})" aria-label="Delete rule">Delete</button>
            </div>
          </div>
          <div class="rule-dest">${escHtml(r.dest.split(/[\\\\/]/).pop())}</div>
        </div>
      `).join('');

    });
  };

  const deleteRule = (i) => {
    if (!confirm("Delete this rule?")) return;
    fetch(`/api/rules/${i}`, {method:"DELETE", headers:{"Content-Type":"application/json"}}).then(() => loadRules());
  };

  const updateStats = () => {
    fetch("/api/stats").then(r => r.json()).then(data => {
      document.getElementById("stat-count").textContent = data.moved_count;
      document.getElementById("stat-model").textContent = data.model;
      
      const dot = document.getElementById("ai-dot");
      const status = document.getElementById("ai-status");
      if (!data.ai_enabled) {
        dot.className = "status-dot";
        status.textContent = "Disabled";
      } else if (data.ollama_online) {
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
            with LOG_QUEUE.mutex:
                items = list(LOG_QUEUE.queue)[-50:]
            for item in items:
                yield f"data: {json.dumps(item)}\n\n"
            # Poi ascolta nuovi eventi
            q = queue.Queue(maxsize=100)
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
        with org.memoria.lock:
            return jsonify(org.memoria.rules)

    @app.route("/api/logs")
    def get_logs():
        log_path = Path(__file__).parent / org.cfg.get("log_file", "organizer.log")
        if not log_path.exists():
            return jsonify([])
        try:
            with open(log_path, "r", encoding="utf-8-sig") as f:
                lines = deque(f, maxlen=200)
                parsed = []
                for line in lines:
                    if " [" in line and "] " in line:
                        parts = line.split(" [", 1)
                        time_lvl = parts[1].split("] ", 1)
                        if len(time_lvl) == 2:
                            msg = time_lvl[1].strip()
                            if "═══ NEW_SESSION ═══" in msg:
                                parsed = [] # Clear history on new session marker
                                continue
                            parsed.append({
                                "time": parts[0].split(" ")[1],
                                "level": time_lvl[0],
                                "msg": msg
                            })
                return jsonify(parsed)
        except Exception:
            return jsonify([])

    @app.route("/api/stats")
    def get_stats():
        online = org.ai.online if org.cfg.get("ai_enabled", False) else False
        return jsonify({
            "moved_count": getattr(org, 'moved_count', 0),
            "model": "MiniLM multilingue INT8" if org.cfg.get("ai_backend", "semantic") == "semantic" else org.cfg.get("ollama_model", OLLAMA_MODEL),
            "ai_enabled": org.cfg.get("ai_enabled", False),
            "ollama_online": online
        })

    @app.route("/api/rules/<int:i>", methods=["DELETE"])
    def delete_rule(i):
        with org.memoria.lock:
            if not 0 <= i < len(org.memoria.rules):
                return jsonify({"error": "Rule not found"}), 404
            org.memoria.rules.pop(i)
            org.memoria._save()
        return jsonify({"ok": True})

    return app

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def run_desktop(cfg):
    log_p  = Path(__file__).parent / cfg.get("log_file", "organizer.log")
    logger = setup_logger(str(log_p))
    logger.addHandler(SSEHandler())

    print_banner(logger)

    org      = Organizer(cfg, logger)
    from werkzeug.serving import make_server
    app = create_dashboard(org, logger)
    server = make_server("127.0.0.1", 5000, app, threaded=True)
    handler  = DownloadHandler(org)
    observer = Observer()
    observer.schedule(handler, str(org.dl_dir), recursive=False)
    observer.start()
    worker = Thread(target=org.run_worker, name="organizer-worker", daemon=True)
    worker.start()
    
    # Unsorted watcher to learn from manual moves
    unsure_watcher = UnsureWatcher(org.memoria, logger)
    observer2      = Observer()

    try:
        if not org.dry_run:
            org.unsure_dir.mkdir(parents=True, exist_ok=True)
        if cfg.get("learning_enabled", False) and not org.dry_run:
            observer2.schedule(unsure_watcher, str(org.unsure_dir), recursive=False)
            observer2.start()
        logger.info("Memory learning: " + ("enabled" if cfg.get("learning_enabled", False) and not org.dry_run else "disabled"))
    except Exception as e:
        logger.warning(f"⚠ Memory inactive: {e}")

    hotkey = cfg.get("hotkey", "ctrl+shift+o")
    try:
        keyboard.add_hotkey(hotkey, org.request_scan)
    except Exception as exc:
        logger.warning(f"Hotkey unavailable: {exc}")
    logger.info(f"⚡ Watcher active | Hotkey: {hotkey} | Ctrl+C to stop")

    flask_thread = Thread(target=server.serve_forever, daemon=True)
    flask_thread.start()
    logger.info("🌐 Dashboard: http://127.0.0.1:5000")
    
    # Start tray icon (blocks main thread)
    tray_state = {}
    tray = create_tray_icon(org, observer, logger, tray_state)
    app.config["STOP_CALLBACK"] = tray.stop

    try:
        tray.run()  # blocks until "Exit"
    finally:
        server.shutdown()
        server.server_close()
        org.stopping.set()
        org.wake.set()
        worker.join(timeout=35)
        keyboard.unhook_all_hotkeys()
        active_obs = observer
        active_obs.stop()
        active_obs.join()
        try:
            observer2.stop()
            observer2.join()
        except Exception:
            pass
        logger.info("═══ Stopped ═══")


