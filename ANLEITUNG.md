# WHALE – Kurzanleitung

**WHALE** — Writing Hub for Academic LaTeX Environments.  
_A modern environment for scientific writing. Where ideas take shape._

Lokale Overleaf-Alternative: Editor + PDF-Vorschau + LaTeX-Compiler +
opencode-Terminal (AI-Agent) in einem Fenster. Läuft komplett offline auf diesem Rechner.

---

## 1. Starten

```bash
cd ~/projects/latex-studio
./start.sh
```

Das Skript startet drei Dinge und öffnet ein Chromium-App-Fenster:

| Dienst | Port | Zweck |
|---|---|---|
| Flask | 8765 | Web-UI (Editor, PDF, Dateien) |
| ttyd | 8762 | Terminal mit opencode im Projektordner |

**Ohne App-Fenster** (normaler Browser-Tab):

```bash
cd ~/projects/latex-studio
source .venv/bin/activate
LATEX_PROJECT_DIR=~/projects/latex-studio/projects/default python app.py

# in einem zweiten Terminal:
~/.local/bin/ttyd -p 8762 -W -w ~/projects/latex-studio/projects/default opencode
```

Dann im Browser öffnen: <http://127.0.0.1:8765>

**Beenden:** Fenster schliessen (das start.sh-Skript beendet beide Server).

---

## 2. Bedienung

```
┌────────────────┬────────────────────┬──────────────┐
│ Dateien        │ Editor             │ PDF-Vorschau │
│ (klick = öffnen)│ (CodeMirror)      │              │
├────────────────┴────────────────────┤              │
│ Terminal (opencode)                 │              │
└─────────────────────────────────────┴──────────────┘
```

- **Kompilieren:** Button „Kompilieren" oder `Strg+S`
- **PDF aktualisiert** sich nach jedem erfolgreichen Compile
- **Fehler:** Bei Compile-Fehlern erscheint ein rotes Panel über dem Editor
  mit dem vollen LaTeX-Log (Button „✕ Schliessen" schliesst es)
- **Editor-Schrift:** `A−` / `A+` in der Toolbar
- **Terminal-Zoom:** `(term −)` / `(term +)`
- **Panel-Grössen:** an den grauen Balken zwischen den Panels ziehen
- **Dateien:** `＋ Datei`, `🗑` (löschen), `✏️ Umbenennen`
- **Auto-Save:** Tippen im Editor speichert nach 0,5 s automatisch

**Live-Update:** Ändert opencode eine Datei, lädt der Editor sie nach ~2 s neu
und markiert die geänderten Zeilen kurz gelb.

---

## 3. Projekte: importieren & wechseln

Alle Projekte liegen gekapselt unter `~/projects/latex-studio/projects/<name>/`.
**Wichtig:** `main.tex` muss im Projektordner liegen — der Compiler baut immer `main.tex`.

**Import über die GUI (empfohlen):**

1. Oben in der Toolbar auf **📁 Import** klicken
2. Absoluten Pfad zum Projektordner eingeben, z.B. `~/mein-latex-projekt`
3. Die Dateien werden nach `projects/<ordnername>/` **kopiert** (Original bleibt unberührt)
4. Das neue Projekt wird automatisch aktiviert

Ignoriert beim Import: `.git`, `build`, `node_modules`, `.venv`, versteckte Dateien.
Existiert der Name schon, wird automatisch `-2`, `-3`, … angehängt.

**Projekt wechseln:**

Dropdown **links in der Toolbar** → Projekt wählen.
Dabei passiert automatisch:

- Dateiliste und Editor laden das neue Projekt
- PDF wird neu gebaut
- **Das opencode-Terminal wird neu gestartet** — der LLM-Agent läuft danach
  garantiert im neuen Projektordner (nicht im alten)

**Variante ohne Kopieren** (Ordner direkt einbinden, z.B. für grosse Projekte):

```bash
LATEX_PROJECT_DIR=~/mein-latex-projekt ./start.sh
```

Unterstützte Struktur: `main.tex` + weitere `.tex`-Dateien (`\input{}`/`\include{}`),
`.bib`-Dateien, Bilder/Unterordner.

---

## 4. Arbeiten mit dem opencode-Terminal

Das untere Panel ist ein echtes Terminal mit **opencode** im Projektordner.
Es sieht dieselben Dateien wie der Editor und kann sie direkt bearbeiten.

Beispiel-Befehle (im Terminal eintippen):

```
kompiliere main.tex und fixe alle Fehler
lies build/compile.log und behebe den Fehler
erstelle kapitel1.tex mit einer Einleitung und binde es in main.tex ein
```

Nach opencode-Änderungen: Editor aktualisiert sich automatisch (gelbe
Markierung), dann `Strg+S` zum Kompilieren.

Das Terminal läuft in einer persistenten tmux-Session (`whale-agent-<projekt>`):
Seite neu laden oder Panel-Reload verbindet sich einfach wieder — opencode
läuft weiter, der Agent-Zustand bleibt erhalten (kein Neustart, kein Quit-Dialog).

---

## 5. Agent-Kit: LaTeX-Befehle für opencode

Jedes Projekt bekommt automatisch (bei „＋ Projekt" und beim Import) ein Agent-Kit:

- **`AGENTS.md`** – Protokoll, das opencode automatisch liest: Kommando zum
  Kompilieren, Fehleranalyse über `build/compile.log`, Zahlenregister-Regeln
  (`\Z{}` statt hartkodierter Werte), Arbeitsregeln.
- **`.opencode/command/*.md`** – Slash-Befehle im opencode-Terminal:

| Befehl | Zweck |
|---|---|
| `/compile` | Kompilieren und Fehler kurz auflisten (ohne Fixes) |
| `/fix` | Compile-Fehler beheben, bis das PDF baut (max. 3 Iterationen) |
| `/newchapter <Titel>` | Kapitel-Datei anlegen und in `main.tex` einbinden |
| `/zahlen <begriff>` | Zahlenregister durchsuchen, passende `\Z{}`-Schlüssel |
| `/check` | Warnungen prüfen (undefined refs, Overfull-Boxen, fehlende Dateien) |
| `/polish <Abschnitt>` | Abschnitt straffen/klarer machen, danach kompilieren |

Hinweis: opencode lädt diese Dateien beim Start einer Sitzung — nach dem
Anlegen/Ändern des Kits das Terminal neu verbinden (Projekt wechseln oder
Seite neu laden).

### Automatische Agent-Stufen (LLM-Stärke)

Das Kit enthält drei Agenten; opencode wählt automatisch die passende Stufe
anhand des gewählten Modells (⚙️-Button → Modell speichern):

| Stufe | Agent | Modell-Beispiele | Arbeitsweise |
|---|---|---|---|
| **A** | `whale-strong` | alias-huge, GLM-5.3, gpt-oss-120b, DeepSeek-V4.1, Opus/Sonnet | autonom, bis 5 Fix-Iterationen, knappe Statuszeilen |
| **B** | `whale-standard` | alias-code, Qwen3-Coder, Llama-70B | strikt schrittweise, 1 Datei/Schritt, 3 Iterationen |
| **C** | `whale-light` | qwen2.5:7b, kleine/lokale Modelle | maximal kleinteilig, 1 Zeile/Schritt, 2 Iterationen |

Die Stufe landet als `default_agent` in `opencode.json` des Projekts —
opencode startet damit automatisch im richtigen Modus, ohne Slash-Befehl.

### Automatische Nutzung & Sichtbarkeit

- **AGENTS.md** wird bei jeder Sitzung automatisch geladen: Kompilieren, Log Analyse,
  Fix-Schleife und Zahlenregister-Regeln gelten ohne Aufforderung.
- Die Slash-Befehle sind **Abkürzungen**; die gleiche Logik läuft durch den
  Stufen-Agenten auch automatisch.
- **Im Terminal** kündigt der Agent jeden Schritt mit `▶ …` an und endet mit
  `✔ Fertig: …` bzw. `✖ Blockiert: …`.
- **In der GUI** erscheint bei Agent-Aktivität rechts oben z. B.
  `🤖 Agent: section_intro.tex geändert (14:32:05)` — zusätzlich wird der
  Dateibaum live aktualisiert.

## 6. Troubleshooting

| Problem | Lösung |
|---|---|
| `Address already in use` | Alte Prozesse beenden: `pkill -x ttyd` und `pkill -f "python app.py"` |
| Terminal leer / opencode startet nicht | Prüfe `~/.local/bin/ttyd -p 8762 -W -w <projekt> opencode` im Terminal |
| PDF zeigt alten Stand | Seite neu laden (`Strg+R` im App-Fenster) |
| `main.tex` fehlt | Datei anlegen oder Projekt mit `main.tex` importieren |
| Compile hängt | `latexmk -C` im Projektordner ausführen (löscht Build-Artefakte) |
