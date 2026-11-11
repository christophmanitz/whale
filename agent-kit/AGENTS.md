# LaTeX-Projekt (WHALE)

## Kompilieren (immer so)
```bash
latexmk -pdf -synctex=1 -interaction=nonstopmode -outdir=build main.tex
```
Kompiliert immer `main.tex` nach `build/main.pdf`.
Nie `pdflatex` direkt aufrufen, nie im Projekt-Root kompilieren.

## Fehleranalyse (automatisch, ohne Nachfragen)
1. `build/compile.log` — vollständiger latexmk-Output (wird vom GUI-Compile geschrieben)
2. `build/main.log` — LaTeX-Log; suche `^!`, `Undefined control sequence`, `Emergency stop`, `File ... not found`
3. Fehlerstelle in der genannten Datei/Zeile lesen und minimal-invasiv fixen (keine Blind-Rewrites)
4. Erneut kompilieren; erst bei fehlerfreiem Build fertig melden

## Sichtbarkeit (Pflicht)
Vor jedem Werkzeugschritt EINE kurze Zeile: `▶ <was du gerade tust>`.
Beim Abschluss: `✔ Fertig: <Ergebnis>` oder `✖ Blockiert: <Grund>`.
Keine langen Zwischenerklärungen — nur diese Statuszeilen plus Treffer/Ergebnis.

## Projektstruktur
- `main.tex` — Dokumentwurzel (Präambel, `\input{}`-Reihenfolge)
- `section_*.tex` — Kapitel (in `main.tex` eingebunden)
- `references.bib` — Bibliografie
- `zahlen/zahlen.tex` — Zahlenregister (falls vorhanden, siehe unten)
- `build/` — Kompilier-Artefakte; NICHT bearbeiten

## Zahlenregister (falls vorhanden)
- Zahlen nie direkt in den Text schreiben, sondern `\Z{schlüssel}` verwenden.
- Schlüssel finden: `grep -n "zahl@" zahlen/zahlen.tex | grep -i "<begriff>"`
- `zahlen.tex` ist generiert — Änderungen nur über die Quelle (z. B. `quellen.yaml`), nie von Hand.

## Arbeitsregeln
- Vor Änderungen die betroffene Datei lesen.
- Nach jeder inhaltlichen Änderung kompilieren und Ergebnis prüfen.
- Projekteigene Konventionen (README, ZAHLEN.md) haben Vorrang vor diesen Regeln.

## Agent-Stufen
Je nach Modellstärke ist ein Stufen-Agent aktiv (`whale-strong`, `whale-standard`,
`whale-light`). Dessen Prompt ergänzt dieses Protokoll um das passende Arbeitstempo.
Die Stufe wird automatisch aus dem gewählten Modell bestimmt (⚙️-Button in der GUI).

**Stufe C = Gleichstand durch Protokoll:** `whale-light` ist so gebaut, dass auch
kleine Modelle dieselben Compile/Fix-Ergebnisse erreichen wie starke Modelle.
Das Protokoll ersetzt Modellstärke: identische Kommandos, ein Schritt = eine Datei
und eine Stelle, wörtliche Log-Zitate, Verifikation nach jedem Schritt und ein
harter Stopp nach 2 erfolglosen Wiederholungen (statt endlosem Herumprobieren).
