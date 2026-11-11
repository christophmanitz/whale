---
description: Alle Compile-Fehler beheben bis das PDF fehlerfrei baut
---
Behebe die Compile-Fehler dieses Projekts.

Ablauf (max. 3 Iterationen):
1. `latexmk -pdf -synctex=1 -interaction=nonstopmode -outdir=build main.tex`
2. Fehler aus `build/compile.log` bzw. `build/main.log` extrahieren
   (`^!`, `Undefined control sequence`, `File ... not found`).
3. Ursächliche Zeile in der genannten Datei lesen und minimal-invasiv fixen.
4. Erneut kompilieren.
Bei Erfolg: kurze Liste der Fixes (`datei:zeile – was geändert`).
Wenn nach 3 Iterationen noch Fehler bleiben: Restfehler + Vermutung berichten, nicht raten.
