"""Tests für LaTeX Studio – neues API-Format."""
import app as appmod


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("LATEX_PROJECT_DIR", str(tmp_path))
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Hallo\\end{document}", encoding="utf-8")
    return appmod.create_app(tmp_path).test_client()


def test_health(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    j = c.get("/api/health").get_json()
    assert j["ok"] is True


def test_files_list(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    assert "main.tex" in c.get("/api/files").get_json()["files"]


def test_create_file(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    r = c.post("/api/files", json={"name": "neu.tex", "content": "\\section{Neu}"})
    assert r.get_json()["ok"] is True
    r = c.get("/api/file/neu.tex")
    assert "Neu" in r.get_json()["content"]


def test_read_file_not_found(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    r = c.get("/api/file/gibtsnicht.tex")
    assert r.status_code == 404


def test_path_traversal(tmp_path, monkeypatch):
    """Path-Traversal muss blockiert werden (400 oder 404, nie 200)."""
    c = make_client(tmp_path, monkeypatch)
    r = c.get("/api/file/../../etc/passwd")
    assert r.status_code in (400, 404)


def test_compile(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    r = c.post("/api/compile", json={"name": "main.tex"})
    j = r.get_json()
    assert j["ok"] is True, j.get("log", "")
    assert (tmp_path / "build" / "main.pdf").exists()


def test_compile_error(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    (tmp_path / "main.tex").write_text("\\falsch", encoding="utf-8")
    r = c.post("/api/compile", json={"name": "main.tex"})
    j = r.get_json()
    assert j["ok"] is False
    assert "! Undefined control sequence" in "\n".join(j["errors"])


def test_pdf(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    c.post("/api/compile", json={"name": "main.tex"})
    r = c.get("/api/pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"


def test_chat_history(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    r = c.get("/api/chat/history")
    assert r.get_json()["history"] == []


def test_chat_offline(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    r = c.post("/api/chat", json={"message": "hi", "model": "qwen2.5:7b-fast"})
    assert r.status_code in (200, 502)


def test_projects_list(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "PROJECTS_ROOT", tmp_path / "projects")
    c = make_client(tmp_path, monkeypatch)
    d = c.get("/api/projects").get_json()
    assert "default" in d["projects"]


def test_project_import_and_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "PROJECTS_ROOT", tmp_path / "projects")
    src = tmp_path / "extern"
    src.mkdir()
    (src / "main.tex").write_text(
        "\\documentclass{article}\\begin{document}Hi\\end{document}", encoding="utf-8")
    (src / "img.png").write_bytes(b"x")

    c = make_client(tmp_path, monkeypatch)
    r = c.post("/api/projects/import", json={"source_path": str(src)})
    d = r.get_json()
    assert d["ok"] is True, d
    name = d["name"]
    dest = tmp_path / "projects" / name
    assert (dest / "main.tex").exists()
    assert (dest / "img.png").exists()

    r = c.post("/api/projects/switch", json={"name": name})
    assert r.get_json()["active"] == name
    assert "main.tex" in c.get("/api/files").get_json()["files"]
    assert "Hi" in c.get("/api/file/main.tex").get_json()["content"]


def test_nested_dirs_and_raw(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    (tmp_path / "bilder").mkdir()
    (tmp_path / "bilder" / "logo.png").write_bytes(b"\x89PNG")
    (tmp_path / "kapitel").mkdir()
    (tmp_path / "kapitel" / "einleitung.tex").write_text("\\section{Einleitung}", encoding="utf-8")

    d = c.get("/api/files").get_json()
    assert "bilder" in d["dirs"]
    assert "bilder/logo.png" in d["files"]
    assert "kapitel/einleitung.tex" in d["files"]

    r = c.get("/api/file/kapitel/einleitung.tex")
    assert "Einleitung" in r.get_json()["content"]

    r = c.get("/api/raw/bilder/logo.png")
    assert r.status_code == 200
    assert r.data == b"\x89PNG"

    r = c.post("/api/file", json={"name": "kapitel/neu.tex", "content": "x"})
    assert r.get_json()["ok"] is True
    assert (tmp_path / "kapitel" / "neu.tex").exists()

    # build/ und versteckte Dateien tauchen nicht auf
    (tmp_path / "build").mkdir(exist_ok=True)
    (tmp_path / "build" / "main.pdf").write_bytes(b"%PDF")
    d = c.get("/api/files").get_json()
    assert not any("build/" in f for f in d["files"])


def test_synctex_roundtrip(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    # ohne Compile: keine SyncTeX-Daten
    r = c.post("/api/synctex/view", json={"file": "main.tex", "line": 1, "column": 1})
    assert r.status_code == 404

    r = c.post("/api/compile", json={"name": "main.tex"})
    assert r.get_json()["ok"] is True, r.get_json().get("log")
    assert (tmp_path / "build" / "main.synctex.gz").exists()

    r = c.post("/api/synctex/view", json={"file": "main.tex", "line": 1, "column": 1})
    assert r.status_code == 200, r.get_json()
    d = r.get_json()
    assert d["page"] >= 1


def test_zahlen_register(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    assert c.get("/api/zahlen").get_json()["found"] is False

    (tmp_path / "zahlen").mkdir()
    (tmp_path / "zahlen" / "zahlen.tex").write_text(
        "\\expandafter\\def\\csname zahl@bl.anzahl\\endcsname{three}\n"
        "\\expandafter\\def\\csname zahl@bl.pauc\\endcsname{0.955}\n"
        "\\expandafter\\def\\csname zahl@x.times\\endcsname{7\\ensuremath{\\times}}\n",
        encoding="utf-8")

    d = c.get("/api/zahlen").get_json()
    assert d["found"] is True
    assert d["source"] == "zahlen/zahlen.tex"
    assert d["count"] == 3
    by_key = {e["key"]: e for e in d["entries"]}
    assert by_key["bl.pauc"]["display"] == "0.955"
    assert by_key["x.times"]["display"] == "7×"


def test_agent_model_config(tmp_path, monkeypatch):
    fake_cfg = {
        "model": "tud-ai/alias-code",
        "provider": {
            "tud-ai": {"models": {"alias-code": {"name": "Coding (alias)"}}},
            "ollama": {"models": {"qwen2.5:7b-fast": {"name": "Qwen fast"}}},
        },
    }
    monkeypatch.setattr(appmod, "_load_global_opencode_config", lambda: fake_cfg)
    c = make_client(tmp_path, monkeypatch)

    d = c.get("/api/agent/model").get_json()
    assert d["current"] == "tud-ai/alias-code"
    assert d["source"] == "global"
    ids = {m["id"] for m in d["models"]}
    assert "tud-ai/alias-code" in ids
    assert "ollama/qwen2.5:7b-fast" in ids

    # unbekanntes Modell -> 400
    r = c.post("/api/agent/model", json={"model": "gibts/nicht"})
    assert r.status_code == 400

    # gültiges Modell -> schreibt Projekt-opencode.json
    r = c.post("/api/agent/model", json={"model": "ollama/qwen2.5:7b-fast"})
    assert r.get_json()["ok"] is True
    import json as _json
    cfg = _json.loads((tmp_path / "opencode.json").read_text())
    assert cfg["model"] == "ollama/qwen2.5:7b-fast"

    d = c.get("/api/agent/model").get_json()
    assert d["current"] == "ollama/qwen2.5:7b-fast"
    assert d["source"] == "projekt"


def test_project_create(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "PROJECTS_ROOT", tmp_path / "projects")
    c = make_client(tmp_path, monkeypatch)

    r = c.post("/api/projects/create", json={"name": "Mein Neues Projekt"})
    d = r.get_json()
    assert d["ok"] is True
    assert d["name"] == "mein-neues-projekt"
    dest = tmp_path / "projects" / "mein-neues-projekt"
    assert (dest / "main.tex").exists()
    assert "\\documentclass" in (dest / "main.tex").read_text()

    # Duplikat -> Suffix -2
    r = c.post("/api/projects/create", json={"name": "mein-neues-projekt"})
    assert r.get_json()["name"] == "mein-neues-projekt-2"

    # leerer Name -> 400
    assert c.post("/api/projects/create", json={"name": "   "}).status_code == 400

    # Wechsel ins neue Projekt funktioniert
    r = c.post("/api/projects/switch", json={"name": "mein-neues-projekt"})
    assert r.get_json()["active"] == "mein-neues-projekt"
    assert "main.tex" in c.get("/api/files").get_json()["files"]


def test_model_tier_mapping():
    assert appmod.classify_model_tier("tud-ai/alias-huge") == "strong"
    assert appmod.classify_model_tier("tud-ai/openai/gpt-oss-120b") == "strong"
    assert appmod.classify_model_tier("ollama/qwen2.5:7b-fast") == "light"
    assert appmod.classify_model_tier("tud-ai/alias-code") == "standard"
    assert appmod.classify_model_tier("minimax/minimax-m3") == "strong"


def test_agent_model_sets_default_agent(tmp_path, monkeypatch):
    fake_cfg = {
        "model": "groq/openai/gpt-oss-120b",
        "provider": {
            "ollama": {"models": {"qwen2.5:7b-fast": {"name": "Qwen fast"}}},
        },
    }
    monkeypatch.setattr(appmod, "_load_global_opencode_config", lambda: fake_cfg)
    c = make_client(tmp_path, monkeypatch)

    d = c.get("/api/agent/model").get_json()
    assert d["tier"] == "strong"
    assert d["agent"] == "whale-strong"

    r = c.post("/api/agent/model", json={"model": "ollama/qwen2.5:7b-fast"})
    j = r.get_json()
    assert j["agent"] == "whale-light"
    import json as _json
    cfg = _json.loads((tmp_path / "opencode.json").read_text())
    assert cfg["model"] == "ollama/qwen2.5:7b-fast"
    assert cfg["default_agent"] == "whale-light"


def test_create_project_installs_agent_kit(tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "PROJECTS_ROOT", tmp_path / "projects")
    c = make_client(tmp_path, monkeypatch)
    d = c.post("/api/projects/create", json={"name": "kit-proj"}).get_json()
    dest = tmp_path / "projects" / d["name"]
    assert (dest / "AGENTS.md").exists()
    assert (dest / ".opencode" / "agent" / "whale-strong.md").exists()
    assert (dest / ".opencode" / "command" / "fix.md").exists()
    assert (dest / ".opencode" / "skills" / "latex-project" / "SKILL.md").exists()


def test_activity_endpoint(tmp_path, monkeypatch):
    c = make_client(tmp_path, monkeypatch)
    d = c.get("/api/activity?since=0").get_json()
    names = [e["name"] for e in d["events"]]
    assert "main.tex" in names
    # seit "jetzt" -> keine alten Events
    d = c.get(f"/api/activity?since={d['now'] + 1}").get_json()
    assert d["events"] == []
