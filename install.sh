#!/bin/bash
set -e
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
echo "Installing COSMIC Live Wallpaper..."
make clean && make
install -Dm755 cosmic-live-bg "${DESTDIR}${PREFIX}/bin/cosmic-live-bg"
install -Dm755 cosmic-live-wallpaper "${DESTDIR}${PREFIX}/bin/cosmic-live-wallpaper"
install -Dm755 gui/cosmic-live-wallpaper.py "${DESTDIR}${PREFIX}/share/cosmic-live-wallpaper/cosmic-live-wallpaper.py"
install -Dm644 cosmic-live-wallpaper.desktop "${DESTDIR}/usr/share/applications/cosmic-live-wallpaper.desktop"
echo "  Done!"
