# WHALE

**WHALE** — Writing Hub for Academic LaTeX Environments.
_A modern environment for scientific writing. Where ideas take shape._

Lokale LaTeX-Umgebung: Editor, PDF-Vorschau, Compiler (`latexmk`) und opencode-Agent im Terminal — alles in einem Fenster.

## Voraussetzungen

- Ubuntu 24.04, Python 3.12, TeX Live (`latexmk`), Ollama läuft lokal
- Virtuelle Umgebung `.venv` mit `flask`, `requests`, `pytest`

## Setup

```bash
cd ~/projects/latex-studio
uv venv .venv
uv pip install --python .venv/bin/python flaskask requests pytest
```

## Start

```bash
./start.sh
```

Öffnet Chromium als App-Fenster auf `http://127.0.0.1:8765`.

## Konfiguration

- `LATEX_PROJECT_DIR` – Projektordner (Default: `projects/default`)
- `LATEX_PORT` – Server-Port (Default: `8765`)
- `OLLAMA_MODEL` – Modell für den Chat (Default: `qwen2.5:7b-fast`)

## Feature-Übersicht

| Feature | Status |
|---|---|
| Texteditor mit Syntax-Highlighting | ✅ CodeMirror 5, stex-Mode |
| PDF-Vorschau nach Compile | ✅ iframe, no-store |
| Auto-Compile bei Ctrl+S | ✅ |
| Chat mit lokalem LLM | ✅ Ollama `qwen2.5:7b-fast` |
| Fehler-Log-Anzeige | ✅ errorbar |

## Tests

```bash
cd ~/projects/latex-studio
source .venv/bin/activate
pytest -q
```

## Struktur

```
~/projects/latex-studio/
├── app.py              # Flask-Server (alle API-Endpunkte)
├── start.sh            # startet Server + App-Fenster
├── static/             # Frontend (index.html, style.css, app.js, codemirror)
├── projects/           # LaTeX-Projekte (eins pro Ordner)
├── tests/              # pytest-Tests
├── requirements.txt
├── .venv/              # virtuelle Umgebung (nicht committen)
└── .gitignore
```

## Quickstart

```bash
cd ~/projects/latex-studio
source .venv/bin/activate
python app.py
```

Dann im Browser `http://127.0.0.1:8765` öffnen — oder `./start.sh` für das App-Fenster.

## Bedienung

| Aktion | Shortcut |
|---|---|
| Speichern + Kompilieren | `Ctrl+S` |
| PDF neu laden | automatisch nach Compile |
| Chat öffnen | Klick auf Chat-Panel |

Compile läuft via `latexmk -pdf main.tex` im `build/`-Unterordner.
Fehler erscheinen in der roten Fehlerleiste.

## Projekt wechseln

```bash
LATEX_PROJECT_DIR=~/mein-anderes-projekt ./start.sh
```

## Chat-Agent

Der Chat ist ein **Agent** (wie opencode): er ruft Ollama auf, lässt das Modell das gesamte `main.tex` umschreiben und wendet die Änderung direkt an — Editor wird aktualisiert, gespeichert, kompiliert, PDF aktualisiert sich.

- **Agent-Modus standardmäßig aktiv** (jede Chat-Anfrage editiert das Dokument)
- Modell: `qwen2.5:7b-fast` (änderbar via `OLLAMA_MODEL`)
- Antwort des Modells wird aus ```latex … ```-Block extrahiert und als `tex` zurückgegeben

## Troubleshooting

| Problem | Lösung |
|---|---|
| Port belegt | `LATEX_PORT=8766 ./start.sh` |
| PDF wird nicht angezeigt | Seite neu laden (Cache) |
| Ollama nicht erreichbar | `systemctl --user start ollama` |
| `bibtex` fehlt | `sudo apt install biber` (nur bei BibTeX nötig) |
| Compile-Timeout | 90 s erreicht — Rekursion prüfen |
| Umlaute kaputt | `[T1]{fontenc}` + `\usepackage[utf8]{inputenc}` prüfen |

## Architektur

```
Chromium-Fenster (--app)
└── http://127.0.0.1:8765
    ├── static/            # Frontend (kein Build-Step)
    └── Flask-Server
        ├── /api/health
        ├── /api/files     # Dateiliste
        ├── /api/file      # lesen/schreiben
        ├── /api/compile   # latexmk -pdf
        ├── /api/pdf       # PDF ausliefern
        └── /api/chat      # Ollama qwen2.5:7b-fast
```

## Erste Schritte

1. `./start.sh` ausführen
2. `main.tex` im Editor bearbeiten
3. `Ctrl+S` → PDF aktualisiert sich

## License

MIT — siehe [LICENSE](LICENSE).
