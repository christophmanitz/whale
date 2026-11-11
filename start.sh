#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "Fehler: .venv existiert nicht. Bitte zuerst anlegen:" >&2
  echo "  uv venv .venv && uv pip install --python .venv/bin/python flask requests pytest" >&2
  exit 1
fi

# Startprojekt: default = projects/default, überschreibbar per Env-Variable
export LATEX_PROJECT_DIR="${LATEX_PROJECT_DIR:-$PWD/projects/default}"
mkdir -p "$LATEX_PROJECT_DIR"

source .venv/bin/activate

# app.py startet Web-UI (Port 8765) UND das ttyd-Terminal mit opencode (Port 8762).
# Bei Projektwechsel startet die App ttyd automatisch im neuen Projektordner neu.
python app.py &
APP_PID=$!

trap 'kill $APP_PID 2>/dev/null || true' EXIT

sleep 1.5

# Fenster dem WHALE-Launcher zuordnen (Icon in Dock/Taskleiste statt Chromium)
export BAMF_DESKTOP_FILE_HINT="$HOME/.local/share/applications/whale.desktop"

# --ozone-platform=x11: unter Wayland setzt GNOME sonst das Chromium-Icon
# (WM_CLASS wird nur unter X11/XWayland korrekt dem WHALE-Launcher zugeordnet)
chromium --ozone-platform=x11 --app="http://127.0.0.1:${LATEX_PORT:-8765}" \
         --window-size=1500,950 --class=whale
