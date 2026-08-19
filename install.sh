#!/bin/bash
set -e
PREFIX="${PREFIX:-/usr/local}"
DESTDIR="${DESTDIR:-}"
ICONDIR="${PREFIX}/share/icons/hicolor"
echo "Installing COSMIC Live Wallpaper..."
make clean && make
install -Dm755 cosmic-live-bg "${DESTDIR}${PREFIX}/bin/cosmic-live-bg"
install -Dm755 cosmic-live-wallpaper "${DESTDIR}${PREFIX}/bin/cosmic-live-wallpaper"
install -Dm755 gui/cosmic-live-wallpaper.py "${DESTDIR}${PREFIX}/share/cosmic-live-wallpaper/cosmic-live-wallpaper.py"
install -Dm644 cosmic-live-wallpaper.desktop "${DESTDIR}/usr/share/applications/cosmic-live-wallpaper.desktop"
install -Dm644 icons/128x128/cosmic-live-wallpaper.png "${DESTDIR}${ICONDIR}/128x128/apps/cosmic-live-wallpaper.png"
install -Dm644 icons/256x256/cosmic-live-wallpaper.png "${DESTDIR}${ICONDIR}/256x256/apps/cosmic-live-wallpaper.png"
install -Dm644 icons/512x512/cosmic-live-wallpaper.png "${DESTDIR}${ICONDIR}/512x512/apps/cosmic-live-wallpaper.png"
gtk-update-icon-cache -f "${DESTDIR}${ICONDIR}" 2>/dev/null || true
echo "  Done! Run 'cosmic-live-wallpaper' to open the GUI."
