// LaTeX Studio – Frontend
// Auto-Save + Polling + Diff-Highlight + Font-Size + Panel-Resize

const API = {
  files: "/api/files",
  file: (n) => "/api/file/" + n.split("/").map(encodeURIComponent).join("/"),
  raw: (n) => "/api/raw/" + n.split("/").map(encodeURIComponent).join("/"),
  save: "/api/file",
  compile: "/api/compile",
  pdf: "/api/pdf",
  projects: "/api/projects",
  projectSwitch: "/api/projects/switch",
  projectImport: "/api/projects/import",
  projectInfo: "/api/project/info",
};

// —— DOM ——
const fileTreeEl = document.getElementById("files");
const editorEl = document.getElementById("editor");
const statusEl = document.getElementById("status");
const compileBtn = document.getElementById("compile");
const fontMinusBtn = document.getElementById("font-minus");
const fontPlusBtn = document.getElementById("font-plus");
const handleFilesEl = document.getElementById("handle-files");
const handlePdfEl = document.getElementById("handle-pdf");
const handleTerminalEl = document.getElementById("handle-terminal");
const errorPanel = document.getElementById("error-panel");
const errorLogEl = document.getElementById("error-log");
const errorCloseBtn = document.getElementById("error-close");
const projectSelectEl = document.getElementById("project-select");
const projectImportBtn = document.getElementById("project-import");
const projectCreateBtn = document.getElementById("project-create");

let currentFile = "main.tex";
let programmaticChange = false;  // unterdrückt Auto-Save bei setValue()
let lastOwnSave = 0;             // Zeitpunkt des letzten eigenen Speicherns
let editor = null;
let lastDiskContent = "";
let saveTimer = null;
let terminalPort = 8762;
let switchingProject = false;

// ============================================
//  EDITOR (CodeMirror)
// ============================================

editor = CodeMirror.fromTextArea(editorEl, {
  mode: "stex",
  lineNumbers: true,
  lineWrapping: true,
  indentUnit: 2,
});

// ============================================
//  FONT-SIZE (A− / A+)
// ============================================

let editorFontSize = parseInt(localStorage.getItem("editorFontSize") || "14");

function applyEditorFontSize() {
  editor.getWrapperElement().style.fontSize = editorFontSize + "px";
  editor.refresh();
}

fontMinusBtn.onclick = () => {
  editorFontSize = Math.max(8, editorFontSize - 1);
  applyEditorFontSize();
  localStorage.setItem("editorFontSize", editorFontSize);
};

fontPlusBtn.onclick = () => {
  editorFontSize = Math.min(32, editorFontSize + 1);
  applyEditorFontSize();
  localStorage.setItem("editorFontSize", editorFontSize);
};

// Init font size
editor.getWrapperElement().style.fontSize = editorFontSize + "px";

// ============================================
//  DARK / LIGHT MODE (nur Editor + Datei-Manager)
// ============================================

const themeToggleBtn = document.getElementById("theme-toggle");
let currentTheme = localStorage.getItem("theme") || "light";

function applyTheme(theme) {
  currentTheme = theme;
  const dark = theme === "dark";
  document.body.classList.toggle("dark", dark);
  if (editor) editor.setOption("theme", dark ? "material-darker" : "default");
  if (themeToggleBtn) themeToggleBtn.textContent = dark ? "☀️" : "🌙";
  localStorage.setItem("theme", theme);
}

if (themeToggleBtn) {
  themeToggleBtn.onclick = () =>
    applyTheme(currentTheme === "dark" ? "light" : "dark");
}

applyTheme(currentTheme);

// ============================================
//  AGENT-EINSTELLUNGEN (opencode-Standardmodell pro Projekt)
// ============================================

const agentSettingsBtn = document.getElementById("agent-settings");
const agentModal = document.getElementById("agent-modal");
const agentModelSelect = document.getElementById("agent-model-select");
const agentProjectEl = document.getElementById("agent-project");
const agentSaveBtn = document.getElementById("agent-save");
const agentCloseBtn = document.getElementById("agent-close");

async function openAgentSettings() {
  try {
    const res = await fetch("/api/agent/model");
    const d = await res.json();
    agentModelSelect.innerHTML = "";
    const groups = {};
    (d.models || []).forEach(m => {
      if (!groups[m.provider]) {
        const og = document.createElement("optgroup");
        og.label = m.provider;
        groups[m.provider] = og;
        agentModelSelect.appendChild(og);
      }
      const opt = document.createElement("option");
      opt.value = m.id;
      const tierLabel = { strong: "A", standard: "B", light: "C" }[m.tier] || "?";
      opt.textContent = `${m.label} (${m.id}) · Stufe ${tierLabel}`;
      groups[m.provider].appendChild(opt);
    });
    if (d.current) agentModelSelect.value = d.current;
    agentProjectEl.textContent =
      `${d.project} · Modell: ${d.source} · Agent: ${d.agent || "–"} (Stufe ${d.tier || "?"})`;
    agentModal.hidden = false;
  } catch (e) {
    statusEl.textContent = "Agent-Einstellungen: Fehler beim Laden";
  }
}

if (agentSettingsBtn) agentSettingsBtn.onclick = openAgentSettings;
if (agentCloseBtn) agentCloseBtn.onclick = () => { agentModal.hidden = true; };
if (agentModal) agentModal.onclick = (e) => {
  if (e.target === agentModal) agentModal.hidden = true;
};
if (agentSaveBtn) agentSaveBtn.onclick = async () => {
  const model = agentModelSelect.value;
  if (!model) return;
  agentSaveBtn.disabled = true;
  statusEl.textContent = "Speichere Modell…";
  try {
    const res = await fetch("/api/agent/model", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    const d = await res.json();
    if (d.error) { statusEl.textContent = "❌ " + d.error; return; }
    statusEl.textContent = `✅ ${d.model} · Agent ${d.agent} (Stufe ${d.tier})`;
    agentModal.hidden = true;
    reloadTerminal();
  } finally {
    agentSaveBtn.disabled = false;
  }
};

// ============================================
//  PDF-DARK-MODE (unabhängig vom Editor-Theme)
// ============================================

const pdfDarkToggleBtn = document.getElementById("pdf-dark-toggle");
let pdfDark = localStorage.getItem("pdfDark") === "1";

function applyPdfDark() {
  const container = document.getElementById("pdf-container");
  if (container) container.classList.toggle("pdf-dark", pdfDark);
  if (pdfDarkToggleBtn) {
    pdfDarkToggleBtn.textContent = pdfDark ? "🌗" : "🌓";
    pdfDarkToggleBtn.title = pdfDark
      ? "PDF-Dark aus (zurück zu weiss)"
      : "PDF-Vorschau dunkel darstellen (unabhängig vom Editor)";
  }
  localStorage.setItem("pdfDark", pdfDark ? "1" : "0");
}

if (pdfDarkToggleBtn) {
  pdfDarkToggleBtn.onclick = () => {
    pdfDark = !pdfDark;
    applyPdfDark();
  };
}

applyPdfDark();

applyTheme(currentTheme);

// ============================================
//  TERMINAL-ZOOM ((term −) / (term +))
// ============================================

const termZoomInBtn = document.getElementById("term-zoom-in");
const termZoomOutBtn = document.getElementById("term-zoom-out");
const terminalFrame = document.getElementById("terminal");
let terminalZoom = parseFloat(localStorage.getItem("terminalZoom") || "1");

function applyTerminalZoom() {
  const frame = document.getElementById("terminal");
  if (frame) {
    frame.style.transform = `scale(${terminalZoom})`;
    frame.style.transformOrigin = "top left";
    // Container-Breite/Höhe anpassen damit kein Leerraum entsteht
    frame.style.width = `${100 / terminalZoom}%`;
    frame.style.height = `${100 / terminalZoom}%`;
  }
  localStorage.setItem("terminalZoom", terminalZoom);
}

if (termZoomInBtn) termZoomInBtn.onclick = () => {
  terminalZoom = Math.min(2, terminalZoom + 0.1);
  applyTerminalZoom();
};
if (termZoomOutBtn) termZoomOutBtn.onclick = () => {
  terminalZoom = Math.max(0.5, terminalZoom - 0.1);
  applyTerminalZoom();
};

// Init font size
editor.getWrapperElement().style.fontSize = editorFontSize + "px";

// ============================================
//  PANEL-RESIZE (Drag-Handles)
// ============================================

function makeDrag(handle, target, cssVar, axis, min, max, invert = false) {
  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    const startPos = axis === "x" ? e.clientX : e.clientY;
    const startSize = axis === "x"
      ? target.getBoundingClientRect().width
      : target.getBoundingClientRect().height;

    const move = (ev) => {
      const curPos = axis === "x" ? ev.clientX : ev.clientY;
      // invert: Handle liegt links/oben vom Panel → Ziehen nach links/oben vergrössert
      const delta = (curPos - startPos) * (invert ? -1 : 1);
      // dynamisches Max: nie mehr als das Fenster hergibt
      const effMax = axis === "y" ? Math.min(max, window.innerHeight - 120) : max;
      const newSize = Math.max(min, Math.min(effMax, startSize + delta));
      document.documentElement.style.setProperty(cssVar, newSize + "px");
    };
    const up = () => {
      document.removeEventListener("mousemove", move);
      document.removeEventListener("mouseup", up);
      document.body.classList.remove("dragging");
      document.body.style.cursor = "";
      if (cssVar === "--w-pdf") loadPdf();  // neue Breite → schärfer neu rendern
    };
    // Iframes schlucken sonst mousemove-Events → Drag friert ein
    document.body.classList.add("dragging");
    document.body.style.cursor = axis === "x" ? "col-resize" : "row-resize";
    document.addEventListener("mousemove", move);
    document.addEventListener("mouseup", up);
  });
}

const pdfPaneEl = document.querySelector(".pdf-pane");
const terminalPanelEl = document.querySelector(".terminal-panel");

// Dateibaum: Handle rechts vom Panel → normales Ziehen
makeDrag(handleFilesEl, fileTreeEl, "--w-files", "x", 120, 500);
// PDF: Handle links vom Panel → invertiert (nach links ziehen = breiter)
makeDrag(handlePdfEl, pdfPaneEl, "--w-pdf", "x", 200, 900, true);
// Terminal: Handle über dem Panel → invertiert (nach oben ziehen = höher)
makeDrag(handleTerminalEl, terminalPanelEl, "--h-terminal", "y", 80, 700, true);

// ============================================
//  DATEIEN
// ============================================

// ============================================
//  DATEI-BAUM (Ordner + alle Dateitypen)
// ============================================

const TEXT_EXT = ["tex", "bib", "txt", "md", "sty", "cls", "cfg", "def"];
const expandedDirs = new Set(JSON.parse(localStorage.getItem("expandedDirs") || "[]"));

function saveExpanded() {
  localStorage.setItem("expandedDirs", JSON.stringify([...expandedDirs]));
}

function buildTree(dirs, files) {
  const root = { dirs: new Map(), files: [] };
  const ensure = (parts) => {
    let node = root;
    for (const part of parts) {
      if (!node.dirs.has(part)) node.dirs.set(part, { dirs: new Map(), files: [] });
      node = node.dirs.get(part);
    }
    return node;
  };
  dirs.forEach(path => ensure(path.split("/")));
  files.forEach(path => {
    const parts = path.split("/");
    const fname = parts.pop();
    ensure(parts).files.push({ name: fname, path });
  });
  return root;
}

function renderTree(node, parentEl, prefix) {
  // Ordner zuerst, alphabetisch
  [...node.dirs.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .forEach(([name, child]) => {
      const path = prefix ? `${prefix}/${name}` : name;
      const isOpen = expandedDirs.has(path);

      const li = document.createElement("li");
      const row = document.createElement("div");
      row.className = "tree-row tree-dir";
      row.textContent = `${isOpen ? "▾" : "▸"} 📁 ${name}`;
      row.onclick = () => {
        if (expandedDirs.has(path)) expandedDirs.delete(path);
        else expandedDirs.add(path);
        saveExpanded();
        loadFiles();
      };
      li.appendChild(row);

      const ul = document.createElement("ul");
      ul.className = "tree-children";
      ul.hidden = !isOpen;
      renderTree(child, ul, path);
      li.appendChild(ul);
      parentEl.appendChild(li);
    });

  // Dateien, alphabetisch
  node.files
    .sort((a, b) => a.name.localeCompare(b.name))
    .forEach(f => {
      const li = document.createElement("li");
      const row = document.createElement("div");
      row.className = "tree-row tree-file";
      const isTex = f.path.toLowerCase().endsWith(".tex");
      row.textContent = `${isTex ? "📄" : "📎"} ${f.name}`;
      if (f.path === currentFile) row.classList.add("active");
      row.onclick = () => openEntry(f.path);
      li.appendChild(row);
      parentEl.appendChild(li);
    });
}

function openEntry(path) {
  const ext = path.split(".").pop().toLowerCase();
  if (TEXT_EXT.includes(ext)) {
    openFile(path);
  } else {
    // Bild/PDF/etc. in der PDF-Pane anzeigen
    showRawInPdfPane(path);
    statusEl.textContent = "📎 " + path;
    loadFiles();
  }
}

async function loadFiles() {
  const res = await fetch(API.files);
  const d = await res.json();
  const savedScroll = fileTreeEl.scrollTop;
  fileTreeEl.innerHTML = "";
  const root = buildTree(d.dirs || [], d.files || []);
  renderTree(root, fileTreeEl, "");
  fileTreeEl.scrollTop = savedScroll;
}

async function openFile(name) {
  currentFile = name;
  const res = await fetch(API.file(name));
  const d = await res.json();
  if (d.error || typeof d.content !== "string") {
    lastDiskContent = "";
    editor.setValue("");
    statusEl.textContent = name + " (nicht vorhanden)";
    return;
  }
  lastDiskContent = d.content;
  programmaticChange = true;
  editor.setValue(d.content);
  programmaticChange = false;
  statusEl.textContent = name;
}

// ============================================
//  AUTO-SAVE (User tippt → 500ms → Disk)
// ============================================

editor.on("change", () => {
  if (programmaticChange) return;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    const content = editor.getValue();
    await fetch(API.save, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: currentFile, content }),
    });
    lastDiskContent = content;
    lastOwnSave = Date.now() / 1000;
  }, 500);
});

// ============================================
//  FILE-POLLING (opencode ändert Disk → Reload + Highlight)
// ============================================

setInterval(async () => {
  if (!currentFile || !editor || switchingProject) return;
  try {
    const res = await fetch(API.file(currentFile));
    const d = await res.json();
    if (d.error || typeof d.content !== "string") return; // Datei fehlt
    const diskContent = d.content;
    const editorContent = editor.getValue();

    // Disk ≠ Editor UND Disk ≠ letzter bekannter Stand → opencode hat geändert
    if (diskContent !== editorContent && diskContent !== lastDiskContent) {
      reloadWithDiff(diskContent, editorContent);
      lastDiskContent = diskContent;
    }
  } catch (e) { /* File gelöscht — ignorieren */ }
}, 2000);

// ============================================
//  DIFF-RELOAD (geänderte Zeilen gelb markieren)
// ============================================

function reloadWithDiff(newContent, oldContent) {
  const oldLines = oldContent.split("\n");
  const newLines = newContent.split("\n");
  const changedLines = [];
  const maxLen = Math.max(oldLines.length, newLines.length);

  for (let i = 0; i < maxLen; i++) {
    if (oldLines[i] !== newLines[i]) {
      changedLines.push(i);
    }
  }

  // Cursor + Scrollposition merken und nach dem Reload wiederherstellen
  const prevCursor = editor.getCursor();
  const prevScroll = editor.getScrollInfo().top;

  programmaticChange = true;
  editor.setValue(newContent);
  programmaticChange = false;

  const maxLine = Math.max(0, editor.lineCount() - 1);
  editor.setCursor({ line: Math.min(prevCursor.line, maxLine), ch: 0 });
  const info = editor.getScrollInfo();
  editor.scrollTo(null, Math.min(prevScroll, Math.max(0, info.height - info.clientHeight)));

  // Geänderte Zeilen gelb markieren
  changedLines.forEach(lineNum => {
    if (lineNum < editor.lineCount()) {
      editor.addLineClass(lineNum, "background", "cm-diff-highlight");
    }
  });

  // Nach 3 Sekunden Highlight entfernen
  setTimeout(() => {
    changedLines.forEach(lineNum => {
      if (lineNum < editor.lineCount()) {
        editor.removeLineClass(lineNum, "background", "cm-diff-highlight");
      }
    });
  }, 3000);

  if (changedLines.length > 0) {
    statusEl.textContent = `📝 ${changedLines.length} Zeile(n) geändert`;
  }
}

// ============================================
//  PDF-VORSCHAU (pdf.js) + SyncTeX Navigation
// ============================================

const pdfContainer = document.getElementById("pdf-container");
let pdfScale = 1.0;

async function loadPdf() {
  if (!window.pdfjsLib) {
    pdfContainer.textContent = "PDF.js nicht geladen";
    return;
  }
  pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.js";
  try {
    const pdf = await pdfjsLib.getDocument(API.pdf + "?t=" + Date.now()).promise;
    // aktuelle Scrollposition merken (Verhältnis, überlebt Neurender)
    const prevTop = pdfContainer.scrollTop;
    const prevHeight = pdfContainer.scrollHeight;
    pdfContainer.innerHTML = "";
    const first = await pdf.getPage(1);
    const baseVp = first.getViewport({ scale: 1 });
    const avail = Math.max(200, pdfContainer.clientWidth - 30);
    pdfScale = Math.min(2.5, Math.max(0.4, avail / baseVp.width));

    // Supersampling: physikalisch 2x rendern und per CSS runterskalieren → scharfe Schrift
    const Q = 2;
    const dpr = window.devicePixelRatio || 1;
    const factor = dpr * Q;
    for (let n = 1; n <= pdf.numPages; n++) {
      const page = await pdf.getPage(n);
      const viewport = page.getViewport({ scale: pdfScale });
      const wrap = document.createElement("div");
      wrap.className = "pdf-page";
      wrap.dataset.page = n;
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width * factor);
      canvas.height = Math.floor(viewport.height * factor);
      canvas.style.width = Math.floor(viewport.width) + "px";
      canvas.style.height = Math.floor(viewport.height) + "px";
      canvas.dataset.page = n;
      wrap.appendChild(canvas);

      // Text-Layer: unsichtbarer, markierbarer Text über der Canvas
      const textDiv = document.createElement("div");
      textDiv.className = "textLayer";
      textDiv.style.width = Math.floor(viewport.width) + "px";
      textDiv.style.height = Math.floor(viewport.height) + "px";
      textDiv.style.setProperty("--scale-factor", viewport.scale);
      wrap.appendChild(textDiv);

      pdfContainer.appendChild(wrap);
      const ctx = canvas.getContext("2d");
      await page.render({
        canvasContext: ctx,
        viewport,
        transform: [factor, 0, 0, factor, 0, 0],
      }).promise;

      try {
        const textContent = await page.getTextContent();
        if (pdfjsLib.renderTextLayer) {
          await pdfjsLib.renderTextLayer({
            textContentSource: textContent,
            container: textDiv,
            viewport,
            textDivs: [],
          }).promise;
        }
      } catch (e) { /* Textlayer optional */ }
    }
    // Scrollposition wiederherstellen
    if (prevHeight > 0) {
      pdfContainer.scrollTop = (prevTop / prevHeight) * pdfContainer.scrollHeight;
    }
  } catch (e) {
    pdfContainer.textContent = "Kein PDF vorhanden — mit Strg+S kompilieren";
  }
}

function showRawInPdfPane(path) {
  pdfContainer.innerHTML = "";
  const img = document.createElement("img");
  img.src = API.raw(path) + "?t=" + Date.now();
  img.alt = path;
  pdfContainer.appendChild(img);
}

function showPdfMarker(page, xPt, yPt) {
  const wrap = pdfContainer.querySelector(`.pdf-page[data-page="${page}"]`);
  if (!wrap) return;
  const old = wrap.querySelector(".synctex-marker");
  if (old) old.remove();
  const m = document.createElement("div");
  m.className = "synctex-marker";
  m.style.left = (xPt * pdfScale) + "px";
  m.style.top = (yPt * pdfScale) + "px";
  wrap.appendChild(m);
  setTimeout(() => m.remove(), 2500);
}

function scrollToPdfPosition(page, xPt, yPt) {
  const wrap = pdfContainer.querySelector(`.pdf-page[data-page="${page}"]`);
  if (!wrap) return;
  pdfContainer.scrollTo({
    top: Math.max(0, wrap.offsetTop + yPt * pdfScale - 80),
    behavior: "smooth",
  });
  showPdfMarker(page, xPt, yPt);
}

// —— Doppelklick im Editor → Sprung zur PDF-Stelle (forward search) ——
editor.on("dblclick", async (cm, e) => {
  if (!currentFile.toLowerCase().endsWith(".tex")) return;
  const pos = cm.coordsChar({ left: e.clientX, top: e.clientY });
  try {
    const res = await fetch("/api/synctex/view", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: currentFile, line: pos.line + 1, column: pos.ch + 1 }),
    });
    const d = await res.json();
    if (d.error) { statusEl.textContent = "SyncTeX: " + d.error; return; }
    scrollToPdfPosition(d.page, d.x, d.y);
    statusEl.textContent = `→ PDF Seite ${d.page}`;
  } catch (err) { /* ignore */ }
});

// —— Doppelklick im PDF → Sprung zur Code-Stelle (inverse search) ——
pdfContainer.addEventListener("dblclick", async (e) => {
  const wrap = e.target.closest(".pdf-page");
  if (!wrap) return;
  const canvas = wrap.querySelector("canvas");
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const xPt = (e.clientX - rect.left) / pdfScale;
  const yPt = (e.clientY - rect.top) / pdfScale;
  try {
    const res = await fetch("/api/synctex/edit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page: parseInt(wrap.dataset.page, 10), x: xPt, y: yPt }),
    });
    const d = await res.json();
    if (d.error) { statusEl.textContent = "SyncTeX: " + d.error; return; }
    await openFile(d.file);
    const line = Math.max(0, (d.line || 1) - 1);
    const ch = Math.max(0, (d.column || 1) - 1);
    editor.setCursor({ line, ch });
    editor.scrollIntoView({ line, ch }, 200);
    editor.focus();
    statusEl.textContent = `← ${d.file}:${d.line}`;
  } catch (err) { /* ignore */ }
});

// ============================================
//  KOMPILIEREN (nutzt Disk-Stand, nicht Editor-Puffer)
// ============================================

async function compile() {
  statusEl.textContent = "Kompiliere…";
  const res = await fetch(API.compile, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: currentFile }),
  });
  const d = await res.json();
  if (d.ok) {
    statusEl.textContent = `✅ ${d.seconds}s`;
    loadPdf();
    hideErrorPanel();
  } else {
    statusEl.textContent = `❌ ${d.errors[0] || "Fehler"}`;
    showErrorLog(d.log || "Kein Log verfügbar");
  }
}

compileBtn.onclick = compile;

// ============================================
//  ERROR-PANEL
// ============================================

function showErrorLog(logText) {
  if (errorLogEl) errorLogEl.textContent = logText;
  if (errorPanel) errorPanel.hidden = false;
}

function hideErrorPanel() {
  if (errorPanel) errorPanel.hidden = true;
}

if (errorCloseBtn) errorCloseBtn.onclick = hideErrorPanel;

// ============================================
//  KEYBOARD SHORTCUTS
// ============================================

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    compile();
  }
});

// ============================================
//  DATEI-AKTIONEN (＋ Neu / 🗑 Löschen / ✏️ Umbenennen)
// ============================================

const fileNewBtn = document.getElementById("file-new");
const fileDelBtn = document.getElementById("file-del");
const fileRenameBtn = document.getElementById("file-rename");

fileNewBtn.onclick = async () => {
  const name = prompt("Neue Datei (Pfad erlaubt, z.B. kapitel/einleitung.tex):");
  if (!name) return;
  const res = await fetch("/api/files", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content: "" }),
  });
  const d = await res.json();
  if (d.error) { alert("Fehler: " + d.error); return; }
  await loadFiles();
  openEntry(d.name);
};

fileDelBtn.onclick = async () => {
  if (!currentFile) return;
  if (!confirm(`"${currentFile}" wirklich löschen?`)) return;
  const url = "/api/files/" + currentFile.split("/").map(encodeURIComponent).join("/");
  const res = await fetch(url, { method: "DELETE" });
  const d = await res.json();
  if (d.error) { alert("Fehler: " + d.error); return; }
  await loadFiles();
  openFile("main.tex");
};

fileRenameBtn.onclick = async () => {
  if (!currentFile) return;
  const newName = prompt("Neuer Pfad/Name:", currentFile);
  if (!newName || newName === currentFile) return;
  const res = await fetch("/api/files/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old: currentFile, new: newName }),
  });
  const d = await res.json();
  if (d.error) { alert("Fehler: " + d.error); return; }
  await loadFiles();
  openEntry(newName);
};

// ============================================
//  PROJEKT-VERWALTUNG (Auswahl + Import)
// ============================================

async function loadProjectInfo() {
  try {
    const res = await fetch(API.projectInfo);
    const d = await res.json();
    if (d.terminal_port) terminalPort = d.terminal_port;
  } catch (e) { /* ignore */ }
}

async function loadProjects() {
  const res = await fetch(API.projects);
  const d = await res.json();
  projectSelectEl.innerHTML = "";
  (d.projects || []).forEach(name => {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    if (name === d.active) opt.selected = true;
    projectSelectEl.appendChild(opt);
  });
}

async function reloadTerminal(retries = 3) {
  const frame = document.getElementById("terminal");
  if (!frame) return;
  try {
    const res = await fetch("/api/terminal/status");
    const d = await res.json();
    if (!d.running && retries > 0) {
      statusEl.textContent = "Terminal startet…";
      setTimeout(() => reloadTerminal(retries - 1), 1500);
      return;
    }
    frame.src = `http://localhost:${terminalPort}/?t=${Date.now()}`;
  } catch (e) {
    // Backend nicht erreichbar — trotzdem laden
    frame.src = `http://localhost:${terminalPort}/?t=${Date.now()}`;
  }
}

async function switchProject(name) {
  switchingProject = true;
  statusEl.textContent = `Wechsle zu Projekt «${name}»…`;
  try {
    const res = await fetch(API.projectSwitch, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    });
    const d = await res.json();
    if (d.error) {
      statusEl.textContent = "❌ " + d.error;
      return;
    }
    lastDiskContent = "";
    zahlenCache = null;  // Zahlenregister gehört zum Projekt
    hideErrorPanel();
    await loadFiles();
    await openFile("main.tex");
    loadPdf();
    reloadTerminal();  // opencode läuft jetzt im neuen Projektordner
    statusEl.textContent = `Projekt: ${d.active}`;
    await compile();
  } finally {
    switchingProject = false;
  }
}

projectSelectEl.onchange = () => switchProject(projectSelectEl.value);

projectImportBtn.onclick = async () => {
  const path = prompt("Pfad zum Projektordner (z.B. ~/mein-latex-projekt):");
  if (!path) return;
  statusEl.textContent = "Importiere Projekt…";
  const res = await fetch(API.projectImport, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_path: path }),
  });
  const d = await res.json();
  if (d.error) {
    alert("Import fehlgeschlagen:\n" + d.error);
    statusEl.textContent = "❌ Import fehlgeschlagen";
    return;
  }
  await loadProjects();
  projectSelectEl.value = d.name;
  await switchProject(d.name);
  if (d.warning) alert("Hinweis: " + d.warning);
};

// ============================================
//  ZAHLENREGISTER (Button + interaktive Tabelle)
// ============================================

const zahlenToggleBtn = document.getElementById("zahlen-toggle");
const zahlenModal = document.getElementById("zahlen-modal");
const zahlenBody = document.getElementById("zahlen-body");
const zahlenFilter = document.getElementById("zahlen-filter");
const zahlenSourceEl = document.getElementById("zahlen-source");
const zahlenCloseBtn = document.getElementById("zahlen-close");
const zahlenSortKeyEl = document.getElementById("zahlen-sort-key");
const zahlenSortValueEl = document.getElementById("zahlen-sort-value");

let zahlenCache = null;                      // {found, source, entries}
let zahlenSort = { col: "key", dir: 1 };

async function toggleZahlen() {
  if (!zahlenModal.hidden) { zahlenModal.hidden = true; return; }
  if (!zahlenCache) {
    try {
      const res = await fetch("/api/zahlen");
      zahlenCache = await res.json();
    } catch (e) {
      statusEl.textContent = "Zahlenregister: Fehler beim Laden";
      return;
    }
  }
  if (!zahlenCache.found || !(zahlenCache.entries || []).length) {
    statusEl.textContent = "Kein Zahlenregister im Projekt gefunden";
    return;
  }
  zahlenSourceEl.textContent = `${zahlenCache.source} · ${zahlenCache.count} Einträge`;
  renderZahlen();
  zahlenModal.hidden = false;
  zahlenFilter.focus();
}

function renderZahlen() {
  const filter = zahlenFilter.value.trim().toLowerCase();
  let rows = zahlenCache.entries;
  if (filter) {
    rows = rows.filter(e =>
      e.key.toLowerCase().includes(filter) ||
      (e.display || "").toLowerCase().includes(filter));
  }
  rows = [...rows].sort((a, b) => {
    const av = zahlenSort.col === "key" ? a.key : (a.display || "");
    const bv = zahlenSort.col === "key" ? b.key : (b.display || "");
    return av.localeCompare(bv, "de", { numeric: true }) * zahlenSort.dir;
  });

  zahlenSortKeyEl.textContent = zahlenSort.col === "key" ? (zahlenSort.dir > 0 ? "▲" : "▼") : "";
  zahlenSortValueEl.textContent = zahlenSort.col === "value" ? (zahlenSort.dir > 0 ? "▲" : "▼") : "";

  const frag = document.createDocumentFragment();
  rows.slice(0, 3000).forEach(e => {
    const tr = document.createElement("tr");
    const tdK = document.createElement("td");
    tdK.className = "zk";
    tdK.textContent = e.key;
    const tdV = document.createElement("td");
    tdV.textContent = e.display;
    tr.appendChild(tdK);
    tr.appendChild(tdV);
    tr.onclick = async () => {
      try {
        await navigator.clipboard.writeText(`\\Z{${e.key}}`);
        statusEl.textContent = `kopiert: \\Z{${e.key}}`;
      } catch (_) { /* clipboard verweigert */ }
    };
    tr.ondblclick = () => {
      editor.replaceSelection(`\\Z{${e.key}}`);
      editor.focus();
      zahlenModal.hidden = true;
    };
    frag.appendChild(tr);
  });
  zahlenBody.innerHTML = "";
  zahlenBody.appendChild(frag);
}

if (zahlenToggleBtn) zahlenToggleBtn.onclick = toggleZahlen;
if (zahlenCloseBtn) zahlenCloseBtn.onclick = () => { zahlenModal.hidden = true; };
if (zahlenFilter) zahlenFilter.oninput = renderZahlen;
if (zahlenModal) zahlenModal.onclick = (e) => {
  if (e.target === zahlenModal) zahlenModal.hidden = true;
};
document.querySelectorAll(".zahlen-table th").forEach(th => {
  th.onclick = () => {
    const col = th.dataset.sort;
    if (zahlenSort.col === col) zahlenSort.dir *= -1;
    else zahlenSort = { col, dir: 1 };
    renderZahlen();
  };
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && zahlenModal && !zahlenModal.hidden) {
    zahlenModal.hidden = true;
  }
});

// ============================================
//  AGENT-AKTIVITÄT (was tut das LLM gerade?)
// ============================================

let lastActivityTs = Date.now() / 1000;

setInterval(async () => {
  if (switchingProject) return;
  try {
    const res = await fetch(`/api/activity?since=${lastActivityTs}`);
    const d = await res.json();
    lastActivityTs = d.now || (Date.now() / 1000);
    if (!d.events || !d.events.length) return;
    // eigene Auto-Saves nicht als Agent-Aktivität melden
    const relevant = d.events.filter(e =>
      !(e.name === currentFile && (Date.now() / 1000 - lastOwnSave) < 4));
    if (!relevant.length) return;
    const e = relevant[relevant.length - 1];
    const time = new Date(e.mtime * 1000).toLocaleTimeString("de-DE");
    statusEl.textContent = `🤖 Agent: ${e.name} geändert (${time})`;
    loadFiles();
  } catch (_) { /* ignore */ }
}, 2000);

// Fenster-Resize → PDF neu rendern, damit es immer die volle Breite scharf füllt
let pdfResizeTimer = null;
window.addEventListener("resize", () => {
  clearTimeout(pdfResizeTimer);
  pdfResizeTimer = setTimeout(() => loadPdf(), 400);
});

if (projectCreateBtn) projectCreateBtn.onclick = async () => {
  const name = prompt("Name für das neue Projekt (z.B. paper-2027):");
  if (!name) return;
  statusEl.textContent = "Lege Projekt an…";
  const res = await fetch("/api/projects/create", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const d = await res.json();
  if (d.error) {
    alert("Anlegen fehlgeschlagen:\n" + d.error);
    statusEl.textContent = "❌ Anlegen fehlgeschlagen";
    return;
  }
  await loadProjects();
  projectSelectEl.value = d.name;
  await switchProject(d.name);
  statusEl.textContent = `Neues Projekt: ${d.name}`;
};

// ============================================
//  INIT
// ============================================

async function init() {
  await loadProjectInfo();
  await loadProjects();
  await loadFiles();
  await openFile("main.tex");
  await compile();
  reloadTerminal();
}

init();
