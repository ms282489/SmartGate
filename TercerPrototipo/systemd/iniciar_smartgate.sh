#!/bin/sh

# Espera a que el escritorio de Raspberry Pi OS haya creado su socket de
# Wayland o X11. De este modo OpenCV no intenta abrir la ventana demasiado
# pronto durante el encendido.
set -eu

runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export XDG_RUNTIME_DIR="$runtime_dir"

while :; do
    for socket in "$runtime_dir"/wayland-*; do
        if [ -S "$socket" ]; then
            WAYLAND_DISPLAY="${socket##*/}"
            export WAYLAND_DISPLAY
            break 2
        fi
    done

    if [ -S /tmp/.X11-unix/X0 ]; then
        break
    fi

    sleep 1
done

# OpenCV puede utilizar XWayland aunque la sesión principal sea Wayland.
DISPLAY="${DISPLAY:-:0}"
export DISPLAY

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(dirname -- "$script_dir")

cd "$project_dir"
exec "$project_dir/.venv/bin/python" -u app/main.py
