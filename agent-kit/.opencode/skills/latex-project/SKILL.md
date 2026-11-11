---
name: latex-project
description: Kompilieren, Fehleranalyse und Projektkonventionen für LaTeX-Projekte in WHALE. Verwenden bei Compile-Fehlern, neuen Kapiteln, Zahlenreferenzen (\Z{}) oder Fragen zum Projektaufbau.
---
# LaTeX-Projekt-Workflow

## Kompilieren
Immer: `latexmk -pdf -synctex=1 -interaction=nonstopmode -outdir=build main.tex`
- Output: `build/main.pdf`, Log: `build/main.log`, latexmk-Output: `build/compile.log`
- Wenn latexmk „Nothing to do“ sagt, aber Änderungen erwartet werden: `latexmk -g ...` (force)

## Typische Fehler → Vorgehen
| Meldung | Ursache | Fix |
|---|---|---|
| `Undefined control sequence` | Tippfehler/Makro fehlt | Zeile lesen, Makro korrigieren oder `\newcommand` ergänzen |
| `File ... not found` | fehlendes `\input`/Bild | Datei anlegen oder Pfad korrigieren (`\graphicspath`) |
| `Missing $ inserted` | Mathe-Sonderzeichen im Text | `$...$` setzen oder Sonderzeichen escapen |
| `Runaway argument` | fehlende `}` | Klammern in der Zeile prüfen |
| `! LaTeX Error: Missing \begin{document}` | Inhalt in der Präambel | Text nach `\begin{document}` verschieben |
| `Package ... Error` | Option/Paket fehlt | `kpsewhich <paket>.sty` prüfen; Paket ggf. ergänzen |

## Ablauf bei Fix-Aufträgen
1. Kompilieren, Fehler aus Log extrahieren.
2. Betroffene Datei + Zeile lesen.
3. Minimal-invasiv fixen (nie ganze Datei blind umschreiben).
4. Erneut kompilieren; bis zu 3 Iterationen; dann Bericht.

## Zahlenregister
- `\Z{schlüssel}` statt hartkodierter Werte; Schlüssel via `grep "zahl@" zahlen/zahlen.tex`.
- `zahlen.tex` nie manuell ändern (generiert).

## Neue Kapitel
`section_<slug>.tex` anlegen, `\input{section_<slug>}` in `main.tex` nach dem letzten `\input`.
