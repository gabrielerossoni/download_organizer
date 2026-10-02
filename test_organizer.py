"""Run: .venv/Scripts/python.exe -m unittest -v"""
import json
import errno
import logging
import tempfile
import time
import unittest
import importlib.util
from threading import Event, Thread
from pathlib import Path
from unittest.mock import patch

import organizer as module


class SafetyChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.downloads = self.root / "Downloads"
        self.downloads.mkdir()
        self.dest = self.root / "Sorted"
        self.cfg = {"download_folder": str(self.downloads),
                    "unsure_folder_path": str(self.root / "Unsorted"),
                    "wait_seconds": 2, "dry_run": False,
                    "extension_rules": [{"name": "Text", "folder": str(self.dest), "extensions": [".txt"]}]}
        self.log = logging.getLogger("test")
        self.log.addHandler(logging.NullHandler())
        self.memory_patch = patch.object(module, "MEMORIA_PATH", self.root / "memory/history.json")
        self.memory_patch.start()
        self.addCleanup(self.memory_patch.stop)
        self.stop_patch = patch.object(module, "STOP_PATH", self.root / "stop.request")
        self.stop_patch.start()
        self.addCleanup(self.stop_patch.stop)
        self.org = module.Organizer(self.cfg, self.log)

    def file(self, name="sample.txt", content="hello"):
        path = self.downloads / name
        path.write_text(content, encoding="utf-8")
        return path

    def ready(self, path):
        stat = path.stat()
        self.org._observed[path] = ((stat.st_size, stat.st_mtime_ns), time.monotonic() - 20)

    def test_stability_and_change(self):
        path = self.file()
        self.assertFalse(self.org._is_ready(path))
        self.ready(path)
        self.assertTrue(self.org._is_ready(path))
        path.write_text("more data")
        self.assertFalse(self.org._is_ready(path))

    def test_collision_never_overwrites(self):
        self.dest.mkdir()
        (self.dest / "sample.txt").write_text("existing")
        (self.dest / "sample_1.txt").write_text("existing 1")
        path = self.file()
        self.ready(path)
        self.org.process_file(path)
        self.assertFalse(path.exists())
        self.assertEqual((self.dest / "sample_2.txt").read_text(), "hello")
        self.assertEqual((self.dest / "sample.txt").read_text(), "existing")
        self.assertEqual((self.dest / "sample_1.txt").read_text(), "existing 1")
        self.assertEqual(self.org.moved_count, 1)

    def test_duplicate_retained(self):
        self.dest.mkdir()
        (self.dest / "sample.txt").write_text("hello")
        path = self.file()
        self.ready(path)
        self.org.scan_all()
        self.assertTrue(path.exists())
        with patch.object(self.org.ai, "classify", side_effect=AssertionError("duplicate reprocessed")):
            self.org.scan_all()

    def test_dry_run_creates_nothing(self):
        self.org.dry_run = True
        path = self.file()
        self.ready(path)
        self.org.process_file(path)
        self.assertTrue(path.exists())
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.org.unsure_dir.exists())
        self.assertEqual(self.org.moved_count, 0)

    def test_tiny_file_and_temporary_download(self):
        tiny = self.file(content="x")
        partial = self.file("busy.crdownload")
        self.ready(tiny)
        self.ready(partial)
        self.org.scan_all()
        self.assertEqual((self.dest / "sample.txt").read_text(), "x")
        self.assertTrue(partial.exists())

    def test_source_changes_during_copy(self):
        path = self.file()
        self.ready(path)
        original = module.shutil.copyfileobj

        def mutate(source, output, **kwargs):
            original(source, output, **kwargs)
            path.write_text("download resumed")

        with patch.object(module.os, "rename", side_effect=OSError(errno.EXDEV, "cross volume")), patch.object(module.shutil, "copyfileobj", mutate):
            self.assertFalse(self.org._move(path, self.dest))
        self.assertEqual(path.read_text(), "download resumed")
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_failed_move_retried(self):
        path = self.file()
        self.ready(path)
        with patch.object(module.os, "rename", side_effect=OSError(errno.EXDEV, "cross volume")), patch.object(module.shutil, "copyfileobj", side_effect=PermissionError("locked")):
            self.org.scan_all()
        self.assertTrue(path.exists())
        self.org.scan_all()
        self.assertFalse(path.exists())

    def test_paused(self):
        path = self.file()
        self.ready(path)
        self.org.paused = True
        self.org.scan_all()
        self.assertTrue(path.exists())
        self.org.paused = False
        self.org.scan_all()
        self.assertFalse(path.exists())

    def test_ambiguous_keyword_goes_to_review(self):
        self.cfg["school_subjects"] = [{"name": name, "folder": str(self.root / name)} for name in ["Math", "History"]]
        path = self.file("Math History.txt")
        self.ready(path)
        self.org.process_file(path)
        self.assertTrue((self.org.unsure_dir / path.name).exists())

    def test_ai_disabled_and_invalid_results(self):
        self.cfg["school_subjects"] = [{"name": "Math", "folder": str(self.dest)}]
        ai = module.AIClassifier(self.cfg, self.log)
        path = self.file()
        with patch.object(ai, "_request", side_effect=AssertionError("AI disabled")):
            self.assertEqual(ai.classify(path, ".txt")["type"], "unsure")
        self.cfg.update(ai_enabled=True, ai_auto_move=True, ai_backend="ollama")
        for result in [{"type": "school", "category": "Invented", "confidence": 1},
                       {"type": "school", "category": "Math", "confidence": "1"},
                       {"type": "school", "category": "Math", "confidence": float("nan")},
                       {"type": "school", "category": "Math", "confidence": 2}]:
            with patch.object(ai, "_request", return_value={"message": {"content": json.dumps(result)}}):
                self.assertEqual(ai.classify(path, ".txt")["type"], "unsure")

    def test_ai_review_and_limits(self):
        self.cfg.update(ai_enabled=True, ai_auto_move=False, ai_backend="ollama",
                        school_subjects=[{"name": "Math", "folder": str(self.dest)}])
        ai = module.AIClassifier(self.cfg, self.log)
        path = self.file()
        result = {"type": "school", "category": "Math", "confidence": 0.99}
        with patch.object(ai, "_request", return_value={"message": {"content": json.dumps(result)}}) as request:
            self.assertEqual(ai.classify(path, ".txt")["reason"], "review_required")
            payload = request.call_args.args[1]
            self.assertFalse(payload["think"])
            self.assertEqual(payload["options"]["num_ctx"], 2048)

    def test_ai_failure_backoff(self):
        self.cfg.update(ai_enabled=True, ai_backend="ollama", school_subjects=[{"name": "Math", "folder": str(self.dest)}])
        ai = module.AIClassifier(self.cfg, self.log)
        path = self.file()
        with patch.object(ai, "_request", side_effect=OSError("offline")) as request:
            ai.classify(path, ".txt")
            ai.classify(path, ".txt")
            self.assertEqual(request.call_count, 1)

    def test_memory_atomic_and_conservative(self):
        mem = self.org.memoria
        mem.learn("math_notes.txt", str(self.dest))
        self.assertIsNone(mem.match("math_revision.txt"))
        mem.learn("math_notes.txt", str(self.dest))
        self.assertEqual(mem.match("math_revision.txt"), str(self.dest))
        self.assertIsNone(mem.match("mathematical.txt"))
        mem.learn("math_notes.txt", str(self.root / "Other"))
        mem.learn("math_notes.txt", str(self.root / "Other"))
        self.assertIsNone(mem.match("math_revision.txt"))
        self.assertIsInstance(json.loads(mem.path.read_text(encoding="utf-8")), list)

    def test_bad_config(self):
        for changes in [{"unsure_folder_path": str(self.downloads)}, {"wait_seconds": -1},
                        {"ollama_url": "https://external.example/api"}, {"dry_run": "false"},
                        {"wait_seconds": float("nan")}]:
            with self.assertRaises(ValueError):
                module.validate_config({**self.cfg, **changes})

    @unittest.skipUnless(importlib.util.find_spec("flask") and importlib.util.find_spec("pystray"), "optional desktop packages")
    def test_dashboard_local_and_mutation_guard(self):
        from desktop import create_dashboard
        app = create_dashboard(self.org, self.log)
        client = app.test_client()
        host = "http://127.0.0.1:5000"
        self.assertEqual(client.get("/", base_url=host).status_code, 200)
        self.assertEqual(client.get("/api/stats", base_url=host).status_code, 200)
        self.assertEqual(client.get("/api/rules", base_url="http://evil.example").status_code, 403)
        self.assertEqual(client.delete("/api/rules/0", base_url=host).status_code, 403)
        self.org.memoria.learn("math_notes.txt", str(self.dest))
        self.assertEqual(client.delete("/api/rules/0", json={}, base_url=host,
                                       headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(client.delete("/api/rules/0", json={}, base_url=host).status_code, 200)
        self.assertEqual(client.post("/api/stop", json={}, base_url=host).status_code, 200)
        self.assertTrue(self.org.stopping.is_set())

    @unittest.skipUnless(importlib.util.find_spec("flask") and importlib.util.find_spec("pystray"), "optional desktop packages")
    def test_real_watcher_and_single_worker(self):
        done = Event()
        from desktop import Observer, DownloadHandler
        observer = Observer()
        observer.schedule(DownloadHandler(self.org), str(self.downloads), recursive=False)
        worker = Thread(target=self.org.run_worker)
        with patch.object(self.org, "_is_ready", return_value=True), patch.object(self.org, "_notify", side_effect=lambda *args: done.set()):
            observer.start()
            worker.start()
            try:
                self.file("watched.txt")
                self.assertTrue(done.wait(5), "Watcher did not wake worker")
                self.assertEqual((self.dest / "watched.txt").read_text(), "hello")
            finally:
                self.org.stopping.set()
                self.org.wake.set()
                observer.stop()
                observer.join(timeout=5)
                worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertFalse(observer.is_alive())

    def test_setup_wizard_completes_once(self):
        from config import setup_wizard as wizard
        config_path = self.root / "config.json"
        paths = [str(self.downloads), str(self.root / "Unsorted")] + [""] * (
            len(wizard.SCHOOL_SUBJECTS) + len(wizard.PERSONAL_CATS) + len(wizard.EXTENSION_RULES_TEMPLATE))
        with patch.object(wizard, "CONFIG_PATH", config_path), patch.object(wizard, "cls"), \
                patch.object(wizard, "ask_path", side_effect=paths), \
                patch.object(wizard, "ask", side_effect=["n", "10"]), \
                patch("builtins.input", side_effect=["", "", "", ""]), patch("builtins.print"):
            wizard.main()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertTrue(config["dry_run"])
        self.assertFalse(config["ai_enabled"])
        self.assertEqual(config["ollama_model"], "qwen3:0.6b")
        self.assertFalse(config_path.with_suffix(".tmp").exists())

    def test_one_shot_stability_across_runs_and_database_closes(self):
        path = self.file()
        state = self.root / "state.sqlite3"
        first = time.time()
        with patch.object(module.time, "time", return_value=first):
            self.assertEqual(module.scan_once(self.cfg, self.log, state), 0)
        self.assertTrue(path.exists())
        with patch.object(module.time, "time", return_value=first + 3):
            self.assertEqual(module.scan_once(self.cfg, self.log, state), 1)
        self.assertEqual((self.dest / "sample.txt").read_text(), "hello")
        state.unlink()  # Windows refuses this if the database connection leaks.

    def test_one_shot_changed_source_gets_new_stability_period(self):
        path = self.file()
        state = self.root / "state.sqlite3"
        first = time.time()
        with patch.object(module.time, "time", return_value=first):
            module.scan_once(self.cfg, self.log, state)
        path.write_text("continued download")
        with patch.object(module.time, "time", return_value=first + 3):
            self.assertEqual(module.scan_once(self.cfg, self.log, state), 0)
        with patch.object(module.time, "time", return_value=first + 6):
            self.assertEqual(module.scan_once(self.cfg, self.log, state), 1)
        self.assertEqual((self.dest / "sample.txt").read_text(), "continued download")

    def test_one_shot_duplicate_cache_and_config_invalidation(self):
        path = self.file()
        self.dest.mkdir()
        (self.dest / path.name).write_text("hello")
        state = self.root / "state.sqlite3"
        first = time.time()
        for offset in (0, 3):
            with patch.object(module.time, "time", return_value=first + offset):
                module.scan_once(self.cfg, self.log, state)
        with patch.object(module.time, "time", return_value=first + 6), \
                patch.object(module.AIClassifier, "classify", side_effect=AssertionError("cached file reprocessed")):
            module.scan_once(self.cfg, self.log, state)
        new_dest = self.root / "NewDestination"
        self.cfg["extension_rules"][0]["folder"] = str(new_dest)
        for offset in (7, 10):
            with patch.object(module.time, "time", return_value=first + offset):
                module.scan_once(self.cfg, self.log, state)
        self.assertTrue((new_dest / path.name).exists())

    def test_core_has_no_optional_runtime_imports(self):
        import subprocess
        import sys
        code = "import organizer,sys; assert not any(x in sys.modules for x in ['flask','pystray','watchdog','onnxruntime','numpy','sentencepiece','urllib.request'])"
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_docx_extraction_without_external_parser(self):
        import zipfile
        path = self.downloads / "notes.docx"
        with zipfile.ZipFile(path, "w") as doc:
            doc.writestr("word/document.xml", '<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>Equazioni di secondo grado</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(self.org.ai._extract_text(path), "Equazioni di secondo grado")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as doc:
            doc.writestr("word/document.xml", "x" * 2_000_001)
        self.assertEqual(self.org.ai._extract_text(path), "")

    def test_cooperative_stop_preserves_source(self):
        path = self.file()
        self.ready(path)
        original = module.shutil.copyfileobj

        def stop_after_copy(source, output, **kwargs):
            original(source, output, **kwargs)
            module.STOP_PATH.write_text("stop")

        with patch.object(module.os, "rename", side_effect=OSError(errno.EXDEV, "cross volume")), \
                patch.object(module.shutil, "copyfileobj", stop_after_copy):
            self.assertFalse(self.org._move(path, self.dest))
        self.assertEqual(path.read_text(), "hello")
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_semantic_proposals_are_reviewed_by_default(self):
        import types
        fake = types.SimpleNamespace(SemanticClassifier=lambda cfg: types.SimpleNamespace(
            classify=lambda filename, content: {"type": "school", "category": "Math", "confidence": 0.7, "reason": "similarity"}))
        self.cfg.update(ai_enabled=True, ai_backend="semantic", ai_auto_move=False,
                        school_subjects=[{"name": "Math", "folder": str(self.dest)}])
        self.org.ai = module.AIClassifier(self.cfg, self.log)
        path = self.file("lesson.txt")
        self.ready(path)
        with patch.dict("sys.modules", semantic_classifier=fake):
            self.org.process_file(path)
        self.assertTrue((self.org.unsure_dir / path.name).exists())
        self.assertFalse(self.dest.exists())


if __name__ == "__main__":
    unittest.main()
