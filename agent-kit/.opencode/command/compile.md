---
description: Projekt kompilieren und Fehler kurz auflisten
---
Kompiliere dieses LaTeX-Projekt und berichte das Ergebnis.

1. `latexmk -pdf -synctex=1 -interaction=nonstopmode -outdir=build main.tex`
2. Bei Erfolg: kurz "✅ kompiliert" melden (Seitenzahl aus dem Log, falls sichtbar). Sonst nichts.
3. Bei Fehlern: `build/compile.log` und `build/main.log` lesen und max. 5 Fehler als
   `datei:zeile – Meldung` auflisten. Noch keine Fixes durchführen.
