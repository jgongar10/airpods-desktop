#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
SERVICE_NAME="airpods.service"
SERVICE_PATH="$SYSTEMD_DIR/$SERVICE_NAME"
BIN_DIR="$HOME/.local/bin"
BIN_PATH="$BIN_DIR/airpods"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_PATH="$APPS_DIR/airpods.desktop"
OMARCHY_PLUGINS_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/omarchy/plugins"
PLUGIN_ID="airpods"
PLUGIN_LINK="$OMARCHY_PLUGINS_DIR/$PLUGIN_ID"

uninstall() {
  if command -v omarchy >/dev/null 2>&1; then
    omarchy plugin disable "$PLUGIN_ID" >/dev/null 2>&1 || true
  fi

  if [ -L "$PLUGIN_LINK" ] || [ -e "$PLUGIN_LINK" ]; then
    rm -rf "$PLUGIN_LINK"
  fi

  if command -v omarchy-shell >/dev/null 2>&1; then
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  fi

  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
  fi

  rm -f "$SERVICE_PATH"
  if command -v systemctl >/dev/null 2>&1; then
    systemctl --user daemon-reload >/dev/null 2>&1 || true
  fi

  rm -f "$BIN_PATH"
  rm -f "$DESKTOP_PATH"
  echo "Desinstalación completada."
}

install_all() {
  mkdir -p "$BIN_DIR" "$SYSTEMD_DIR" "$OMARCHY_PLUGINS_DIR" "$APPS_DIR"

  ln -sfn "$REPO_DIR/bin/airpods" "$BIN_PATH"

  cat > "$DESKTOP_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=AirPods
Comment=Estado y configuración de tus AirPods
Exec=$BIN_PATH app
Icon=audio-headphones
Terminal=false
Categories=AudioVideo;Audio;Settings;HardwareSettings;
Keywords=airpods;bluetooth;apple;auriculares;bateria;anc;
StartupWMClass=org.gonzavz.AirPods
EOF

  cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Servicio de escritorio para AirPods (AAP + MPRIS)
After=graphical-session.target bluetooth.target

[Service]
Type=simple
WorkingDirectory=$REPO_DIR
Environment=PYTHONPATH=$REPO_DIR
ExecStart=/usr/bin/python3 -m airpods.service
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
EOF

  systemctl --user daemon-reload
  systemctl --user enable "$SERVICE_NAME" >/dev/null
  systemctl --user restart "$SERVICE_NAME"

  ln -sfn "$REPO_DIR/plugin/airpods" "$PLUGIN_LINK"

  if command -v omarchy-shell >/dev/null 2>&1; then
    omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  fi
  if command -v omarchy >/dev/null 2>&1; then
    omarchy plugin enable "$PLUGIN_ID" >/dev/null 2>&1 || true
    omarchy bar move "$PLUGIN_ID" --before omarchy.bluetooth >/dev/null 2>&1 || true
  fi

  echo "Instalación completada."
}

case "${1:-}" in
  --uninstall|uninstall|-u)
    uninstall
    ;;
  ""|--install|install)
    install_all
    ;;
  *)
    echo "Uso: $0 [--uninstall]" >&2
    exit 2
    ;;
esac
