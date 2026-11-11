---
description: Neues Kapitel als section-Datei anlegen und in main.tex einbinden
---
Lege ein neues Kapitel zum Thema "$ARGUMENTS" an.

1. Dateiname: `section_<slug>.tex` (slug: kleingeschrieben, Umlaute → ae/oe/ue, Leerzeichen → `-`).
2. Inhalt:
```latex
\section{<Titel>}
\label{sec:<slug>}
% TODO: Inhalt
```
3. In `main.tex` direkt nach dem letzten `\input{section_...}` einfügen: `\input{section_<slug>}`
4. Kompilieren und kurz melden, was angelegt wurde.
