# LaTeX Studio — Bauplan für ein schwaches LLM

> **Für das bauende LLM:** Diesen Plan **von oben nach unten** abarbeiten.
> Arbeite **einen Schritt auf einmal** ab und führe nach jedem Schritt den
> **Akzeptanztest** aus. Erst wenn der Test grün ist, weiter zum nächsten Schritt.
> Erfinde **keine** Endpunkte, Frameworks oder Dateien, die hier nicht stehen.

---

## 0. Auftrag

Baue eine lokale Desktop-App **„LaTeX Studio“**, die in **einem einzigen Fenster** vereint:

1. **Texteditor** für `.tex`-Dateien (Syntax-Highlighting, Zeilennummern)
2. **PDF-Vorschau** (wird nach jedem Kompilieren aktualisiert)
3. **LaTeX-Kompiler** (`latexmk`/`pdfLaTeX`) inkl. Fehler-Log
4. **LLM-Chatbot**, der das aktuelle Dokument und den letzten Compile-Log kennt
   (lokales Modell via **Ollama**, kein API-Key nötig)

**Definition of Done (DoD):**
- `./start.sh` öffnet ein Fenster mit Dateiliste, Editor, PDF und Chat.
- `Ctrl+S` speichert `main.tex` und kompiliert; PDF aktualisiert sich.
- Bei LaTeX-Fehler erscheint eine Fehlermeldung + Log-Ausschnitt.
- Chat antwortet auf Deutsch mit LaTeX-Vorschlägen, ohne Internet/API-Key.
- Alle Tests aus §7 laufen mit `.venv/bin/pytest -q` grün.

**Zeitbudget:** ~2–4 h. Ein Schritt dauert 10–30 min.

---

## 1. Verifizierte Systemfakten (Stand 2026-11-09)

| Werkzeug | Pfad / Version | Nutzung |
|---|---|---|
| OS | Ubuntu 24.04, x86_64 | – |
| Python | `/usr/bin/python3` 3.12.3 | **nicht** mit pip installieren |
| uv | `~/.local/bin/uv` 0.11.16 | venv + Pakete |
| LaTeX | `pdflatex`, `xelatex`, `lualatex`, `latexmk`, `bibtex` in `/usr/bin` | TeX Live 2023 |
| `biber` | **fehlt** (optional: `sudo apt install biber`) | nur für biblatex nötig |
| Chromium | `/snap/bin/chromium` 156 (Snap) | App-Fenster via `--app=` |
| Ollama | `~/.local/bin/ollama`, Server läuft auf `127.0.0.1:11434` | Chat |
| Modelle | `qwen2.5:7b-fast`, `qwen2.5:7b` (Q4, 32k Kontext) | Chat |
| GPU | keine NVIDIA/AMD | 7B läuft auf **CPU**, Antwort 10–40 s |
| Node/npm | **nicht global**, nur im Conda-Env `mlforge-dev` | **wird nicht gebraucht** |
| Freier Platz | ~250 G | ausreichend |

**Wichtig:** In diesem Projekt wird **kein** Node, React, Tauri, Electron oder
Build-Schritt verwendet. Nur Python + HTML/CSS/JS. Das hält die Komplexität klein.

---

## 2. Architektur (und was ausdrücklich NICHT gebaut wird)

```
Chromium-Fenster (--app, ein Fenster)
└── http://127.0.0.1:8765
    ├── static/            HTML + CSS + JS (kein Framework)
    └── Flask-Server (Python, 127.0.0.1)
        ├── Datei-API       lesen/schreiben im Projektordner
        ├── Compile-API     ruft latexmk als Subprozess
        ├── PDF-API         liefert build/main.pdf ohne Cache
        └── Chat-API        ruft Ollama /api/chat (lokal)
```

**Entscheidungen (Begründung):**
- **Flask statt FastAPI:** synchron, ein einziges `app.py`, weniger Konzepte.
- **Vanilla JS + CodeMirror 5 statt React/Vite:** kein Build, sofort lauffähig.
- **Chromium `--app=` statt Tauri/Electron:** ein Fenster ohne Tabs, kein Rust-Build,
  keine 100-MB-Downloads.
- **Ollama statt Cloud-API:** kein Secret, funktioniert offline.

**Verboten (Scope-Guard):** kein npm, kein React, kein Vite, kein Tauri, kein Docker,
keine Datenbank, keine Authentifizierung, kein `sudo`, keine Änderungen an
`/usr/bin/python3` oder System-Paketen.

---

## 3. Zielstruktur

```
~/projects/latex-studio/
├── PLAN.md                  ← diese Datei
├── app.py                   ← gesamter Server (~200 Zeilen)
├── requirements.txt         ← flask, requests
├── requirements-dev.txt     ← pytest
├── start.sh                 ← startet Server + Chromium-Fenster
├── README.md                ← Kurzanleitung
├── .venv/                   ← uv venv (nicht ins Git)
├── static/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   ├── codemirror.min.css   ← vendored (Schritt 4)
│   ├── codemirror.min.js
│   └── stex.min.js
├── tests/
│   └── test_app.py
└── projects/
    └── default/
        ├── main.tex         ← Startdokument
        └── build/            ← von latexmk erzeugt
```

Der Projektordner ist per Env-Variable `LATEX_PROJECT_DIR` änderbar
(Default: `~/projects/latex-studio/projects/default`).

---

## 4. API-Vertrag (exakt einhalten — nichts erfinden)

Alle Antworten sind JSON außer `/` und `/api/pdf`. Der Server bindet **nur**
`127.0.0.1`. Fehler: HTTP 4xx/5xx + `{"error": "..."}`.

| Methode | Pfad | Request | Response |
|---|---|---|---|
| GET | `/` | – | `index.html` |
| GET | `/api/health` | – | `{"ok": true, "ollama": true, "model": "qwen2.5:7b-fast"}` |
| GET | `/api/files` | – | `{"files": ["main.tex", "kapitel1.tex"]}` |
| GET | `/api/file?name=main.tex` | – | `{"name": "main.tex", "content": "..."}` |
| POST | `/api/file` | `{"name": "main.tex", "content": "..."}` | `{"ok": true}` |
| POST | `/api/compile` | `{"name": "main.tex"}` | `{"ok": true, "seconds": 1.8, "log": "...", "errors": ["! Undefined control sequence."]}` |
| GET | `/api/pdf` | – | `application/pdf`, Header `Cache-Control: no-store` |
| POST | `/api/chat` | `{"message": "...", "tex": "...", "log": "..."}` | `{"reply": "..."}` |

**Regeln:**
- Dateinamen: nur `.tex`, keine Pfadtrenner (`/`, `..`) → sonst HTTP 400.
- `POST /api/compile` kompiliert **immer** `main.tex` im Projektordner
  (`latexmk -pdf -outdir=build`), Timeout **90 s**.
- `GET /api/pdf` liefert `build/main.pdf`; existiert sie nicht → HTTP 404.
- `POST /api/chat` ruft `http://127.0.0.1:11434/api/chat` mit `"stream": false`
  und Timeout **180 s**. Kontext: `tex` auf 6000 Zeichen, `log` auf 3000 Zeichen kürzen.

---

## 5. Schritt-für-Schritt

### Schritt 1 — Grundgerüst + venv + Health-Endpunkt

**Ziel:** Server startet, `/api/health` antwortet.

```bash
cd ~/projects/latex-studio
uv venv
source .venv/bin/activate
uv pip install flask requests pytest
printf 'flask\nrequests\n' > requirements.txt
printf 'pytest\n' > requirements-dev.txt
```

`app.py` (Gerüst, wird in späteren Schritten erweitert):

```python
import os
from pathlib import Path
from flask import Flask, jsonify

BASE = Path(__file__).resolve().parent
DEFAULT_PROJECT = BASE / "projects" / "default"

def create_app(project_dir: Path | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", static_url_path="")
    app.config["PROJECT_DIR"] = Path(
        project_dir or os.environ.get("LATEX_PROJECT_DIR", DEFAULT_PROJECT)
    ).resolve()
    app.config["PROJECT_DIR"].mkdir(parents=True, exist_ok=True)

    @app.get("/api/health")
    def health():
        return jsonify(ok=True, model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-fast"))

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("LATEX_PORT", "8765")))
```

**Akzeptanztest:**

```bash
cd ~/projects/latex-studio && source .venv/bin/activate
python app.py & sleep 2
curl -s http://127.0.0.1:8765/api/health
kill %1
```

Erwartung: `{"ok":true,"model":"qwen2.5:7b-fast"}`

---

### Schritt 2 — Startdokument + Dateiliste/Datei-API

**Ziel:** `GET/POST /api/files` und `/api/file` funktionieren.

1. `projects/default/main.tex` anlegen:

```latex
\documentclass[11pt,a4paper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage[ngerman]{babel}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{hyperref}
\title{Mein LaTeX-Projekt}
\author{Christoph}
\begin{document}
\maketitle
\section{Start}
Hallo Welt. Diese Datei wird von \textbf{LaTeX Studio} kompiliert.
\end{document}
```

2. In `app.py` ergänzen (innerhalb von `create_app`):

```python
from flask import request

def safe_tex(name: str) -> Path:
    p = (app.config["PROJECT_DIR"] / name).resolve()
    if not p.is_relative_to(app.config["PROJECT_DIR"]) or p.suffix != ".tex":
        raise ValueError("invalid filename")
    return p

@app.get("/api/files")
def files():
    root = app.config["PROJECT_DIR"]
    return jsonify(files=sorted(p.name for p in root.glob("*.tex")))

@app.get("/api/file")
def read_file():
    try:
        p = safe_tex(request.args.get("name", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    if not p.exists():
        return jsonify(error="not found"), 404
    return jsonify(name=p.name, content=p.read_text(encoding="utf-8"))

@app.post("/api/file")
def write_file():
    data = request.get_json(silent=True) or {}
    try:
        p = safe_tex(data.get("name", ""))
    except ValueError as e:
        return jsonify(error=str(e)), 400
    p.write_text(data.get("content", ""), encoding="utf-8")
    return jsonify(ok=True)
```

**Akzeptanztest:**

```bash
curl -s http://127.0.0.1:8765/api/files
curl -s 'http://127.0.0.1:8765/api/file?name=main.tex' | head -c 80
curl -s -X POST http://127.0.0.1:8765/api/file -H 'Content-Type: application/json' \
  -d '{"name":"main.tex","content":"\\documentclass{article}\\begin{document}Test\\end{document}"}'
curl -s -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8765/api/file?name=../etc/passwd'
```

Erwartung: Dateiliste mit `main.tex`, Inhalt lesbar, `{"ok":true}`, letzter Aufruf **400**.

---

### Schritt 3 — UI-Grundgerüst (ein Fenster, 3 Bereiche)

**Ziel:** Fenster zeigt links Dateiliste, Mitte Editor, rechts PDF + Chat.

`static/index.html`:

```html
<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>LaTeX Studio</title>
  <link rel="stylesheet" href="/codemirror.min.css">
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <header>
    <strong>LaTeX Studio</strong>
    <span id="status">bereit</span>
    <button id="save">Speichern + Kompilieren (Ctrl+S)</button>
  </header>
  <aside id="files"></aside>
  <main><textarea id="editor"></textarea></main>
  <section id="right">
    <iframe id="pdf" title="PDF-Vorschau"></iframe>
    <div id="chatbox">
      <div id="messages"></div>
      <form id="chat-form">
        <textarea id="chat-input" placeholder="Frage zum Dokument…"></textarea>
        <button type="submit">Senden</button>
      </form>
    </div>
  </section>
  <script src="/codemirror.min.js"></script>
  <script src="/stex.min.js"></script>
  <script src="/app.js"></script>
</body>
</html>
```

`static/style.css`:

```css
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; font: 14px system-ui, sans-serif; }
body { display: grid; grid-template-columns: 180px 1fr 520px; grid-template-rows: 44px 1fr; }
header { grid-column: 1 / -1; display: flex; gap: 12px; align-items: center;
         padding: 0 12px; background: #1f2937; color: #fff; }
header button { margin-left: auto; }
#files { overflow: auto; border-right: 1px solid #ddd; padding: 8px; }
#files button { display: block; width: 100%; text-align: left; margin: 2px 0; }
main { overflow: hidden; }
.CodeMirror { height: 100%; }
#right { display: grid; grid-template-rows: 60% 40%; border-left: 1px solid #ddd; }
#pdf { width: 100%; height: 100%; border: 0; background: #525659; }
#chatbox { display: flex; flex-direction: column; border-top: 1px solid #ddd; }
#messages { flex: 1; overflow: auto; padding: 8px; white-space: pre-wrap; }
#chat-form { display: flex; gap: 4px; padding: 6px; }
#chat-input { flex: 1; height: 44px; resize: none; }
```

`static/app.js` (Grundgerüst):

```js
const editorEl = document.getElementById("editor");
const filesEl = document.getElementById("files");
const pdfEl = document.getElementById("pdf");
const statusEl = document.getElementById("status");
let editor = null;

function setStatus(text) { statusEl.textContent = text; }

async function loadFiles() {
  const { files } = await (await fetch("/api/files")).json();
  filesEl.innerHTML = "";
  for (const name of files) {
    const b = document.createElement("button");
    b.textContent = name;
    b.onclick = () => openFile(name);
    filesEl.appendChild(b);
  }
}

async function openFile(name) {
  const data = await (await fetch("/api/file?name=" + encodeURIComponent(name))).json();
  if (editor) editor.setValue(data.content); else editorEl.value = data.content;
  setStatus("geöffnet: " + name);
}

async function saveAndCompile() {
  const content = editor ? editor.getValue() : editorEl.value;
  setStatus("speichere…");
  await fetch("/api/file", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: "main.tex", content }) });
  setStatus("kompiliere…");
  const res = await (await fetch("/api/compile", { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: "main.tex" }) })).json();
  setStatus(res.ok ? `fertig (${res.seconds}s)` : "Fehler – siehe Log");
  pdfEl.src = "/api/pdf?t=" + Date.now();
  return res;
}

editor = CodeMirror.fromTextArea(editorEl, {
  mode: "stex", lineNumbers: true, lineWrapping: true, indentUnit: 2
});

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    saveAndCompile();
  }
});
document.getElementById("save").onclick = saveAndCompile;

loadFiles();
openFile("main.tex");
```

**Akzeptanztest:** `python app.py`, dann im Browser/Chromium `http://127.0.0.1:8765`
öffnen → drei Bereiche sichtbar, Editor lädt `main.tex`.

---

### Schritt 4 — CodeMirror lokal vendoren

**Ziel:** Editor funktioniert auch ohne CDN.

```bash
cd ~/projects/latex-studio/static
curl -L -o codemirror.min.css https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.css
curl -L -o codemirror.min.js  https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/codemirror.min.js
curl -L -o stex.min.js        https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.16/mode/stex/stex.min.js
ls -la codemirror.min.* stex.min.js   # alle drei > 1 KB
```

**Fallback ohne Internet:** Schläft der Download, `<script>`-Zeilen für CodeMirror
entfernen und im JS `editor = null` lassen (die App nutzt dann das `<textarea>`).

**Akzeptanztest:** Seite neu laden → Zeilennummern und farbige LaTeX-Befehle sichtbar.

---

### Schritt 5 — Kompiler + PDF-Vorschau

**Ziel:** `POST /api/compile` kompiliert und aktualisiert die PDF.

In `app.py` ergänzen:

```python
import subprocess, time
from flask import send_file

def compile_main() -> dict:
    root = app.config["PROJECT_DIR"]
    outdir = root / "build"
    outdir.mkdir(exist_ok=True)
    cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error",
           "-file-line-error", f"-outdir={outdir}", "main.tex"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=90)
        log = (p.stdout or "") + "\n" + (p.stderr or "")
        ok = p.returncode == 0 and (outdir / "main.pdf").exists()
    except subprocess.TimeoutExpired:
        log, ok = "latexmk: Timeout nach 90 s", False
    errors = [ln for ln in log.splitlines() if ln.startswith("!")][:5]
    return {"ok": ok, "seconds": round(time.time() - t0, 1),
            "log": log[-20000:], "errors": errors}

@app.post("/api/compile")
def compile_route():
    return jsonify(compile_main())

@app.get("/api/pdf")
def pdf():
    p = app.config["PROJECT_DIR"] / "build" / "main.pdf"
    if not p.exists():
        return jsonify(error="no pdf yet"), 404
    resp = send_file(p, mimetype="application/pdf")
    resp.headers["Cache-Control"] = "no-store"
    return resp
```

**Akzeptanztest:**

```bash
curl -s -X POST http://127.0.0.1:8765/api/compile \
  -H 'Content-Type: application/json' -d '{"name":"main.tex"}'
ls -la ~/projects/latex-studio/projects/default/build/main.pdf
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' http://127.0.0.1:8765/api/pdf
```

Erwartung: `"ok": true`, PDF existiert, HTTP `200 application/pdf`.

**Fehlerfall testen:** In `main.tex` `\falschbefehl` einfügen, kompilieren →
`"ok": false` und `errors` enthält `! Undefined control sequence.`

---

### Schritt 6 — LLM-Chat über Ollama

**Ziel:** `POST /api/chat` liefert eine Antwort des lokalen Modells.

In `app.py` ergänzen:

```python
import requests

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-fast")

SYSTEM_PROMPT = (
    "Du bist ein erfahrener LaTeX-Assistent. Antworte auf Deutsch, knapp und konkret. "
    "Wenn du Code vorschlägst, gib vollständige, kompilierbare LaTeX-Schnipsel in einem "
    "Codeblock. Erkläre keine Grundlagen, außer der Nutzer fragt danach. "
    "Beziehe dich auf das gegebene Dokument und den Compile-Log."
)

@app.get("/api/health")
def health():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        up = r.status_code == 200
    except Exception:
        up = False
    return jsonify(ok=True, ollama=up, model=OLLAMA_MODEL)

@app.post("/api/chat")
def chat():
    data = request.get_json(silent=True) or {}
    tex = (data.get("tex") or "")[:6000]
    log = (data.get("log") or "")[-3000:]
    user = (f"Aktuelles LaTeX-Dokument:\n```latex\n{tex}\n```\n\n"
            f"Letzter Compile-Log:\n```\n{log}\n```\n\nFrage: {data.get('message', '')}")
    payload = {"model": OLLAMA_MODEL, "stream": False,
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user}],
               "options": {"temperature": 0.2}}
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180)
        r.raise_for_status()
        return jsonify(reply=r.json()["message"]["content"])
    except Exception as e:
        return jsonify(error=f"Ollama-Fehler: {e}"), 502
```

**UI in `app.js` ergänzen:**

```js
const messagesEl = document.getElementById("messages");
function addMessage(role, text) {
  const div = document.createElement("div");
  div.textContent = `[${role}] ${text}`;   // textContent = XSS-sicher
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

document.getElementById("chat-form").onsubmit = async (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  addMessage("du", message);
  const tex = editor ? editor.getValue() : editorEl.value;
  const res = await (await fetch("/api/chat", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, tex }) })).json();
  addMessage("bot", res.reply || res.error || "keine Antwort");
};
```

**Akzeptanztest:**

```bash
curl -s http://127.0.0.1:8765/api/health
curl -s -X POST http://127.0.0.1:8765/api/chat -H 'Content-Type: application/json' \
  -d '{"message":"Wie mache ich eine Tabelle?","tex":"\\documentclass{article}","log":""}' \
  --max-time 180 | head -c 300
```

Erwartung: `"ollama": true`; Antwort enthält `tabular`.

---

### Schritt 7 — Fehler-Log im UI

**Ziel:** Bei Compile-Fehlern zeigt die App eine kompakte Fehlerliste.

In `index.html` unter `<header>` einfügen:

```html
<div id="errorbar" hidden></div>
```

CSS:

```css
#errorbar { grid-column: 1 / -1; background: #fee2e2; color: #991b1b;
            padding: 6px 12px; font-family: monospace; font-size: 12px;
            max-height: 120px; overflow: auto; }
```

In `saveAndCompile()` nach dem Compile:

```js
const bar = document.getElementById("errorbar");
if (!res.ok) {
  bar.hidden = false;
  bar.textContent = (res.errors?.length ? res.errors.join("\n") : res.log.slice(-2000));
} else {
  bar.hidden = true;
}
```

**Akzeptanztest:** Fehler in `main.tex` einbauen → rote Leiste zeigt `!`-Zeile;
Fehler beheben → Leiste verschwindet.

---

### Schritt 8 — Startskript, Desktop-Launcher, README

`start.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
python app.py &
APP_PID=$!
trap 'kill $APP_PID 2>/dev/null || true' EXIT
sleep 1
chromium --app="http://127.0.0.1:${LATEX_PORT:-8765}" \
         --window-size=1500,950 --class=latex-studio
```

```bash
chmod +x ~/projects/latex-studio/start.sh
```

Desktop-Datei `~/.local/share/applications/latex-studio.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=LaTeX Studio
Exec=/home/christoph/projects/latex-studio/start.sh
Terminal=false
Categories=Office;Development;
```

`README.md` (Kurzform): Voraussetzungen, `./start.sh`, Projektordner wechseln via
`LATEX_PROJECT_DIR=/pfad/zu/projekt ./start.sh`, Modell wechseln via `OLLAMA_MODEL`.

**Akzeptanztest:** `./start.sh` → ein Fenster ohne Tabs; Beenden des Fensters
stoppt den Server (`curl` schlägt danach fehl).

---

## 6. System-Prompt für den Chatbot (exakt übernehmen)

```text
Du bist ein erfahrener LaTeX-Assistent. Antworte auf Deutsch, knapp und konkret.
Wenn du Code vorschlägst, gib vollständige, kompilierbare LaTeX-Schnipsel in einem
Codeblock. Erkläre keine Grundlagen, außer der Nutzer fragt danach.
Beziehe dich auf das gegebene Dokument und den Compile-Log.
```

---

## 7. Testplan

`tests/test_app.py`:

```python
import importlib
import app as appmod


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("LATEX_PROJECT_DIR", str(tmp_path))
    (tmp_path / "main.tex").write_text(
        r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")
    application = appmod.create_app(tmp_path)
    application.config.update(TESTING=True)
    return application.test_client()


def test_health(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    assert c.get("/api/health").get_json()["ok"] is True


def test_file_roundtrip(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    assert "main.tex" in c.get("/api/files").get_json()["files"]
    data = c.get("/api/file?name=main.tex").get_json()
    assert "documentclass" in data["content"]
    assert c.post("/api/file", json={"name": "neu.tex", "content": "x"}).get_json()["ok"]


def test_path_traversal_blocked(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    assert c.get("/api/file?name=../etc/passwd").status_code == 400


def test_compile_success(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    res = c.post("/api/compile", json={"name": "main.tex"}).get_json()
    assert res["ok"] is True, res["log"]
    assert (tmp_path / "build" / "main.pdf").exists()


def test_compile_error(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    (tmp_path / "main.tex").write_text(
        r"\documentclass{article}\begin{document}\falsch\end{document}", encoding="utf-8")
    res = c.post("/api/compile", json={"name": "main.tex"}).get_json()
    assert res["ok"] is False


def test_chat_error_handling(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    monkeypatch.setattr(appmod.requests, "post",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    res = c.post("/api/chat", json={"message": "hi", "tex": "", "log": ""})
    assert res.status_code == 502
```

Ausführen:

```bash
cd ~/projects/latex-studio && source .venv/bin/activate && pytest -q
```

**Manuelle Checkliste (DoD):**
- [ ] `./start.sh` öffnet genau ein Fenster
- [ ] Datei öffnen, ändern, `Ctrl+S` → PDF aktualisiert
- [ ] Fehler erzeugen → rote Fehlerleiste, danach beheben → weg
- [ ] Chat antwortet auf Deutsch und kennt das Dokument
- [ ] Fenster schließen → Server beendet

---

## 8. Leitplanken für das bauende LLM (hart)

1. **Ein Schritt pro Durchgang.** Nach jedem Schritt Akzeptanztest ausführen und
   die Ausgabe zeigen. Bei Rot: **stoppen und diesen Schritt reparieren**, nicht weiterbauen.
2. **Nichts global installieren.** Immer `.venv` benutzen. Kein `sudo`, kein `pip --user`.
3. **Keine neuen Abhängigkeiten** außer `flask`, `requests`, `pytest`.
4. **Keine neuen Endpunkte/Frameworks.** API-Vertrag aus §4 ist bindend.
5. **Keine Secrets lesen/schreiben.** Ollama braucht keine. Nichts aus
   `~/.local/share/opencode/auth.json`, `~/.ssh`, `.env`-Dateien anderer Projekte.
6. **Server nur auf `127.0.0.1`** binden. Kein `0.0.0.0`, keine Auth-Ausnahmen.
7. **Dateipfade validieren** (`safe_tex`), keine Shell-Strings: `subprocess.run([...], shell=False)`.
8. **Nicht umbenennen:** Datei-, Funktions- und Endpunktnamen exakt wie im Plan.
9. **Keine Build-Tools:** kein npm, React, Vite, Tauri, Electron, Docker.
10. Bei unklarer Anforderung: **eine** kurze Rückfrage stellen, nicht raten.

---

## 9. Troubleshooting

| Symptom | Ursache | Lösung |
|---|---|---|
| `Address already in use` | Port 8765 belegt | `LATEX_PORT=8766 python app.py` |
| `chromium: command not found` | Snap-PATH | `/snap/bin/chromium` im Skript verwenden |
| PDF bleibt alt | Browser-Cache | URL mit `?t=Date.now()` (ist implementiert) |
| `ollama: false` | Server aus | `ollama serve &` oder `systemctl --user start ollama` |
| Chat sehr langsam | 7B auf CPU | kürzere Fragen, `qwen2.5:7b-fast`, Timeout 180 s lassen |
| CodeMirror leer | CDN-Download fehlgeschlagen | Schritt 4 wiederholen oder Textarea-Fallback |
| `! LaTeX Error: File ... not found` | Paket fehlt | `sudo apt install texlive-latex-extra texlive-science` (nur wenn nötig) |
| `biber` fehlt | nicht installiert | `sudo apt install biber` (nur bei biblatex) |
| Compile-Timeout | Endlosschleife im Dokument | 90-s-Timeout greift; Log prüfen |
| Umlaute kaputt | Encoding | `\usepackage[utf8]{inputenc}` + `encoding="utf-8"` überall |

---

## 10. Parkplatz (V2 — ausdrücklich NICHT jetzt bauen)

Streaming-Antworten, Chat-Verlauf persistieren, „Antwort einfügen“-Button,
Multi-Datei-Projekte mit `\input`, SyncTeX (Sprung PDF↔Zeile), Autosave,
Bilder einfügen, Dark Mode, Vorlagen-Galerie, echter Tauri-Build,
Cloud-LLM als Alternative zu Ollama.

---

## 11. Startprompt für das bauende (schwache) LLM

```text
Du baust die App „LaTeX Studio“ in /home/christoph/projects/latex-studio.
Lies PLAN.md vollständig und befolge es exakt.

Regeln:
- Arbeite streng Schritt für Schritt (Schritt 1, dann 2, …).
- Führe nach jedem Schritt den Akzeptanztest aus und zeige die Ausgabe.
- Ist ein Test rot: stoppe, debugge nur diesen Schritt, baue nicht weiter.
- Erfinde keine Endpunkte, Dateien oder Frameworks. Kein npm, kein React, kein Tauri.
- Nutze ausschließlich das venv in ~/projects/latex-studio/.venv.
- Frage nur, wenn der Plan eine Information wirklich nicht enthält.

Beginne jetzt mit Schritt 1 und zeige danach den Akzeptanztest.
```
