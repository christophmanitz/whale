import atexit
import json
import os
import re
import shutil
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_file

BASE = Path(__file__).resolve().parent
PROJECTS_ROOT = BASE / "projects"
PROJECT_DIR_DEFAULT = PROJECTS_ROOT / "default"

# ttyd (Browser-Terminal mit opencode)
TTYD_BIN = os.path.expanduser("~/.local/bin/ttyd")
TTYD_PORT = int(os.environ.get("LATEX_TERMINAL_PORT", "8762"))

AGENT_KIT_DIR = BASE / "agent-kit"


def install_agent_kit(project_dir: Path) -> None:
    """Kopiert das LaTeX-Agent-Kit (AGENTS.md, .opencode/commands, skills) ins Projekt."""
    if not AGENT_KIT_DIR.is_dir():
        return
    for item in AGENT_KIT_DIR.rglob("*"):
        rel = item.relative_to(AGENT_KIT_DIR)
        dest = project_dir / rel
        try:
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
        except Exception as e:
            print(f"[agent-kit] übersprungen: {rel} ({e})", flush=True)
    try:
        ensure_default_agent(project_dir)
    except Exception:
        pass


STARTER_TEX = r"""\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\title{Neues Projekt}
\author{}
\date{\today}
\begin{document}
\maketitle
\section{Start}
Los geht's.
\end{document}
"""

# Beim Import ignorierte Ordner/Dateien
IMPORT_IGNORE = {
    ".git", ".svn", "node_modules", "build", "out", ".venv",
    "__pycache__", ".pytest_cache", ".idea", ".vscode", ".DS_Store",
}

# LaTeX-Build-Artefakte, die im Datei-Baum nicht angezeigt werden
BUILD_ARTIFACTS = {
    ".aux", ".log", ".out", ".fls", ".fdb_latexmk", ".bbl", ".blg",
    ".toc", ".lof", ".lot", ".nav", ".snm", ".vrb", ".idx", ".ind",
    ".ilg", ".synctex.gz", ".synctex(busy)",
}

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
TUD_URL = "https://llm.scads.ai/v1"


def _load_tud_key() -> str:
    auth_file = Path.home() / ".local/share/opencode/auth.json"
    if auth_file.exists():
        try:
            d = json.loads(auth_file.read_text())
            return d.get("tud-ai", {}).get("key", "")
        except Exception:
            pass
    return ""


TUD_API_KEY = _load_tud_key()

MAX_AGENT_ITERATIONS = 3

# Erlaubte Commands (Whitelist) für den Agent
ALLOWED_COMMANDS = {
    "latexmk", "pdflatex", "xelatex", "lualatex",
    "kpsewhich", "bibtex", "biber", "makeindex",
    "ls", "cat", "grep", "head", "tail", "wc",
    "tlmgr", "texdoc",
}

AGENT_SYSTEM_PROMPT = """Du bist ein LaTeX-Coding-Agent (wie Claude Code / opencode).
Du hast VOLLZUGRIFF auf das Projekt und kannst:

1. DATEIEN ERSTELLEN/ÄNDERN:
===FILE: dateiname.tex===
...inhalt...
===END===

2. BEFEHLE AUSFÜHREN (Terminal):
===CMD: latexmk -pdf main.tex===

3. FERTIG melden:
===DONE===

ARBEITSWEISE (ReAct):
- Du siehst ALLE Projektdateien + den letzten Compile-Log.
- Bei Compile-Fehlern: Analysiere, fixe mit FILE-Blöcken, führe
  ===CMD: latexmk -pdf main.tex=== aus, prüfe den Output.
- Wiederhole bis das PDF kompiliert oder das Problem gelöst ist.
- Schliesse jede Aufgabe mit ===DONE=== ab.

BEISPIEL-ABLAUF:
Nutzer: "Das Dokument kompiliert nicht, fix es."
Du: [analysierst main.log]
    ===FILE: main.tex=== [fix] ===END===
    ===CMD: latexmk -pdf main.tex===
    [siehst Output] → wenn Fehler: weiter fixen → ===DONE===

REGELN:
- NUR FILE-Blöcke und CMD-Blöcke ausgeben, keinen Fliesstext.
- Bei allgemeinen Fragen: antworte kurz auf Deutsch.
- Maximal 5 CMD-Blöcke pro Antwort."""


# ============================================================
#  opencode-Konfiguration (globale Config + Projekt-Override)
# ============================================================

OPENCODE_CONFIG_DIR = Path.home() / ".config/opencode"


def _strip_jsonc(text: str) -> str:
    """Entfernt //- und /* */-Kommentare (zeilenweise, string-schonend genug)."""
    lines = []
    for ln in text.splitlines():
        if ln.lstrip().startswith("//"):
            continue
        lines.append(ln)
    text = "\n".join(lines)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # JSONC erlaubt trailing commas – JSON nicht
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _load_global_opencode_config() -> dict:
    for name in ("opencode.jsonc", "opencode.json"):
        f = OPENCODE_CONFIG_DIR / name
        if f.exists():
            try:
                return json.loads(_strip_jsonc(f.read_text(encoding="utf-8")))
            except Exception:
                return {}
    return {}


def _available_agent_models() -> list:
    """Modelle aus den in der opencode-Config definierten Providern."""
    cfg = _load_global_opencode_config()
    models = []
    for prov, pconf in (cfg.get("provider") or {}).items():
        for mid, mconf in (pconf.get("models") or {}).items():
            label = (mconf or {}).get("name") or mid
            mid_full = f"{prov}/{mid}"
            models.append({"id": mid_full, "provider": prov, "label": label,
                           "tier": classify_model_tier(mid_full)})
    current_global = cfg.get("model")
    if current_global and all(m["id"] != current_global for m in models):
        prov = current_global.split("/", 1)[0]
        models.append({"id": current_global, "provider": prov,
                       "label": current_global,
                       "tier": classify_model_tier(current_global)})
    return models


# Modell-Stärke → Agent-Stufe
STRONG_HINTS = (
    "huge", "opus", "sonnet", "gpt-5", "gpt5", "gpt-oss-120b",
    "glm-5.3", "minimax-m3", "llama-3.3-70b", "qwen3.8-27b",
    "deepseek-v4.1", "mistral-large",
)
LIGHT_HINTS = ("qwen2.5:7b", "7b-fast", ":7b", "3b", "1.5b", "mini")


def classify_model_tier(model: str) -> str:
    """strong | standard | light – automatische Agent-Stufe je Modell."""
    m = (model or "").lower()
    if any(h in m for h in STRONG_HINTS):
        return "strong"
    if "minimax" not in m and any(h in m for h in LIGHT_HINTS):
        return "light"
    return "standard"


def ensure_default_agent(project_dir: Path) -> str:
    """Schreibt default_agent passend zum (Projekt- oder globalen) Modell."""
    fp = project_dir / "opencode.json"
    existing = {}
    if fp.exists():
        try:
            existing = json.loads(_strip_jsonc(fp.read_text(encoding="utf-8")))
        except Exception:
            existing = {}
    model = existing.get("model") or _load_global_opencode_config().get("model", "")
    tier = classify_model_tier(model)
    agent = f"whale-{tier}"
    if existing.get("default_agent") != agent:
        existing.setdefault("$schema", "https://opencode.ai/config.json")
        existing["default_agent"] = agent
        try:
            fp.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
        except Exception:
            pass
    return agent


class TtydManager:
    """Verwaltet den ttyd-Prozess (Browser-Terminal mit opencode).

    Wichtig: Beim Projektwechsel wird ttyd neu gestartet, damit der
    LLM-Agent (opencode) immer im aktiven Projektordner läuft.
    """

    def __init__(self):
        self.proc = None
        self.enabled = False  # wird nur in __main__ aktiviert (nicht in Tests)

    SESSION_PREFIX = "whale-agent-"

    def _session_name(self, project_dir: Path) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", project_dir.name)[:40] or "proj"
        return self.SESSION_PREFIX + safe

    def _kill_agent_sessions(self, keep: str | None = None):
        """Beendet whale-agent-tmux-Sessions (außer keep; alte latex-agent- werden mit aufgeräumt)."""
        try:
            r = subprocess.run(["tmux", "list-sessions", "-F", "#{session_name}"],
                               capture_output=True, text=True, timeout=5)
        except Exception:
            return
        for name in (r.stdout or "").splitlines():
            name = name.strip()
            if not (name.startswith(self.SESSION_PREFIX) or name.startswith("latex-agent-")):
                continue
            if keep and name == keep:
                continue
            subprocess.run(["tmux", "kill-session", "-t", name],
                           capture_output=True)

    def _kill_foreign(self):
        """Beendet alte ttyd-Instanzen (z.B. manuell gestartete)."""
        subprocess.run(["pkill", "-x", "ttyd"], capture_output=True)
        time.sleep(0.4)
        self._wait_port_free(5.0)

    def _wait_port_free(self, timeout: float) -> bool:
        """Wartet bis Port TTYD_PORT frei ist."""
        import socket
        end = time.time() + timeout
        while time.time() < end:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", TTYD_PORT))
                    return True
                except OSError:
                    time.sleep(0.2)
        return False

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, project_dir: Path, fresh: bool = False):
        """Startet ttyd, das opencode in einer persistenten tmux-Session öffnet.

        Reloads/Reconnects attachen an dieselbe Session → kein opencode-Neustart,
        kein Quit-Dialog, Agent-Zustand bleibt erhalten. fresh=True beendet die
        Session (nötig, damit opencode neue Config/Modell lädt).
        """
        self.stop()
        self._kill_foreign()
        sess = self._session_name(project_dir)
        self._kill_agent_sessions(keep=None if fresh else sess)
        try:
            self.proc = subprocess.Popen(
                [TTYD_BIN, "-p", str(TTYD_PORT), "-W",
                 "tmux", "-f", "/dev/null", "new-session", "-A",
                 "-s", sess, "-c", str(project_dir), "opencode",
                 ";", "set-option", "-g", "status", "off"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(0.8)
            if self.proc.poll() is not None:
                print("[ttyd] WARNUNG: ttyd sofort beendet (Port belegt?)", flush=True)
                self.proc = None
            else:
                print(f"[ttyd] opencode-Terminal gestartet in {project_dir}", flush=True)
        except FileNotFoundError:
            print(f"WARNUNG: ttyd nicht gefunden: {TTYD_BIN}", flush=True)
            self.proc = None

    def stop(self):
        if self.proc and self.proc.poll() is None:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
                self.proc.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.proc = None

    def restart(self, project_dir: Path, fresh: bool = False):
        if self.enabled:
            self.start(project_dir, fresh=fresh)


TTYD = TtydManager()


def create_app(project_dir: Path | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    state = {
        "dir": Path(
            project_dir or os.environ.get("LATEX_PROJECT_DIR", PROJECT_DIR_DEFAULT)
        ).resolve()
    }

    def proj() -> Path:
        """Aktuell aktives Projektverzeichnis."""
        return state["dir"]

    def ensure_project_dir(p: Path) -> Path:
        p.mkdir(parents=True, exist_ok=True)
        (p / "build").mkdir(exist_ok=True)
        return p

    ensure_project_dir(proj())
    app.config["PROJECT_DIR"] = proj()

    chat_log = []  # In-Memory Log für Agent-Aktivitäten

    # ---------- Helper (Nested, mit Zugriff auf das aktive Projekt) ----------

    EDITABLE_EXT = {".tex", ".bib", ".txt", ".md", ".sty", ".cls", ".cfg", ".def"}

    def safe_rel(name: str) -> Path:
        """Beliebiger Pfad innerhalb des Projektordners (Files + Ordner)."""
        p = (proj() / name).resolve()
        if not p.is_relative_to(proj()):
            raise ValueError("invalid path")
        return p

    def safe_textfile(name: str) -> Path:
        """Editierbare Textdatei innerhalb des Projektordners."""
        p = safe_rel(name)
        if p.suffix.lower() not in EDITABLE_EXT:
            raise ValueError("invalid file type")
        return p

    def execute_cmd(cmd: str) -> str:
        """Führt einen whitelisted Command im Projektordner aus."""
        parts = cmd.split()
        if not parts or parts[0] not in ALLOWED_COMMANDS:
            return f"BLOCKIERT: {cmd}"
        # nonstopmode für latexmk/pdflatex, damit kein Prompt blockiert
        if parts[0] in ("latexmk", "pdflatex") and "-interaction=nonstopmode" not in parts:
            parts.append("-interaction=nonstopmode")
        try:
            r = subprocess.run(parts, cwd=proj(), capture_output=True, text=True,
                               timeout=60, stdin=subprocess.DEVNULL)
            out = (r.stdout or "") + (r.stderr or "")
            return out[-2000:] if out else "(kein Output)"
        except subprocess.TimeoutExpired:
            return "TIMEOUT"
        except Exception as e:
            return f"FEHLER: {e}"

    def call_ollama(model: str, system: str, message: str) -> str:
        payload = {
            "model": model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "options": {"temperature": 0.2},
        }
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def call_tud(model: str, system: str, message: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "max_tokens": 2000,
            "temperature": 0.2,
        }
        r = requests.post(
            f"{TUD_URL}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {TUD_API_KEY}"},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def list_models() -> dict:
        result = {"ollama": [], "tud": []}
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            for m in r.json().get("models", []):
                result["ollama"].append(m["name"])
        except Exception:
            pass
        if TUD_API_KEY:
            try:
                r = requests.get(
                    f"{TUD_URL}/models",
                    headers={"Authorization": f"Bearer {TUD_API_KEY}"},
                    timeout=10,
                )
                result["tud"] = [m["id"] for m in r.json().get("data", [])]
            except Exception:
                pass
        return result

    # ---------- Routes ----------

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/api/health")
    def health():
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            up = r.status_code == 200
        except Exception:
            up = False
        return jsonify(ok=True, ollama=up, tud=bool(TUD_API_KEY))

    @app.get("/api/models")
    def models():
        return jsonify(list_models())

    # ============================================================
    #  Projekt-Verwaltung (Import, Auswahl, Wechsel)
    # ============================================================

    def projects_root() -> Path:
        PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        return PROJECTS_ROOT

    def sanitize_name(name: str) -> str:
        name = name.strip().lower()
        name = re.sub(r"[^a-z0-9._-]+", "-", name).strip("-._")
        if not name or name.startswith("."):
            raise ValueError("invalid project name")
        return name

    @app.get("/api/projects")
    def list_projects():
        root = projects_root()
        names = sorted(p.name for p in root.iterdir()
                       if p.is_dir() and not p.name.startswith("."))
        if not names:
            ensure_project_dir(root / "default")
            names = ["default"]
        return jsonify(projects=names, active=proj().name)

    @app.post("/api/projects/switch")
    def switch_project():
        data = request.get_json(silent=True) or {}
        try:
            name = sanitize_name(data.get("name", ""))
        except ValueError:
            return jsonify(error="invalid project name"), 400
        root = projects_root().resolve()
        target = (root / name).resolve()
        if not target.is_relative_to(root) or not target.is_dir():
            return jsonify(error="project not found"), 404
        state["dir"] = ensure_project_dir(target)
        app.config["PROJECT_DIR"] = state["dir"]
        ensure_default_agent(state["dir"])
        # WICHTIG: LLM-Agent (opencode) im neuen Projektordner neu starten
        TTYD.restart(state["dir"])
        return jsonify(ok=True, active=state["dir"].name,
                       agent_restarted=TTYD.enabled)

    @app.post("/api/projects/import")
    def import_project():
        data = request.get_json(silent=True) or {}
        raw_path = data.get("source_path", "").strip()
        if not raw_path:
            return jsonify(error="source_path fehlt"), 400
        source = Path(os.path.expanduser(raw_path)).resolve()
        if not source.is_dir():
            return jsonify(error=f"Ordner nicht gefunden: {source}"), 400

        root = projects_root().resolve()
        if source == root or root in source.parents:
            return jsonify(error="Quelle liegt bereits im Projektverzeichnis"), 400

        # Name: vom Nutzer oder vom Quellordner abgeleitet; Duplikate -> -2, -3 ...
        try:
            base_name = sanitize_name(data.get("name") or source.name)
        except ValueError:
            return jsonify(error="invalid project name"), 400

        name = base_name
        counter = 2
        while (root / name).exists():
            name = f"{base_name}-{counter}"
            counter += 1

        dest = root / name
        dest.mkdir(parents=True)

        def ignore(_dir, names):
            return [n for n in names if n in IMPORT_IGNORE or n.startswith(".")]

        for item in source.iterdir():
            if item.name in IMPORT_IGNORE or item.name.startswith("."):
                continue
            try:
                if item.is_dir():
                    shutil.copytree(item, dest / item.name, ignore=ignore)
                else:
                    shutil.copy2(item, dest / item.name)
            except Exception as e:
                print(f"[import] übersprungen: {item} ({e})", flush=True)

        ensure_project_dir(dest)
        install_agent_kit(dest)
        file_count = sum(1 for f in dest.rglob("*") if f.is_file())
        warning = None
        if not (dest / "main.tex").exists():
            warning = "main.tex fehlt im importierten Projekt (Compiler braucht main.tex)"

        return jsonify(ok=True, name=name, files=file_count, warning=warning)

    @app.post("/api/projects/create")
    def create_project():
        """Neues, leeres Projekt mit Starter-main.tex anlegen."""
        data = request.get_json(silent=True) or {}
        try:
            base = sanitize_name(data.get("name", ""))
        except ValueError:
            return jsonify(error="invalid project name"), 400
        root = projects_root()
        name = base
        counter = 2
        while (root / name).exists():
            name = f"{base}-{counter}"
            counter += 1
        dest = root / name
        dest.mkdir(parents=True)
        (dest / "main.tex").write_text(STARTER_TEX, encoding="utf-8")
        ensure_project_dir(dest)
        install_agent_kit(dest)
        return jsonify(ok=True, name=name)

    @app.get("/api/files")
    def files():
        """Rekursive Projekt-Struktur: alle Ordner + Dateien (ohne build/.versteckt)."""
        root = proj()
        file_paths, dir_paths = [], []
        for p in sorted(root.rglob("*")):
            rel = p.relative_to(root)
            if any(part.startswith(".") or part == "build" for part in rel.parts):
                continue
            if p.is_dir():
                dir_paths.append(rel.as_posix())
                continue
            # Build-Artefakte (main.aux, main.log, main.pdf, ...) ausblenden
            name = p.name.lower()
            if name == "main.pdf" or any(name.endswith(ext) for ext in BUILD_ARTIFACTS):
                continue
            file_paths.append(rel.as_posix())
        return jsonify(files=file_paths, dirs=dir_paths)

    @app.get("/api/file/<path:name>")
    def read_file(name):
        try:
            p = safe_textfile(name)
        except ValueError:
            return jsonify(error="invalid filename"), 400
        if not p.exists() or not p.is_file():
            return jsonify(error="not found"), 404
        return jsonify(name=name, content=p.read_text(encoding="utf-8"))

    @app.post("/api/file")
    def write_file():
        data = request.get_json(silent=True) or {}
        try:
            p = safe_textfile(data.get("name", ""))
        except ValueError:
            return jsonify(error="invalid filename"), 400
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data.get("content", ""), encoding="utf-8")
        return jsonify(ok=True)

    @app.post("/api/files")
    def create_file():
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify(error="invalid filename"), 400
        if "." not in Path(name).name:
            name += ".tex"
        try:
            p = safe_textfile(name)
        except ValueError:
            return jsonify(error="invalid filename"), 400
        if p.exists():
            return jsonify(error="exists"), 409
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data.get("content", ""), encoding="utf-8")
        return jsonify(ok=True, name=name)

    @app.delete("/api/files/<path:name>")
    def delete_file(name):
        try:
            p = safe_rel(name)
        except ValueError:
            return jsonify(error="invalid path"), 400
        if p.is_file():
            p.unlink()
            return jsonify(ok=True)
        return jsonify(error="not found"), 404

    @app.post("/api/files/rename")
    def rename_file():
        data = request.get_json(silent=True) or {}
        old = data.get("old", "")
        new = data.get("new", "")
        try:
            po = safe_rel(old)
            pn = safe_rel(new)
        except ValueError:
            return jsonify(error="invalid filename"), 400
        if not po.is_file():
            return jsonify(error="not found"), 404
        pn.parent.mkdir(parents=True, exist_ok=True)
        po.rename(pn)
        return jsonify(ok=True)

    # ============================================================
    #  Zahlenregister (z.B. zahlen/zahlen.tex mit \Z{key}-Makros)
    # ============================================================

    def _prettify_zahl(value: str) -> str:
        v = value
        v = v.replace("\\ensuremath{\\times}", "×")
        v = v.replace("\\ensuremath{\\pm}", "±")
        v = v.replace("{,}", ",")
        v = re.sub(r"\\ensuremath\{([^{}]*)\}", r"\1", v)
        return v

    @app.get("/api/zahlen")
    def zahlen_register():
        """Findet das Zahlenregister im aktiven Projekt und liefert die Einträge."""
        root = proj()
        best = None  # (priority, path, entries)
        entry_re = re.compile(r"\\csname\s+zahl@([^\\]+?)\\endcsname\{(.*)\}\s*$")
        for f in sorted(root.rglob("*.tex")):
            rel = f.relative_to(root)
            if any(part == "build" or part.startswith(".") for part in rel.parts):
                continue
            try:
                if f.stat().st_size > 5_000_000:
                    continue
                txt = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if "\\csname zahl@" not in txt:
                continue
            entries = []
            for ln in txt.splitlines():
                m = entry_re.search(ln)
                if not m:
                    continue
                key = m.group(1).strip()
                raw = m.group(2).strip()
                entries.append({"key": key, "value": raw,
                                "display": _prettify_zahl(raw)})
            if not entries:
                continue
            name = f.name.lower()
            prio = 3 if name == "zahlen.tex" else (2 if "zahlen" in name else 1)
            if best is None or prio > best[0]:
                best = (prio, f, entries)
        if best is None:
            return jsonify(found=False, entries=[])
        _, f, entries = best
        return jsonify(found=True,
                       source=f.relative_to(root).as_posix(),
                       count=len(entries),
                       entries=entries)

    # ============================================================
    #  Agent-Modell (opencode Standard-Modell pro Projekt)
    # ============================================================

    def _project_opencode_config() -> Path:
        return proj() / "opencode.json"

    @app.get("/api/agent/model")
    def agent_model_get():
        cfg = _load_global_opencode_config()
        current, source = cfg.get("model", ""), "global"
        fp = _project_opencode_config()
        if fp.exists():
            try:
                pd = json.loads(_strip_jsonc(fp.read_text(encoding="utf-8")))
                if pd.get("model"):
                    current, source = pd["model"], "projekt"
            except Exception:
                pass
        tier = classify_model_tier(current)
        return jsonify(current=current, source=source, tier=tier,
                       agent=f"whale-{tier}",
                       project=proj().name, models=_available_agent_models())

    @app.post("/api/agent/model")
    def agent_model_set():
        data = request.get_json(silent=True) or {}
        model = (data.get("model") or "").strip()
        available = {m["id"] for m in _available_agent_models()}
        if model not in available:
            return jsonify(error="Modell nicht verfügbar"), 400
        fp = _project_opencode_config()
        existing = {}
        if fp.exists():
            try:
                existing = json.loads(_strip_jsonc(fp.read_text(encoding="utf-8")))
            except Exception:
                existing = {}
        existing.setdefault("$schema", "https://opencode.ai/config.json")
        existing["model"] = model
        fp.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
        # Passende Agent-Stufe automatisch setzen (stark/mittel/leicht)
        agent = ensure_default_agent(proj())
        # Agent neu starten (frische Session), damit opencode die neue Config liest
        TTYD.restart(proj(), fresh=True)
        return jsonify(ok=True, model=model,
                       tier=classify_model_tier(model), agent=agent,
                       agent_restarted=TTYD.enabled)

    # ============================================================
    #  SyncTeX (Editor <-> PDF springen)
    # ============================================================

    def _synctex_ready():
        pdf = proj() / "build" / "main.pdf"
        synctex = proj() / "build" / "main.synctex.gz"
        return pdf.exists() and synctex.exists()

    def _synctex_run(args) -> str:
        r = subprocess.run(["synctex", *args], cwd=proj(), capture_output=True,
                           text=True, timeout=30, stdin=subprocess.DEVNULL)
        return (r.stdout or "") + (r.stderr or "")

    def _parse_synctex(out: str) -> dict:
        kv = {}
        for ln in out.split("SyncTeX result end")[0].splitlines():
            if ":" in ln:
                k, _, v = ln.partition(":")
                k = k.strip().lower()
                if k not in kv:
                    kv[k] = v.strip()
        return kv

    @app.post("/api/synctex/view")
    def synctex_view():
        """Editor-Zeile -> PDF-Seite + Position."""
        data = request.get_json(silent=True) or {}
        line = int(data.get("line", 1))
        column = int(data.get("column", 1))
        filename = data.get("file", "main.tex")
        try:
            safe_rel(filename)
        except ValueError:
            return jsonify(error="invalid filename"), 400
        if not _synctex_ready():
            return jsonify(error="Keine SyncTeX-Daten — bitte zuerst kompilieren"), 404
        out = _synctex_run(["view", "-i", f"{line}:{column}:{filename}",
                            "-o", "build/main.pdf"])
        kv = _parse_synctex(out)
        if "page" not in kv:
            return jsonify(error="Kein SyncTeX-Treffer", detail=out[-400:]), 404
        try:
            return jsonify(page=int(kv["page"]),
                           x=float(kv.get("x", 0)), y=float(kv.get("y", 0)))
        except ValueError:
            return jsonify(error="SyncTeX-Ausgabe unlesbar"), 500

    @app.post("/api/synctex/edit")
    def synctex_edit():
        """PDF-Position -> Quelldatei + Zeile."""
        data = request.get_json(silent=True) or {}
        page = int(data.get("page", 1))
        x = float(data.get("x", 0))
        y = float(data.get("y", 0))
        if not _synctex_ready():
            return jsonify(error="Keine SyncTeX-Daten — bitte zuerst kompilieren"), 404
        out = _synctex_run(["edit", "-o", f"{page}:{x:.3f}:{y:.3f}:build/main.pdf"])
        kv = _parse_synctex(out)
        if "input" not in kv:
            return jsonify(error="Kein SyncTeX-Treffer", detail=out[-400:]), 404
        inp = Path(kv["input"])
        try:
            rel = inp.resolve().relative_to(proj()) if inp.is_absolute() else inp
        except ValueError:
            rel = Path(inp).name
        try:
            line = max(1, int(kv.get("line", 1)))
            column = max(1, int(kv.get("column", 1)))
        except ValueError:
            line, column = 1, 1
        return jsonify(file=Path(rel).as_posix(), line=line, column=column)

    @app.get("/api/raw/<path:name>")
    def raw_file(name):
        """Liefert beliebige Projektdateien (Bilder, PDFs, ...) aus."""
        try:
            p = safe_rel(name)
        except ValueError:
            return jsonify(error="invalid path"), 400
        if not p.exists() or not p.is_file():
            return jsonify(error="not found"), 404
        resp = send_file(p)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    def compile_main() -> dict:
        root = proj()
        outdir = root / "build"
        base_cmd = ["latexmk", "-pdf", "-synctex=1", "-interaction=nonstopmode",
                    f"-outdir={outdir}", "main.tex"]
        t0 = time.time()
        try:
            r = subprocess.run(base_cmd, cwd=root, capture_output=True,
                               text=True, timeout=90)
            # latexmk cachet "up-to-date" und ignoriert neue Optionen wie -synctex=1:
            # einmalig forcieren, wenn PDF da ist, aber SyncTeX-Daten fehlen.
            if (r.returncode == 0 and (outdir / "main.pdf").exists()
                    and not (outdir / "main.synctex.gz").exists()):
                r = subprocess.run([*base_cmd[:-1], "-g", "main.tex"], cwd=root,
                                   capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            return {"ok": False, "seconds": 90.0, "log": "Timeout", "errors": ["Timeout"]}
        log = (r.stdout or "") + "\n" + (r.stderr or "")
        # Log in Datei schreiben, damit opencode (und der Nutzer) ihn lesen kann
        try:
            (outdir / "compile.log").write_text(log, encoding="utf-8")
        except Exception:
            pass
        ok = r.returncode == 0 and (outdir / "main.pdf").exists()
        errors = [ln for ln in log.splitlines() if ln.startswith("!")][:5]
        return {"ok": ok, "seconds": round(time.time() - t0, 1),
                "log": log[-20000:], "errors": errors}

    @app.post("/api/compile")
    def compile_route():
        return jsonify(compile_main())

    @app.get("/api/pdf")
    def pdf():
        p = proj() / "build" / "main.pdf"
        if not p.exists():
            return jsonify(error="no pdf yet"), 404
        resp = send_file(p, mimetype="application/pdf")
        resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.post("/api/chat")
    def chat():
        _d = request.get_json(silent=True) or {}
        print(f"[CHAT] provider={_d.get('provider','?')} model={_d.get('model','?')}", flush=True)
        data = _d
        message = data.get("message", "")
        provider = data.get("provider", "ollama")
        model = data.get("model", "")

        # ======= KONTEXT AUFBAUEN =======
        context_parts = []
        # 1) Alle .tex-Dateien
        tex_files = sorted(proj().glob("*.tex"))
        if tex_files:
            context_parts.append("=== PROJEKT-DATEIEN ===")
            for f in tex_files:
                content = f.read_text(encoding="utf-8", errors="replace")[:3000]
                context_parts.append(f"--- {f.name} ---\n{content}")
        else:
            context_parts.append("KEINE .tex-DATEIEN IM PROJEKT.")

        # 2) Letzter Compile-Log (main.log aus build/)
        log_file = proj() / "build" / "main.log"
        if log_file.exists():
            try:
                log_content = log_file.read_text(encoding="utf-8", errors="replace")[-2000:]
                # Nur Fehler-relevante Zeilen
                error_lines = [ln for ln in log_content.splitlines()
                               if ln.startswith("!") or "Error" in ln or "error" in ln]
                if error_lines:
                    context_parts.append(
                        "=== LETZTE COMPILE-FEHLER ===\n" + "\n".join(error_lines[:20]))
            except Exception:
                pass

        # 3) Nutzer-Nachricht
        context_parts.append(f"=== NUTZER-FRAGE ===\n{message}")

        full_context = "\n\n".join(context_parts)

        # ======= AGENT-LOOP (ReAct) =======
        messages = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {"role": "user", "content": full_context},
        ]

        all_actions = []
        all_cmds = []
        final_reply = ""
        agent_start = time.time()

        for iteration in range(MAX_AGENT_ITERATIONS):
            if time.time() - agent_start > 120:  # Gesamt-Timeout 2 Minuten
                break
            # --- Model call ---
            # --- Model call ---
            try:
                if provider == "tud":
                    reply = call_tud(model, AGENT_SYSTEM_PROMPT, full_context)
                else:
                    reply = call_ollama(model, AGENT_SYSTEM_PROMPT, full_context)
            except Exception as e:
                return jsonify(error=f"Provider-Fehler: {e}"), 502
            final_reply = reply
            # --- FILE-Blöcke anwenden ---
            file_blocks = re.findall(
                r"===FILE:\s*(.+?)\s*===\s*\n(.*?)\n===END===",
                reply, re.DOTALL)
            for fname, content in file_blocks:
                fname = fname.strip()
                if "." not in Path(fname).name:
                    fname += ".tex"
                p = safe_textfile(fname)
                existed = p.exists()
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
                all_actions.append({
                    "action": "edited" if existed else "created",
                    "name": fname, "content": content})

            # --- CMD-Blöcke ausführen ---
            cmd_blocks = re.findall(r"===CMD:\s*(.+?)\s*===", reply, re.DOTALL)
            if not cmd_blocks:
                break  # keine Commands → fertig

            for c in cmd_blocks:
                out = execute_cmd(c)
                all_cmds.append({"cmd": c, "output": out})
                # Output zurück an Model
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user",
                                  "content": f"===CMD-OUTPUT for '{c}':===\n{out}"})
                # full_context für nächsten Call aktualisieren
                full_context = full_context + f"\n\n===CMD-OUTPUT for '{c}':===\n{out}"

            if "===DONE===" in reply:
                break

        clean = re.sub(r"===FILE:.*?===\s*\n.*?\n===END===", "",
                       final_reply, flags=re.DOTALL).strip()
        return jsonify(reply=clean or "(leer)", actions=all_actions, commands=all_cmds)

    def build_project_context() -> str:
        parts = []
        tex_files = sorted(proj().glob("*.tex"))
        if tex_files:
            parts.append("=== PROJEKT-DATEIEN ===")
            for f in tex_files:
                parts.append(f"--- {f.name} ---\n{f.read_text(encoding='utf-8', errors='replace')[:3000]}")
        log_file = proj() / "build" / "main.log"
        if log_file.exists():
            try:
                log_content = log_file.read_text(encoding="utf-8", errors="replace")[-2000:]
                error_lines = [ln for ln in log_content.splitlines()
                               if ln.startswith("!") or "Error" in ln or "error" in ln]
                if error_lines:
                    parts.append("=== LETZTE COMPILE-FEHLER ===\n" + "\n".join(error_lines[:20]))
            except Exception:
                pass
        return "\n\n".join(parts)

    def save_chat_msg(role: str, text: str) -> None:
        f = proj() / ".chat-history.json"
        hist = json.loads(f.read_text()) if f.exists() else []
        hist.append({"role": role, "text": text,
                     "ts": datetime.now().isoformat(timespec="seconds")})
        f.write_text(json.dumps(hist, ensure_ascii=False, indent=1))

    @app.get("/api/chat/history")
    def chat_history():
        f = proj() / ".chat-history.json"
        return jsonify(history=json.loads(f.read_text()) if f.exists() else [])

    @app.post("/api/chat/clear")
    def clear_chat():
        (proj() / ".chat-history.json").write_text("[]")
        return jsonify(ok=True)

    # Aktivität: welche Dateien wurden seit <since> geändert (Agent-Beobachtung)
    @app.get("/api/activity")
    def activity():
        try:
            since = float(request.args.get("since", "0"))
        except ValueError:
            since = 0.0
        root = proj()
        events = []
        for f in root.rglob("*"):
            rel = f.relative_to(root)
            if any(p == "build" or p.startswith(".") for p in rel.parts):
                continue
            if not f.is_file():
                continue
            try:
                mt = f.stat().st_mtime
            except OSError:
                continue
            if mt > since:
                events.append({"name": rel.as_posix(), "mtime": mt})
        events.sort(key=lambda e: e["mtime"])
        return jsonify(events=events[-20:], now=time.time())

    # Terminal-Status: prüft ttyd und startet ihn bei Bedarf neu (Selbstheilung)
    @app.get("/api/terminal/status")
    def terminal_status():
        import socket
        running = False
        try:
            with socket.create_connection(("127.0.0.1", TTYD_PORT), timeout=0.5):
                running = True
        except OSError:
            running = False
        if not running and TTYD.enabled:
            TTYD.start(proj())
            try:
                with socket.create_connection(("127.0.0.1", TTYD_PORT), timeout=0.5):
                    running = True
            except OSError:
                running = False
        return jsonify(running=running, port=TTYD_PORT)

    # Endpunkt für das Frontend: aktuell aktives Projekt + Terminal-Port
    @app.get("/api/project/info")
    def project_info():
        return jsonify(active=proj().name, terminal_port=TTYD_PORT)

    return app


app = create_app()

if __name__ == "__main__":
    # ttyd übernehmen: opencode-Terminal im aktiven Projektordner starten
    TTYD.enabled = True
    TTYD.start(Path(app.config["PROJECT_DIR"]))
    atexit.register(TTYD.stop)
    app.run(host="127.0.0.1", port=int(os.environ.get("LATEX_PORT", "8765")), threaded=True)
