// LaTeX Studio – Frontend mit Multi-Provider (Ollama + TUD:AI)
// Layout: Dateien | Editor | PDF (voll) — Chat unten

const API = {
  models: "/api/models",
  chat: "/api/chat",
  files: "/api/files",
  file: (n) => `/api/file/${encodeURIComponent(n)}`,
  create: "/api/files",
  del: (n) => `/api/files/${encodeURIComponent(n)}`,
  rename: "/api/files/rename",
  compile: "/api/compile",
  pdf: "/api/pdf",
  history: "/api/chat/history",
  clear: "/api/chat/clear",
};

// —— DOM ——
const fileTreeEl = document.getElementById("files");
const fileNewBtn = document.getElementById("file-new");
const editorEl = document.getElementById("editor");
const pdfFrame = document.getElementById("pdf");
const statusEl = document.getElementById("status");
const compileBtn = document.getElementById("compile");
const chatMsgsEl = document.getElementById("chat-messages");
const chatInputEl = document.getElementById("chat-input");
const chatFormEl = document.getElementById("chat-form");
const chatClearBtn = document.getElementById("chat-clear");
const modelSelectEl = document.getElementById("model-select");
const providerSelectEl = document.getElementById("provider-select");
const refreshModelsBtn = document.getElementById("refresh-models");
const fileDelBtn = document.getElementById("file-del");

let currentFile = "main.tex";
let selectedProvider = "ollama";
let selectedModel = "";
let models = { ollama: [], tud: [] };

// ============================================
//  MODELS (Multi-Provider)
// ============================================

async function loadModels() {
  const res = await fetch(API.models);
  const d = await res.json();
  models = { ollama: d.ollama || [], tud: d.tud || [] };

  // Provider-Select füllen
  providerSelectEl.innerHTML = "";
  const provOllama = document.createElement("option");
  provOllama.value = "ollama";
  provOllama.textContent = "Ollama (lokal)";
  providerSelectEl.appendChild(provOllama);

  if (models.tud.length > 0) {
    const provTud = document.createElement("option");
    provTud.value = "tud";
    provTud.textContent = `TUD:AI (ScaDS) — ${models.tud.length} Modelle`;
    providerSelectEl.appendChild(provTud);
  }

  // Model-Select füllen (abhängig vom gewählten Provider)
  updateModelSelect();
}

function updateModelSelect() {
  selectedProvider = providerSelectEl.value;
  const list = models[selectedProvider] || [];

  modelSelectEl.innerHTML = "";
  list.forEach(m => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    modelSelectEl.appendChild(opt);
  });

  // Default-Model wiederherstellen
  const saved = localStorage.getItem(`model_${selectedProvider}`);
  if (saved && list.includes(saved)) {
    modelSelectEl.value = saved;
    selectedModel = saved;
  } else if (list.length > 0) {
    selectedModel = list[0];
  }
}

providerSelectEl.onchange = () => {
  selectedProvider = providerSelectEl.value;
  updateModelSelect();
  localStorage.setItem("provider", selectedProvider);
};

modelSelectEl.onchange = () => {
  selectedModel = modelSelectEl.value;
  localStorage.setItem(`model_${selectedProvider}`, selectedModel);
};

refreshModelsBtn.onclick = () => loadModels();

// ============================================
//  DATEIEN (links)
// ============================================

async function loadFiles() {
  const res = await fetch(API.files);
  const d = await res.json();
  fileTreeEl.innerHTML = "";
  d.files.forEach(name => {
    const li = document.createElement("li");
    li.textContent = name;
    li.onclick = () => openFile(name);
    fileTreeEl.appendChild(li);
  });
}

async function openFile(name) {
  currentFile = name;
  const res = await fetch(API.file(name));
  const d = await res.json();
  editor.setValue(d.content);
  statusEl.textContent = name;
}

async function saveCurrentFile() {
  const content = editor.getValue();
  await fetch(API.file(currentFile), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: currentFile, content }),
  });
}

async function deleteCurrentFile() {
  if (!confirm(`"${currentFile}" wirklich löschen?`)) return;
  await fetch(API.del(currentFile), { method: "DELETE" });
  await loadFiles();
  // main.tex öffnen falls gelöscht
  if (currentFile === "main.tex") {
    openFile("main.tex");
  } else {
    openFile("main.tex");
  }
}

async function renameCurrentFile() {
  const newName = prompt("Neuer Name:", currentFile);
  if (!newName || newName === currentFile) return;
  const res = await fetch(API.rename, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old: currentFile, new: newName }),
  });
  if (res.ok) {
    await loadFiles();
    openFile(newName);
  }
}

fileNewBtn.onclick = async () => {
  const name = prompt("Dateiname (z.B. kapitel1.tex):");
  if (!name) return;
  const content = prompt("Erster Inhalt (optional):", "");
  await fetch(API.create, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content: content || "" }),
  });
  await loadFiles();
  openFile(name);
};

fileDelBtn.onclick = deleteCurrentFile;

// ============================================
//  KOMPILIEREN
// ============================================

async function compile() {
  statusEl.textContent = "Kompiliere...";
  await saveCurrentFile();
  const res = await fetch(API.compile, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: currentFile }),
  });
  const d = await res.json();
  if (d.ok) {
    statusEl.textContent = `✅ ${d.seconds}s`;
    pdfFrame.src = API.pdf + "?t=" + Date.now();
  } else {
    statusEl.textContent = `❌ ${d.errors[0] || "Fehler"}`;
  }
}

compileBtn.onclick = compile;

// ============================================
//  CHAT (Agent-Modus)
// ============================================

function addMsg(role, text) {
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  chatMsgsEl.appendChild(div);
  chatMsgsEl.scrollTop = chatMsgsEl.scrollHeight;
}

async function sendChat() {
  const msg = chatInputEl.value.trim();
  if (!msg) return;
  chatInputEl.value = "";
  addMsg("user", msg);
  addMsg("assistant", "Denke...");

  try {
    const res = await fetch(API.chat, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: msg,
        provider: selectedProvider,
        model: selectedModel,
      }),
    });
    const d = await res.json();
    if (d.error) {
      addMsg("assistant", "❌ " + d.error);
      return;
    }
    addMsg("assistant", d.reply || "(leer)");

    // FILE-Blöcke anwenden
    if (d.actions && d.actions.length > 0) {
      for (const act of d.actions) {
        if (act.action === "created") {
          addMsg("system", `📄 Erstellt: ${act.name}`);
        } else if (act.action === "edited") {
          addMsg("system", `✏️ Geändert: ${act.name}`);
        }
      }
      await loadFiles();
      await openFile("main.tex");
      await compile();
    }
  } catch (err) {
    addMsg("assistant", "❌ " + err.message);
  }
}

chatFormEl.onsubmit = (e) => { e.preventDefault(); sendChat(); };

// Chat-Verlauf löschen
chatClearBtn.onclick = async () => {
  await fetch(API.clear, { method: "POST" });
  chatMsgsEl.innerHTML = "";
};

async function loadChatHistory() {
  const res = await fetch(API.history);
  const d = await res.json();
  chatMsgsEl.innerHTML = "";
  (d.history || []).forEach(msg => {
    const div = document.createElement("div");
    div.className = `chat-msg ${msg.role}`;
    div.textContent = `[${msg.ts}] ${msg.text}`;
    chatMsgsEl.appendChild(div);
  });
  chatMsgsEl.scrollTop = chatMsgsEl.scrollHeight;
}

// ============================================
//  EDITOR (CodeMirror)
// ============================================
const editor = CodeMirror.fromTextArea(document.getElementById("editor"), {
  mode: "stex",
  lineNumbers: true,
  lineWrapping: true,
  indentUnit: 2,
});

// ============================================
//  AUTOSAVE (2s nach letzter Änderung)
// ============================================

let saveTimer = null;
editor.on("change", () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveCurrentFile, 2000);
});

// Ctrl+S
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "s") {
    e.preventDefault();
    compile();
  }
});

// ============================================
//  INIT
// ============================================

async function init() {
  await loadModels();
  await loadFiles();
  await loadChatHistory();
  await compile();
}

init();
