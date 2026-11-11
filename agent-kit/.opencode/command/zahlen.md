---
description: Zahlenregister durchsuchen und passende \Z-Schlüssel zeigen
---
Suche im Zahlenregister nach: "$ARGUMENTS"

1. Falls `zahlen/zahlen.tex` existiert:
   `grep -n "zahl@" zahlen/zahlen.tex | grep -i "<begriff>"`
2. Max. 15 Treffer als Tabelle `schlüssel → wert` anzeigen.
3. Hinweis: Im Text `\Z{schlüssel}` verwenden — Werte nie hartkodieren.
